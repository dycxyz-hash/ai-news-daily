#!/usr/bin/env python3
"""
AI 新闻聚合器 — 抓取多个 AI 相关 RSS 源，生成静态 HTML 页面。

用法:
    python generate.py                # 生成 index.html 到当前目录
    python generate.py -o custom.html # 输出到指定文件
"""

import feedparser
import requests
import html as html_module
import sys
import os
import re
import json
from datetime import datetime, timedelta, timezone, date
from calendar import timegm
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════

# 北京时间时区
CST = timezone(timedelta(hours=8))

# 数据保留天数
MAX_DAYS = 7

# 每个源的请求超时（秒）
REQUEST_TIMEOUT = 10

# 输出文件路径
OUTPUT_FILE = "index.html"

# RSS 数据源列表
RSS_SOURCES = [
    {
        "name": "OpenAI",
        "name_zh": "OpenAI 官方博客",
        "url": "https://openai.com/blog/rss.xml",
        "color": "#10a37f",
    },
    {
        "name": "Hugging Face",
        "name_zh": "Hugging Face 博客",
        "url": "https://huggingface.co/blog/feed.xml",
        "color": "#ff9d00",
    },
    {
        "name": "Google AI",
        "name_zh": "Google AI 博客",
        "url": "https://blog.google/technology/ai/rss/",
        "color": "#4285f4",
    },
    {
        "name": "IT之家",
        "name_zh": "IT之家 · AI",
        "url": "https://www.ithome.com/rss/",
        "color": "#d50000",
        # IT之家是综合科技媒体，需要 AI 关键词过滤
        "keywords": [
            "AI", "人工智能", "大模型", "GPT", "LLM", "智能", "机器人",
            "算力", "芯片", "NVIDIA", "英伟达", "OpenAI", "ChatGPT",
            "机器学习", "深度学习", "自动驾驶", "Agent", "智谱",
            "模型", "算法", "数据中心", "神经网络", "GPU",
            "Copilot", "Gemini", "Claude", "DeepSeek", "深度求索",
        ],
    },
    {
        "name": "TechCrunch AI",
        "name_zh": "TechCrunch · AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "color": "#0a960a",
    },
    {
        "name": "ArXiv AI",
        "name_zh": "ArXiv · 人工智能论文",
        "url": "https://export.arxiv.org/rss/cs.AI",
        "color": "#b31b1b",
    },
    {
        "name": "36氪",
        "name_zh": "36氪 · AI 频道",
        "url": "https://36kr.com/feed",
        "color": "#3370ff",
        # 36kr 是综合科技媒体，需要关键词过滤
        "keywords": [
            "AI", "人工智能", "大模型", "GPT", "LLM", "智能", "机器人",
            "算力", "芯片", "NVIDIA", "英伟达", "OpenAI", "ChatGPT",
            "机器学习", "深度学习", "自动驾驶", "Agent", "智谱",
            "Token", "数据", "数字人", "AI", "机器",
        ],
    },
    {
        "name": "量子位",
        "name_zh": "量子位",
        "url": "https://www.qbitai.com/feed",
        "color": "#6c5ce7",
    },
]

# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════


