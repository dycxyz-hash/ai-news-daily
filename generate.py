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
        "name": "AI News",
        "name_zh": "AI News",
        "url": "https://www.artificialintelligence-news.com/feed/",
        "color": "#0077b6",
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

            published_dt, date_error = parse_entry_date(entry, name)

            entries.append(
                {
                    "title": title,
                    "link": link or "#",
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


def date_label(d):
    """生成日期标签，今天/昨天显示特殊文字。"""
    today = datetime.now(CST).date()
    if d == today:
        return f"📅 今天 · {d}"
    elif d == today - timedelta(days=1):
        return f"📅 昨天 · {d}"
    else:
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]
        return f"📅 {weekday} · {d}"


# ═══════════════════════════════════════════════════════════════════
# HTML 生成
# ═══════════════════════════════════════════════════════════════════

CSS = """
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
                 Arial, sans-serif;
    background: #ffffff;
    color: #1a1a1a;
    line-height: 1.7;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

/* ── Header ── */
header {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    color: #fff;
    padding: 48px 24px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
}

header::before {
    content: "";
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(
        circle at 30% 70%,
        rgba(255, 255, 255, 0.03) 0%,
        transparent 50%
    ),
    radial-gradient(
        circle at 70% 30%,
        rgba(255, 255, 255, 0.04) 0%,
        transparent 50%
    );
    pointer-events: none;
}

header h1 {
    font-size: 2.2em;
    font-weight: 700;
    letter-spacing: 0.02em;
    position: relative;
    z-index: 1;
}

header p {
    margin-top: 8px;
    font-size: 0.95em;
    opacity: 0.7;
    position: relative;
    z-index: 1;
}

/* ── Stats Bar ── */
.stats-bar {
    display: flex;
    justify-content: center;
    gap: 32px;
    flex-wrap: wrap;
    padding: 16px 24px;
    background: #f8f9fa;
    border-bottom: 1px solid #e9ecef;
    font-size: 0.88em;
    color: #6b7280;
}

.stats-bar span {
    white-space: nowrap;
}

.stats-bar .stat-num {
    font-weight: 700;
    color: #302b63;
}

/* ── Main Content ── */
main {
    flex: 1;
    max-width: 860px;
    width: 100%;
    margin: 0 auto;
    padding: 32px 20px 48px;
}

/* ── Date Section ── */
.date-section {
    margin-bottom: 40px;
}

.date-section h2 {
    font-size: 1.15em;
    font-weight: 600;
    color: #374151;
    padding-bottom: 10px;
    border-bottom: 2px solid #e5e7eb;
    margin-bottom: 16px;
    position: sticky;
    top: 0;
    background: #fff;
    z-index: 2;
}

/* ── News Card ── */
.news-list {
    list-style: none;
}

.news-item {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 14px 16px;
    border-radius: 10px;
    transition: background 0.15s ease;
    margin-bottom: 2px;
}

.news-item:hover {
    background: #f9fafb;
}

.source-badge {
    flex-shrink: 0;
    display: inline-block;
    padding: 2px 10px;
    border-radius: 5px;
    font-size: 0.78em;
    font-weight: 600;
    color: #fff;
    line-height: 1.6;
    white-space: nowrap;
    margin-top: 1px;
}

.news-item a {
    color: #1a1a1a;
    text-decoration: none;
    font-size: 0.98em;
    font-weight: 500;
    transition: color 0.15s ease;
    word-break: break-word;
}

.news-item a:hover {
    color: #302b63;
}

.news-item a::after {
    content: " ↗";
    font-size: 0.75em;
    opacity: 0.35;
}

/* ── Empty State ── */
.empty-state {
    text-align: center;
    padding: 80px 24px;
    color: #9ca3af;
}

.empty-state .icon {
    font-size: 3em;
    margin-bottom: 16px;
}

.empty-state p {
    font-size: 1.05em;
}

/* ── Footer ── */
footer {
    text-align: center;
    padding: 28px 24px;
    font-size: 0.82em;
    color: #9ca3af;
    border-top: 1px solid #f0f0f0;
    margin-top: auto;
}

footer p + p {
    margin-top: 4px;
}

footer .error-item {
    color: #d32f2f;
    font-size: 0.9em;
    margin-top: 2px;
}

/* ── Responsive ── */
@media (max-width: 640px) {
    header { padding: 32px 20px 28px; }
    header h1 { font-size: 1.6em; }
    main { padding: 20px 14px 32px; }
    .stats-bar { gap: 16px; font-size: 0.8em; }
    .news-item { padding: 12px 10px; gap: 10px; }
    .source-badge { font-size: 0.72em; padding: 1px 8px; }
    .news-item a { font-size: 0.92em; }
}
"""


def generate_html(entries_by_date, update_time, errors):
    """
    生成完整 HTML 页面。

    entries_by_date: OrderedDict[date -> list of entry dicts]
    update_time: str (北京时间)
    errors: list of (source_name, error_msg)
    """
    # 构建日期区块
    date_sections_html = ""

    if entries_by_date:
        for d, entries in sorted(entries_by_date.items(), reverse=True):
            items_html = ""
            for e in entries:
                items_html += (
                    f'<li class="news-item">'
                    f'<span class="source-badge" style="background:{e["source_color"]};" '
                    f'title="{html_module.escape(e["source_name"])}">'
                    f'{html_module.escape(e["source_name"])}</span>'
                    f'<a href="{html_module.escape(e["link"])}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'{html_module.escape(e["title"])}</a>'
                    f"</li>\n"
                )
            date_sections_html += (
                f'<section class="date-section">\n'
                f'<h2>{date_label(d)}</h2>\n'
                f'<ul class="news-list">\n'
                f'{items_html}'
                f'</ul>\n'
                f'</section>\n'
            )
    else:
        date_sections_html = (
            '<div class="empty-state">\n'
            '<div class="icon">📭</div>\n'
            "<p>暂无新闻数据</p>\n"
            "<p style=\"font-size:0.9em;margin-top:8px;\">请稍后再来，或手动触发更新。</p>\n"
            "</div>\n"
        )

    # 统计
    total_articles = sum(len(v) for v in entries_by_date.values())
    source_count = len(RSS_SOURCES)
    success_count = source_count - len(errors)

    # 错误信息
    errors_html = ""
    if errors:
        for src_name, err_msg in errors:
            errors_html += (
                f'<p class="error-item">'
                f'⚠️ {html_module.escape(src_name)}: {html_module.escape(err_msg)}'
                f"</p>\n"
            )

    # 生成完整页面
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="AI 发展日报 — 每日自动聚合 AI 领域最新资讯">
<meta name="color-scheme" content="light">
<title>🧠 AI 发展日报</title>
<style>{CSS}</style>
</head>
<body>

<header>
    <h1>🧠 AI 发展日报</h1>
    <p>每日自动聚合 AI 领域最新资讯 · 北京时间 8:00 更新</p>
</header>

<div class="stats-bar">
    <span>📰 <span class="stat-num">{total_articles}</span> 条新闻</span>
    <span>📡 <span class="stat-num">{success_count}/{source_count}</span> 源正常</span>
    <span>📆 保留最近 <span class="stat-num">{MAX_DAYS}</span> 天</span>
</div>

<main>
{date_sections_html}
</main>

<footer>
    <p>🕐 最后更新：{html_module.escape(update_time)}（北京时间）</p>
    <p>数据来源：{", ".join(html_module.escape(s["name"]) for s in RSS_SOURCES)}</p>
{errors_html}
    <p style="margin-top:8px;">
        Powered by
        <a href="https://github.com/{_repo_placeholder()}" target="_blank" rel="noopener">GitHub Actions</a>
        · 自动更新 · RSS 聚合
    </p>
</footer>

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