def parse_entry_date(entry, source_name):
    """
    从 feedparser entry 中提取发布时间。
    返回 (datetime_in_utc, error_string_or_None)
    """
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                return datetime.fromtimestamp(timegm(val), tz=timezone.utc), None
            except Exception:
                pass

    # 尝试手动解析 published 字符串
    published_str = getattr(entry, "published", "") or ""
    if published_str:
        try:
            # 尝试多种常见格式
            for fmt in (
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(published_str.strip(), fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt, None
                except ValueError:
                    continue
        except Exception:
            pass

    # 无法解析，使用当前时间并标记
    return datetime.now(timezone.utc), "无法解析日期"


def fetch_feed(source):
    """
    抓取单个 RSS 源，返回 (source_name, entries_list, error_msg_or_None)。

    每个 entry 为 dict: {title, link, published_dt, source_name, source_color}
    """
    name = source["name"]
    url = source["url"]
    color = source["color"]

    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-News-Aggregator/1.0; "
                    "+https://github.com/user/ai-news-aggregator)"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        resp.raise_for_status()

        # feedparser 尝试：先用 bytes，失败再用 text（处理编码/格式问题）
        feed = feedparser.parse(resp.content)

        if feed.bozo and not feed.entries:
            # 回退：用 text 模式重试
            try:
                resp.encoding = "utf-8"
                feed = feedparser.parse(resp.text)
            except Exception:
                pass

        if feed.bozo and not feed.entries:
            return name, [], f"RSS 解析失败: {getattr(feed.bozo_exception, 'getMessage', lambda: str(feed.bozo_exception))()}"

        entries = []
        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title:
                continue

            # 清理 HTML 标签
            title = re.sub(r"<[^>]+>", "", title)
            title = html_module.unescape(title)

            # 关键词过滤（仅对配置了 keywords 的源生效，过滤非 AI 相关内容）
            keywords = source.get("keywords")
            if keywords:
                title_lower = title.lower()
                if not any(kw.lower() in title_lower for kw in keywords):
                    continue

            # 提取摘要（优先 summary，其次 description）
            summary = ""
            for attr in ("summary", "description"):
                val = getattr(entry, attr, None)
                if val:
                    raw = val[0].get("value", "") if isinstance(val, list) else str(val)
                    raw = re.sub(r"<[^>]+>", "", raw)
                    raw = html_module.unescape(raw).strip()
                    if len(raw) > 200:
                        # 在完整句子处截断
                        cut = raw.rfind("。", 0, 200)
                        if cut == -1:
                            cut = raw.rfind(". ", 0, 200)
                        if cut == -1:
                            cut = raw.rfind(" ", 0, 200)
                        if cut > 50:
                            raw = raw[:cut+1] + "…"
                        else:
                            raw = raw[:200] + "…"
                    summary = raw
                    break

            published_dt, date_error = parse_entry_date(entry, name)

            entries.append(
                {
                    "title": title,
                    "link": link or "#",
                    "summary": summary,
                    "published_dt": published_dt,
                    "source_name": name,
                    "source_color": color,
                    "date_error": date_error,
                }
            )

        status = "✓" if entries else "(空)"
        print(f"  [{status}] {name}: {len(entries)} 条")

        return name, entries, None

    except requests.exceptions.Timeout:
        msg = f"请求超时 ({REQUEST_TIMEOUT}s)"
        print(f"  [✗] {name}: {msg}")
        return name, [], msg

    except requests.exceptions.ConnectionError as e:
        msg = f"连接失败: {str(e)[:100]}"
        print(f"  [✗] {name}: {msg}")
        return name, [], msg

    except requests.exceptions.HTTPError as e:
        msg = f"HTTP 错误: {e.response.status_code if e.response else str(e)[:100]}"
        print(f"  [✗] {name}: {msg}")
        return name, [], msg

    except Exception as e:
        msg = f"未知错误: {str(e)[:200]}"
        print(f"  [✗] {name}: {msg}")
        return name, [], msg


def normalize_title(title):
    """标准化标题用于去重比对。"""
    return re.sub(r"\s+", " ", title.strip().lower())


def beijing_date(dt):
    """将 UTC datetime 转换为北京时间日期。"""
    return dt.astimezone(CST).date()


def beijing_str(dt):
    """将 UTC datetime 转换为北京时间字符串。"""
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M")


# ═══════════════════════════════════════════════════════════════════
# HTML 生成
# ═══════════════════════════════════════════════════════════════════

CSS = r"""
/* ── Reset ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}

/* ── Variables ── */
:root{
    --green-50:#f1f8f4; --green-100:#dceee1; --green-200:#b8dbc0;
    --green-300:#8cc598; --green-400:#5faa70; --green-500:#3d8c50;
    --green-600:#2d6e3c; --green-700:#255831; --green-800:#1f4728;
    --text:#1b281d; --text-muted:#5a6b5d; --text-light:#88998b;
    --bg:#fff; --bg-alt:#f6faf7; --border:#e3ece5;
    --shadow-sm:0 1px 3px rgba(0,0,0,.04); --shadow:0 2px 12px rgba(0,0,0,.06);
    --radius-sm:6px; --radius:10px; --radius-lg:16px;
}

/* ── Body ── */
body{
    font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg); color:var(--text); line-height:1.65;
    min-height:100vh; display:flex; flex-direction:column;
    -webkit-font-smoothing:antialiased;
}

/* ── Header ── */
header{
    background:linear-gradient(160deg,#1b5e2a 0%,#2e7d32 40%,#388e3c 70%,#43a047 100%);
    color:#fff; padding:56px 24px 44px; text-align:center; position:relative; overflow:hidden;
}
header::after{
    content:""; position:absolute; inset:0;
    background:radial-gradient(ellipse at 20% 80%,rgba(255,255,255,.06) 0%,transparent 55%),
              radial-gradient(ellipse at 75% 20%,rgba(255,255,255,.04) 0%,transparent 50%),
              radial-gradient(ellipse at 50% 50%,rgba(0,0,0,.08) 0%,transparent 70%);
}
header .lang-switch{
    position:absolute; top:16px; right:20px; z-index:10;
    display:flex; gap:2px; background:rgba(255,255,255,.15); border-radius:20px; padding:3px;
    backdrop-filter:blur(8px);
}
header .lang-switch button{
    border:none; background:transparent; color:rgba(255,255,255,.7);
    padding:5px 14px; border-radius:18px; cursor:pointer; font-size:.82em;
    font-weight:500; transition:all .2s; font-family:inherit;
}
header .lang-switch button.active{background:#fff; color:#2e7d32;}
header .lang-switch button:hover:not(.active){color:#fff;}
header h1{font-size:2.4em;font-weight:700;letter-spacing:-.01em;position:relative;z-index:1}
header p{margin-top:6px;font-size:.95em;opacity:.75;position:relative;z-index:1;font-weight:400}

/* ── Stats Bar ── */
.stats-bar{
    display:flex;justify-content:center;gap:40px;flex-wrap:wrap;
    padding:14px 20px;background:var(--bg-alt);border-bottom:1px solid var(--border);
    font-size:.85em;color:var(--text-muted);
}
.stats-bar .stat-num{font-weight:700;color:var(--green-600)}
.stats-bar .stat-icon{opacity:.6;margin-right:2px}

/* ── Main ── */
main{flex:1;max-width:780px;width:100%;margin:0 auto;padding:36px 20px 56px}

/* ── Date Section ── */
.date-section{margin-bottom:44px}
.date-section h2{
    font-size:1em;font-weight:600;color:var(--green-700);
    padding-bottom:10px;border-bottom:1.5px solid var(--green-100);
    margin-bottom:12px;position:sticky;top:0;background:var(--bg);z-index:2;
    display:flex;align-items:center;gap:8px;
}
.date-section h2 .dot{width:7px;height:7px;border-radius:50%;background:var(--green-400);flex-shrink:0}

/* ── Timeline ── */
.timeline{
    position:fixed;left:max(12px,calc((100vw - 840px)/2 - 56px));
    top:50%;transform:translateY(-50%);z-index:100;
    display:flex;flex-direction:column;gap:6px;
}
.timeline a{
    display:flex;align-items:center;gap:8px;text-decoration:none;
    font-size:.7em;color:var(--text-light);padding:4px 8px;border-radius:14px;
    transition:all .2s;white-space:nowrap;
}
.timeline a:hover,.timeline a.active{color:var(--green-600);background:var(--green-50)}
.timeline a .tl-dot{width:6px;height:6px;border-radius:50%;background:var(--green-300);flex-shrink:0}
.timeline a:hover .tl-dot,.timeline a.active .tl-dot{background:var(--green-500)}
.timeline a .tl-label{display:none}
.timeline a:hover .tl-label{display:inline}

/* ── News Card ── */
.news-list{list-style:none}
.news-item{
    display:flex;align-items:flex-start;gap:10px;
    border-radius:var(--radius-sm);transition:background .12s;margin-bottom:2px;
}
.news-item:hover{background:var(--green-50)}

.source-badge{
    flex-shrink:0;display:inline-block;padding:1px 9px;border-radius:4px;
    font-size:.72em;font-weight:600;color:#fff;line-height:1.7;white-space:nowrap;
    letter-spacing:.01em;opacity:.92;margin-top:9px;
}

/* ── Details / Accordion ── */
.news-details{flex:1;min-width:0}
.news-details summary{
    list-style:none;cursor:pointer;padding:10px 12px;border-radius:var(--radius-sm);
    font-size:.94em;font-weight:500;color:var(--text);
    transition:color .15s,background .15s;
    display:flex;align-items:center;justify-content:space-between;gap:8px;
}
.news-details summary::-webkit-details-marker{display:none}
.news-details summary::marker{display:none;content:''}
.news-details summary:hover{color:var(--green-600);background:var(--green-50)}
.news-details summary .arrow{
    flex-shrink:0;font-size:.65em;opacity:.3;transition:transform .25s;
}
.news-details[open] summary .arrow{transform:rotate(180deg)}
.news-details[open] summary{color:var(--green-700);font-weight:600}

.news-summary{
    padding:6px 12px 14px;font-size:.88em;color:var(--text-muted);
    line-height:1.7;animation:fadeIn .25s;
}
.news-summary p{margin-bottom:10px}
.news-summary .read-more{
    display:inline-block;color:var(--green-600);text-decoration:none;
    font-weight:600;font-size:.92em;padding:5px 14px;
    border:1px solid var(--green-200);border-radius:16px;
    transition:all .15s;
}
.news-summary .read-more:hover{background:var(--green-100);border-color:var(--green-400)}
.news-no-summary{padding:6px 12px 14px;font-size:.85em;color:var(--text-light)}

@keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}

/* ── Empty State ── */
.empty-state{text-align:center;padding:80px 24px;color:var(--text-light)}
.empty-state .icon{font-size:2.8em;margin-bottom:14px}
.empty-state p{font-size:1em}

/* ── Footer ── */
footer{
    text-align:center;padding:24px;font-size:.78em;color:var(--text-light);
    border-top:1px solid var(--border);margin-top:auto;background:var(--bg-alt);
}
footer p+p{margin-top:3px}
footer .error-item{color:#c62828;font-size:.88em;margin-top:3px}
footer a{color:var(--green-600);text-decoration:none}
footer a:hover{text-decoration:underline}

/* ── Lang visibility ── */
[data-lang]{display:none}
html[lang="zh"] [data-lang="zh"]{display:revert}
html[lang="en"] [data-lang="en"]{display:none}
html[lang="en"] [data-lang="en"]{display:revert}

/* ── Responsive ── */
@media(max-width:860px){
    .timeline{display:none}
}
@media(max-width:640px){
    header{padding:40px 18px 32px}
    header h1{font-size:1.7em}
    header .lang-switch{top:10px;right:10px}
    main{padding:24px 12px 36px}
    .stats-bar{gap:18px;font-size:.78em}
    .news-details summary{font-size:.9em;padding:10px 8px}
    .source-badge{font-size:.66em;padding:1px 6px;margin-top:9px}
    .news-summary{font-size:.84em;padding:4px 8px 10px}
    .news-item{gap:6px}
}
"""


# ═══════════════════════════════════════════════════════════════════
# 多语言字符串
# ═══════════════════════════════════════════════════════════════════

I18N = {
    "zh": {
        "lang_label": "中文",
        "page_title": "🧠 AI 发展日报",
        "site_desc": "每小时自动聚合 AI 领域最新资讯",
        "stats_articles": "条新闻",
        "stats_sources": "源正常",
        "stats_days_prefix": "保留最近",
        "stats_days_suffix": "天",
        "today": "今天",
        "yesterday": "昨天",
        "weekdays": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        "empty_title": "暂无新闻数据",
        "empty_hint": "请稍后再来，或手动触发更新。",
        "footer_update": "最后更新",
        "footer_timezone": "北京时间",
        "footer_sources": "数据来源",
        "footer_powered": "由 GitHub Actions 自动更新 · RSS 聚合",
        "error_prefix": "⚠️",
    },
    "en": {
        "lang_label": "English",
        "page_title": "🧠 AI Daily",
        "site_desc": "Hourly AI news aggregation",
        "stats_articles": "articles",
        "stats_sources": "sources OK",
        "stats_days_prefix": "Last",
        "stats_days_suffix": "days",
        "today": "Today",
        "yesterday": "Yesterday",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "empty_title": "No news yet",
        "empty_hint": "Check back later or trigger a manual update.",
        "footer_update": "Last updated",
        "footer_timezone": "CST",
        "footer_sources": "Sources",
        "footer_powered": "Powered by GitHub Actions · RSS Aggregation",
        "error_prefix": "⚠️",
    },
}

JS = r"""
<script>
// ── Language switcher ──
(function(){
    var L = (localStorage.getItem('ai-news-lang') || 'zh');
    document.documentElement.lang = L;
    var btns = document.querySelectorAll('.lang-switch button');
    function setLang(l){
        document.documentElement.lang = l;
        localStorage.setItem('ai-news-lang', l);
        btns.forEach(function(b){b.classList.toggle('active', b.dataset.lang === l)});
    }
    btns.forEach(function(b){b.addEventListener('click',function(){setLang(this.dataset.lang)})});
    setLang(L);
})();

// ── Timeline scroll-spy ──
(function(){
    var links = document.querySelectorAll('.timeline a');
    if (!links.length) return;
    var sections = [];
    links.forEach(function(a){
        var id = a.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (el) sections.push({el:el, a:a});
    });
    function update(){
        var scrollY = window.scrollY + 80;
        var active = null;
        sections.forEach(function(s){
            if (s.el.offsetTop <= scrollY) active = s.a;
        });
        links.forEach(function(a){a.classList.remove('active')});
        if (active) active.classList.add('active');
    }
    window.addEventListener('scroll', update, {passive:true});
    update();
})();
</script>
"""


def i18n_date_label(d, lang):
    """生成日期标签，今天/昨天显示特殊文字。"""
    today = datetime.now(CST).date()
    t = I18N[lang]
    if d == today:
        return f"{t['today']} · {d}"
    elif d == today - timedelta(days=1):
        return f"{t['yesterday']} · {d}"
    else:
        wd = t["weekdays"][d.weekday()]
        return f"{wd} · {d}"


def generate_html(entries_by_date, update_time, errors):
    """
    生成完整 HTML 页面。

    entries_by_date: OrderedDict[date -> list of entry dicts]
    update_time: str (北京时间)
    errors: list of (source_name, error_msg)
    """
    # ── 统计数据 ──
    total_articles = sum(len(v) for v in entries_by_date.values())
    source_count = len(RSS_SOURCES)
    success_count = source_count - len(errors)

    # ── 构建日期区块 ──
    date_sections_html = ""

    timeline_links = ""

    if entries_by_date:
        for d, entries in sorted(entries_by_date.items(), reverse=True):
            date_id = f"date-{d.isoformat()}"
            label_zh = i18n_date_label(d, "zh")
            label_en = i18n_date_label(d, "en")

            # 时间轴条目
            short_label = f"{d.month}/{d.day}"
            timeline_links += (
                f'<a href="#{date_id}">'
                f'<span class="tl-dot"></span>'
                f'<span class="tl-label">{short_label}</span>'
                f'</a>\n'
            )

            items_html = ""
            for e in entries:
                badge = (
                    f'<span class="source-badge" style="background:{e["source_color"]};" '
                    f'title="{html_module.escape(e["source_name"])}">'
                    f'{html_module.escape(e["source_name"])}</span>'
                )
                if e.get("summary"):
                    body = (
                        f'<div class="news-summary">'
                        f'<p>{html_module.escape(e["summary"])}</p>'
                        f'<a href="{html_module.escape(e["link"])}" '
                        f'target="_blank" rel="noopener noreferrer" class="read-more">'
                        f'<span data-lang="zh">阅读原文</span>'
                        f'<span data-lang="en">Read more</span>'
                        f' →</a></div>'
                    )
                else:
                    body = (
                        f'<div class="news-no-summary">'
                        f'<a href="{html_module.escape(e["link"])}" '
                        f'target="_blank" rel="noopener noreferrer" class="read-more">'
                        f'<span data-lang="zh">阅读原文</span>'
                        f'<span data-lang="en">Read more</span>'
                        f' →</a></div>'
                    )
                items_html += (
                    f'<li class="news-item">'
                    f'{badge}'
                    f'<details class="news-details">'
                    f'<summary>{html_module.escape(e["title"])}'
                    f'<span class="arrow">▾</span></summary>'
                    f'{body}'
                    f'</details>'
                    f'</li>\n'
                )

            date_sections_html += (
                f'<section class="date-section" id="{date_id}">\n'
                f'<h2><span class="dot"></span>'
                f'<span data-lang="zh">{label_zh}</span>'
                f'<span data-lang="en">{label_en}</span>'
                f'</h2>\n'
                f'<ul class="news-list">\n{items_html}</ul>\n'
                f'</section>\n'
            )
    else:
        date_sections_html = (
            '<div class="empty-state">\n'
            '<div class="icon">📭</div>\n'
            f'<p data-lang="zh">{html_module.escape(I18N["zh"]["empty_title"])}</p>\n'
            f'<p data-lang="en">{html_module.escape(I18N["en"]["empty_title"])}</p>\n'
            f'<p data-lang="zh" style="font-size:.88em;margin-top:6px;">{html_module.escape(I18N["zh"]["empty_hint"])}</p>\n'
            f'<p data-lang="en" style="font-size:.88em;margin-top:6px;">{html_module.escape(I18N["en"]["empty_hint"])}</p>\n'
            '</div>\n'
        )

    # ── 错误信息 ──
    errors_html = ""
    if errors:
        for src_name, err_msg in errors:
            errors_html += (
                f'<p class="error-item">'
                f'⚠️ {html_module.escape(src_name)}: {html_module.escape(err_msg)}'
                f'</p>\n'
            )

    repo = _repo_placeholder()
    repo_link = f'https://github.com/{repo}' if repo else "#"
    sources_str = ", ".join(html_module.escape(s["name"]) for s in RSS_SOURCES)

    # ── 组装页面 ──
    html_content = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="AI 发展日报 — 每日自动聚合 AI 领域最新资讯 | AI Daily — Automated AI news aggregation">
<meta name="color-scheme" content="light">
<title>🧠 AI 发展日报 / AI Daily</title>
<style>{CSS}</style>
</head>
<body>

<header>
    <div class="lang-switch">
        <button data-lang="zh">中文</button>
        <button data-lang="en">English</button>
    </div>
    <h1 data-lang="zh">🧠 AI 发展日报</h1>
    <h1 data-lang="en">🧠 AI Daily</h1>
    <p data-lang="zh">{html_module.escape(I18N["zh"]["site_desc"])}</p>
    <p data-lang="en">{html_module.escape(I18N["en"]["site_desc"])}</p>
</header>

<div class="stats-bar">
    <span>
        <span class="stat-icon">📰</span>
        <span class="stat-num">{total_articles}</span>
        <span data-lang="zh">{I18N["zh"]["stats_articles"]}</span>
        <span data-lang="en">{I18N["en"]["stats_articles"]}</span>
    </span>
    <span>
        <span class="stat-icon">📡</span>
        <span class="stat-num">{success_count}/{source_count}</span>
        <span data-lang="zh">{I18N["zh"]["stats_sources"]}</span>
        <span data-lang="en">{I18N["en"]["stats_sources"]}</span>
    </span>
    <span>
        <span class="stat-icon">📆</span>
        <span data-lang="zh">{I18N["zh"]["stats_days_prefix"]}</span>
        <span data-lang="en">{I18N["en"]["stats_days_prefix"]}</span>
        &nbsp;<span class="stat-num">{MAX_DAYS}</span>&nbsp;
        <span data-lang="zh">{I18N["zh"]["stats_days_suffix"]}</span>
        <span data-lang="en">{I18N["en"]["stats_days_suffix"]}</span>
    </span>
</div>

{f'''<nav class="timeline" aria-label="Date navigation">
{timeline_links}
</nav>''' if timeline_links else ""}

<main>
{date_sections_html}
</main>

<footer>
    <p>
        🕐 <span data-lang="zh">{I18N["zh"]["footer_update"]}：{html_module.escape(update_time)}（{I18N["zh"]["footer_timezone"]}）</span>
        <span data-lang="en">{I18N["en"]["footer_update"]}: {html_module.escape(update_time)} ({I18N["en"]["footer_timezone"]})</span>
    </p>
    <p>
        <span data-lang="zh">{I18N["zh"]["footer_sources"]}：{sources_str}</span>
        <span data-lang="en">{I18N["en"]["footer_sources"]}: {sources_str}</span>
    </p>
{errors_html}
    <p style="margin-top:6px;">
        <span data-lang="zh">{I18N["zh"]["footer_powered"]}</span>
        <span data-lang="en">{I18N["en"]["footer_powered"]}</span>
        · <a href="{repo_link}" target="_blank" rel="noopener">GitHub</a>
    </p>
</footer>

{JS}
</body>
</html>"""

    return html_content


def _repo_placeholder():
    """尝试从环境变量获取仓库信息，否则返回占位符。"""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        return repo
    return ""


# ═══════════════════════════════════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════════════════════════════════


def main():
    output_path = OUTPUT_FILE

    # 解析命令行参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-o", "--output") and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            return
        else:
            print(f"未知参数: {args[i]}")
            print(__doc__)
            sys.exit(1)

    print("=" * 60)
    print("🧠 AI 新闻聚合器")
    print(f"   运行时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print(f"   数据源数量: {len(RSS_SOURCES)}")
    print(f"   保留天数: {MAX_DAYS}")
    print(f"   输出文件: {output_path}")
    print("=" * 60)

    # ── 并发抓取所有源 ──
    print("\n📡 正在抓取 RSS 源...\n")

    all_entries = []
    fetch_errors = []

    with ThreadPoolExecutor(max_workers=min(len(RSS_SOURCES), 6)) as executor:
        futures = {executor.submit(fetch_feed, src): src for src in RSS_SOURCES}
        for future in as_completed(futures):
            src = futures[future]
            try:
                name, entries, error = future.result()
                all_entries.extend(entries)
                if error:
                    fetch_errors.append((name, error))
            except Exception as e:
                fetch_errors.append((src["name"], f"线程异常: {str(e)[:200]}"))

    # ── 去重 ──
    seen = set()
    unique_entries = []
    for entry in all_entries:
        key = (normalize_title(entry["title"]), entry["source_name"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)

    duplicate_count = len(all_entries) - len(unique_entries)
    if duplicate_count:
        print(f"\n🔍 去重: 移除 {duplicate_count} 条重复条目")

    # ── 按北京时间日期分组 ──
    cutoff_date = datetime.now(CST).date() - timedelta(days=MAX_DAYS)
    entries_by_date = defaultdict(list)

    for entry in unique_entries:
        d = beijing_date(entry["published_dt"])
        if d >= cutoff_date:
            entries_by_date[d].append(entry)

    # 每组内按时间倒序排列
    for d in entries_by_date:
        entries_by_date[d].sort(key=lambda e: e["published_dt"], reverse=True)

    # ── 生成 HTML ──
    print(f"\n📝 生成 HTML...")
    update_time = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    html_content = generate_html(entries_by_date, update_time, fetch_errors)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # ── 打印摘要 ──
    total = sum(len(v) for v in entries_by_date.values())
    ok_sources = len(RSS_SOURCES) - len(fetch_errors)
    print(f"\n{'=' * 60}")
    print(f"✅ 完成！")
    print(f"   新闻总数: {total} 条（去重后）")
    print(f"   成功源:   {ok_sources}/{len(RSS_SOURCES)}")
    print(f"   日期范围: {min(entries_by_date.keys()) if entries_by_date else 'N/A'}"
          f" ~ {max(entries_by_date.keys()) if entries_by_date else 'N/A'}")
    print(f"   输出文件: {os.path.abspath(output_path)}")
    if fetch_errors:
        print(f"\n⚠️  以下源抓取失败:")
        for name, msg in fetch_errors:
            print(f"   - {name}: {msg}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
