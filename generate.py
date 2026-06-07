#!/usr/bin/env python3
"""
AI 新闻聚合器 — 抓取多个 AI 相关 RSS 源，生成中英双语静态 HTML 页面。

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
import time
from datetime import datetime, timedelta, timezone, date
from calendar import timegm
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════

CST = timezone(timedelta(hours=8))
MAX_DAYS = 7
REQUEST_TIMEOUT = 10
OUTPUT_FILE = "index.html"
TRANSLATE_DELAY = 0.15      # 每条翻译间隔秒数

RSS_SOURCES = [
    {"name": "OpenAI",      "url": "https://openai.com/blog/rss.xml",                    "color": "#10a37f"},
    {"name": "Hugging Face","url": "https://huggingface.co/blog/feed.xml",               "color": "#ff9d00"},
    {"name": "Google AI",   "url": "https://blog.google/technology/ai/rss/",             "color": "#4285f4"},
    {"name": "TechCrunch",  "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "color": "#0a960a"},
    {"name": "ArXiv AI",    "url": "https://export.arxiv.org/rss/cs.AI",                  "color": "#b31b1b"},
    {"name": "IT之家",       "url": "https://www.ithome.com/rss/",                         "color": "#d50000",
     "keywords": ["AI","人工智能","大模型","GPT","LLM","智能","机器人","算力","芯片","NVIDIA","英伟达",
                  "OpenAI","ChatGPT","机器学习","深度学习","自动驾驶","Agent","智谱","模型","算法",
                  "数据中心","神经网络","GPU","Copilot","Gemini","Claude","DeepSeek","深度求索"]},
    {"name": "36氪",         "url": "https://36kr.com/feed",                                "color": "#3370ff",
     "keywords": ["AI","人工智能","大模型","GPT","LLM","智能","机器人","算力","芯片","NVIDIA","英伟达",
                  "OpenAI","ChatGPT","机器学习","深度学习","自动驾驶","Agent","智谱","Token","数字人","机器"]},
    {"name": "量子位",       "url": "https://www.qbitai.com/feed",                           "color": "#6c5ce7"},
]


# ═══════════════════════════════════════════════════════════════════
# 翻译模块
# ═══════════════════════════════════════════════════════════════════

def _has_cjk(text):
    """检测文本是否包含中日韩字符。"""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF or
            0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF):
            return True
    return False


def translate_text(text, target_lang):
    """
    使用 MyMemory 免费 API 翻译。失败时返回原文。
    target_lang: 'zh' 或 'en'
    """
    if not text or not text.strip():
        return text
    try:
        src_lang = "zh-CN" if _has_cjk(text) else "en"
        target = "zh-CN" if target_lang == "zh" else "en"
        # 如果源和目标相同，不需要翻译
        if (src_lang == "zh-CN" and target == "zh-CN") or (src_lang == "en" and target == "en"):
            return text

        pair = f"{src_lang}|{target}"
        url = "https://api.mymemory.translated.net/get"
        resp = requests.get(url, params={"q": text, "langpair": pair}, timeout=15)
        data = resp.json()
        if data.get("responseStatus") == 200:
            result = data.get("responseData", {}).get("translatedText", "")
            if result and result.strip():
                return html_module.unescape(result.strip())
    except Exception:
        pass
    return text


def translate_entries(entries):
    """
    对所有条目进行双向翻译。
    - 英文条目 → 翻译标题和摘要为中文
    - 中文条目 → 翻译标题和摘要为英文
    - 翻译失败则保持原文

    返回: 条目列表，每个条目新增 zh_title, en_title, zh_summary, en_summary
    """
    print("\n🌐 正在翻译...")

    # 分类：哪些需要英→中，哪些需要中→英
    en_to_zh = []   # (index, entry)
    zh_to_en = []

    for i, e in enumerate(entries):
        title = e.get("title", "")
        if _has_cjk(title):
            zh_to_en.append(i)
        else:
            en_to_zh.append(i)

    total = len(en_to_zh) + len(zh_to_en)
    if total == 0:
        print("   无需翻译")
        return entries

    translated = 0
    failed = 0

    # 英→中
    batch = []
    for idx in en_to_zh:
        e = entries[idx]
        orig_title = e.get("title", "")
        orig_summary = e.get("summary", "")
        entries[idx]["en_title"] = orig_title
        entries[idx]["en_summary"] = orig_summary

        if orig_title:
            batch.append((idx, "title", orig_title, "zh"))
        if orig_summary:
            batch.append((idx, "summary", orig_summary, "zh"))

    for idx, field, text, target in batch:
        result = translate_text(text, target)
        entries[idx][f"zh_{field}"] = result if result else text
        if result and result != text:
            translated += 1
        else:
            failed += 1
            entries[idx][f"zh_{field}"] = text
        time.sleep(0.3)  # 限速

    # 中→英
    batch2 = []
    for idx in zh_to_en:
        e = entries[idx]
        orig_title = e.get("title", "")
        orig_summary = e.get("summary", "")
        entries[idx]["zh_title"] = orig_title
        entries[idx]["zh_summary"] = orig_summary

        if orig_title:
            batch2.append((idx, "title", orig_title, "en"))
        if orig_summary:
            batch2.append((idx, "summary", orig_summary, "en"))

    for idx, field, text, target in batch2:
        result = translate_text(text, target)
        entries[idx][f"en_{field}"] = result if result else text
        if result and result != text:
            translated += 1
        else:
            failed += 1
            entries[idx][f"en_{field}"] = text
        time.sleep(0.3)

    # 处理未被分类的条目（中英混合等边缘情况）
    for i, e in enumerate(entries):
        if "zh_title" not in e:
            e["zh_title"] = e.get("title", "")
        if "en_title" not in e:
            e["en_title"] = e.get("title", "")
        if "zh_summary" not in e:
            e["zh_summary"] = e.get("summary", "")
        if "en_summary" not in e:
            e["en_summary"] = e.get("summary", "")

    print(f"   完成: {translated} 条翻译成功, {failed} 条保持原文")
    return entries


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════

def parse_entry_date(entry, source_name):
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                return datetime.fromtimestamp(timegm(val), tz=timezone.utc), None
            except Exception:
                pass
    published_str = getattr(entry, "published", "") or ""
    if published_str:
        try:
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(published_str.strip(), fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt, None
                except ValueError:
                    continue
        except Exception:
            pass
    return datetime.now(timezone.utc), "无法解析日期"


def fetch_feed(source):
    name = source["name"]
    url = source["url"]
    color = source["color"]
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-News-Aggregator/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            try:
                resp.encoding = "utf-8"
                feed = feedparser.parse(resp.text)
            except Exception:
                pass
        if feed.bozo and not feed.entries:
            err = getattr(feed.bozo_exception, 'getMessage', lambda: str(feed.bozo_exception))()
            return name, [], f"RSS 解析失败: {err}"

        entries = []
        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title:
                continue
            title = re.sub(r"<[^>]+>", "", title)
            title = html_module.unescape(title)

            keywords = source.get("keywords")
            if keywords:
                if not any(kw.lower() in title.lower() for kw in keywords):
                    continue

            summary = ""
            for attr in ("summary", "description"):
                val = getattr(entry, attr, None)
                if val:
                    raw = val[0].get("value", "") if isinstance(val, list) else str(val)
                    raw = re.sub(r"<[^>]+>", "", raw)
                    raw = html_module.unescape(raw).strip()
                    summary = raw
                    break

            published_dt, date_error = parse_entry_date(entry, name)
            entries.append({
                "title": title, "link": link or "#", "summary": summary,
                "published_dt": published_dt, "source_name": name,
                "source_color": color, "date_error": date_error,
            })

        status = "✓" if entries else "(空)"
        print(f"  [{status}] {name}: {len(entries)} 条")
        return name, entries, None

    except requests.exceptions.Timeout:
        return name, [], f"请求超时 ({REQUEST_TIMEOUT}s)"
    except requests.exceptions.ConnectionError as e:
        return name, [], f"连接失败: {str(e)[:100]}"
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        return name, [], f"HTTP {code}"
    except Exception as e:
        return name, [], f"错误: {str(e)[:200]}"


def normalize_title(title):
    return re.sub(r"\s+", " ", title.strip().lower())


def beijing_date(dt):
    return dt.astimezone(CST).date()


# ═══════════════════════════════════════════════════════════════════
# HTML / CSS / JS
# ═══════════════════════════════════════════════════════════════════

CSS = r"""
/* ── Reset ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-font-smoothing:antialiased}

/* ── Variables ── */
:root{
    --g:#059669;--gd:#047857;--gl:#10b981;--gll:#d1fae5;--glg:#ecfdf5;
    --tx:#111827;--t2:#4b5563;--t3:#9ca3af;
    --bg:#fff;--bg2:#f9fafb;--br:#e5e7eb;
    --r:12px;--rh:8px;
}

/* ── Body ── */
body{
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--tx);line-height:1.6;min-height:100vh;
    display:flex;flex-direction:column;
}

/* ── Header ── */
header{
    padding:72px 24px 40px;text-align:center;position:relative;
    background:linear-gradient(175deg,#f0fdf4 0%,#fff 60%,#fff 100%);
    border-bottom:1px solid var(--gll);
}
header .lang-row{display:flex;justify-content:flex-end;max-width:720px;margin:0 auto 24px}
header .lang-sw{
    display:inline-flex;background:#f3f4f6;border-radius:20px;padding:2px;
}
header .lang-sw button{
    border:none;background:transparent;color:var(--t2);padding:6px 16px;
    border-radius:18px;cursor:pointer;font-size:.8em;font-weight:500;
    transition:all .2s;font-family:inherit;
}
header .lang-sw button.on{background:#fff;color:var(--g);box-shadow:0 1px 4px rgba(0,0,0,.08)}
header h1{font-size:2.6em;font-weight:800;letter-spacing:-.02em;color:var(--tx);
    max-width:720px;margin:0 auto}
header h1 span.grad{background:linear-gradient(135deg,var(--g),var(--gl));-webkit-background-clip:text;
    -webkit-text-fill-color:transparent;background-clip:text}
header .sub{margin-top:10px;font-size:1.05em;color:var(--t3);font-weight:400;
    max-width:720px;margin-left:auto;margin-right:auto}

/* ── Stats ── */
.stats{
    display:flex;justify-content:center;gap:48px;flex-wrap:wrap;
    padding:20px 20px;background:var(--bg2);border-bottom:1px solid var(--br);
    font-size:.88em;color:var(--t3);
}
.stats .val{font-weight:700;color:var(--g);font-size:1.15em}

/* ── Main layout ── */
main-wrap{display:flex;max-width:1100px;width:100%;margin:0 auto;padding:0 20px;flex:1}
main{flex:1;max-width:740px;width:100%;margin:0 auto;padding:40px 0 64px}

/* ── Timeline ── */
aside.tl{
    width:120px;flex-shrink:0;position:relative;padding-top:44px;
}
aside.tl .tl-line{
    position:sticky;top:80px;padding-left:20px;
    border-left:2px solid var(--gll);
}
aside.tl a{
    display:flex;align-items:center;gap:8px;text-decoration:none;
    color:var(--t3);font-size:.75em;font-weight:500;padding:6px 0;
    position:relative;transition:color .2s;
}
aside.tl a::before{
    content:"";position:absolute;left:-26px;top:50%;transform:translateY(-50%);
    width:10px;height:10px;border-radius:50%;background:#fff;
    border:2px solid var(--gll);transition:all .25s;
}
aside.tl a:hover{color:var(--g)}
aside.tl a:hover::before{border-color:var(--gl);background:var(--gll)}
aside.tl a.on{color:var(--g);font-weight:700}
aside.tl a.on::before{background:var(--g);border-color:var(--g);box-shadow:0 0 0 4px var(--gll)}
aside.tl a .tl-lbl{opacity:0;transition:opacity .2s}
aside.tl a:hover .tl-lbl{opacity:1}
aside.tl a.on .tl-lbl{opacity:1}

/* ── Date Section ── */
.ds{margin-bottom:52px}
.ds h2{
    font-size:1em;font-weight:600;color:var(--t2);padding-bottom:12px;
    border-bottom:1px solid var(--br);margin-bottom:4px;position:sticky;
    top:0;background:var(--bg);z-index:2;display:flex;align-items:center;gap:10px;
}
.ds h2 .d-dot{width:8px;height:8px;border-radius:50%;background:var(--gl);flex-shrink:0}

/* ── News Card ── */
.news-list{list-style:none}
.ni{display:flex;align-items:flex-start;gap:12px;border-radius:var(--rh);
    transition:background .12s;margin-bottom:0}
.ni:hover{background:var(--glg)}
.ni .src{
    flex-shrink:0;display:inline-block;padding:2px 10px;border-radius:5px;
    font-size:.7em;font-weight:600;color:#fff;line-height:1.7;white-space:nowrap;
    letter-spacing:.01em;margin-top:10px;
}
.ni .nt{
    flex:1;min-width:0;padding:10px 12px;cursor:pointer;
    font-size:.95em;font-weight:510;color:var(--tx);
    transition:color .15s;border-radius:var(--rh);
}
.ni .nt:hover{color:var(--g)}

/* ── Modal ── */
.modal-overlay{
    position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.32);
    backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
    display:flex;align-items:center;justify-content:center;padding:24px;
    animation:mo .2s ease;
}
.modal-overlay.hidden{display:none}
.modal{
    background:#fff;border-radius:20px;max-width:660px;width:100%;max-height:85vh;
    overflow-y:auto;box-shadow:0 25px 80px rgba(0,0,0,.15);
    animation:ms .3s ease;
}
.modal-header{
    padding:32px 32px 0;display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
}
.modal-header h3{font-size:1.3em;font-weight:700;color:var(--tx);line-height:1.4;flex:1}
.modal-close{
    flex-shrink:0;width:32px;height:32px;border-radius:50%;border:none;
    background:var(--bg2);color:var(--t3);font-size:1.2em;cursor:pointer;
    display:flex;align-items:center;justify-content:center;transition:all .15s;
}
.modal-close:hover{background:#e5e7eb;color:var(--tx)}
.modal-body{padding:24px 32px 32px}
.modal-body .m-src{display:inline-block;padding:3px 12px;border-radius:5px;
    font-size:.75em;font-weight:600;color:#fff;margin-bottom:20px}
.modal-body .m-sum{font-size:.95em;color:var(--t2);line-height:1.8;white-space:pre-wrap}
.modal-body .m-link{
    display:inline-flex;align-items:center;gap:8px;margin-top:24px;
    color:var(--g);text-decoration:none;font-weight:600;font-size:.95em;
    padding:10px 22px;border-radius:24px;background:var(--glg);transition:all .15s;
}
.modal-body .m-link:hover{background:var(--gll);color:var(--gd)}
.modal-body .m-link::after{content:"→";transition:transform .2s}
.modal-body .m-link:hover::after{transform:translateX(3px)}
@keyframes mo{from{opacity:0}to{opacity:1}}
@keyframes ms{from{opacity:0;transform:translateY(20px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}

/* ── Empty ── */
.empty{text-align:center;padding:100px 24px;color:var(--t3)}
.empty .ic{font-size:3em;margin-bottom:16px}
.empty p{font-size:1em}

/* ── Footer ── */
footer{
    text-align:center;padding:28px 20px;font-size:.78em;color:var(--t3);
    border-top:1px solid var(--br);margin-top:auto;background:var(--bg2);
}
footer p+p{margin-top:4px}
footer .er{color:#dc2626;font-size:.85em;margin-top:3px}
footer a{color:var(--g);text-decoration:none}
footer a:hover{text-decoration:underline}

/* ── Lang visibility (class-based, works 100%) ── */
html.lang-zh [data-lang]{display:none}
html.lang-zh [data-lang="zh"]{display:revert}
html.lang-en [data-lang]{display:none}
html.lang-en [data-lang="en"]{display:revert}

/* ── Responsive ── */
@media(max-width:900px){
    aside.tl{display:none}
}
@media(max-width:640px){
    header{padding:48px 18px 32px}
    header h1{font-size:1.8em}
    main{padding:24px 0 36px}
    .stats{gap:20px;font-size:.8em}
    .ni dt summary{font-size:.9em;padding:10px 8px}
    .ni .src{font-size:.64em;padding:1px 7px;margin-top:10px}
    .ni{gap:6px}
    .ni dt .nc{font-size:.84em;padding:4px 8px 12px}
}
"""

JS = r"""
<script>
(function(){
    var H=document.documentElement;
    var btns=document.querySelectorAll('.lang-sw button');

    // ── Lang ──
    var L=localStorage.getItem('ai-news-lang')||'zh';
    function setLang(l){
        H.className='lang-'+l;
        localStorage.setItem('ai-news-lang',l);
        btns.forEach(function(b){b.classList.toggle('on',b.dataset.lang===l)});
    }
    btns.forEach(function(b){b.addEventListener('click',function(){setLang(this.dataset.lang)})});
    setLang(L);

    // ── Timeline ──
    var links=document.querySelectorAll('.tl a');
    if(links.length){
        var sec=[];
        links.forEach(function(a){
            var el=document.getElementById(a.getAttribute('href').slice(1));
            if(el) sec.push({el:el,a:a});
        });
        function up(){
            var sy=window.scrollY+100,ac=null;
            sec.forEach(function(s){if(s.el.offsetTop<=sy) ac=s.a;});
            links.forEach(function(a){a.classList.remove('on')});
            if(ac) ac.classList.add('on');
        }
        window.addEventListener('scroll',up,{passive:true});up();
    }

    // ── Modal ──
    var overlay=document.getElementById('modal-overlay');
    var mTitle=document.getElementById('modal-title-zh');
    var mTitleEn=document.getElementById('modal-title-en');
    var mSrc=document.getElementById('modal-src');
    var mSumZh=document.getElementById('modal-summary-zh');
    var mSumEn=document.getElementById('modal-summary-en');
    var mLink=document.getElementById('modal-link');
    var mRmZh=document.getElementById('modal-rm-zh');
    var mRmEn=document.getElementById('modal-rm-en');

    function openModal(data){
        mTitle.textContent=data.zh_title||'';
        mTitleEn.textContent=data.en_title||'';
        mSrc.textContent=data.source||'';
        mSrc.style.background=data.color||'#999';
        mSumZh.textContent=data.zh_summary||'';
        mSumEn.textContent=data.en_summary||'';
        mLink.href=data.link||'#';
        // Show/hide summary sections
        if(data.zh_summary||data.en_summary){
            mSumZh.style.display='';mSumEn.style.display='';
        }else{
            mSumZh.style.display='none';mSumEn.style.display='none';
        }
        // Show/hide read-more
        if(data.link&&data.link!=='#'){
            mRmZh.style.display='';mRmEn.style.display='';
        }else{
            mRmZh.style.display='none';mRmEn.style.display='none';
        }
        overlay.classList.remove('hidden');
        document.body.style.overflow='hidden';
    }
    window.closeModal=function(){
        overlay.classList.add('hidden');
        document.body.style.overflow='';
    };
    overlay.addEventListener('click',function(e){if(e.target===overlay)closeModal();});
    document.addEventListener('keydown',function(e){if(e.key==='Escape')closeModal();});

    // Attach to news items
    document.querySelectorAll('.ni .nt').forEach(function(el){
        el.addEventListener('click',function(){
            openModal({
                zh_title:el.getAttribute('data-zh-title')||'',
                en_title:el.getAttribute('data-en-title')||'',
                zh_summary:el.getAttribute('data-zh-summary')||'',
                en_summary:el.getAttribute('data-en-summary')||'',
                source:el.getAttribute('data-source')||'',
                color:el.getAttribute('data-color')||'#999',
                link:el.getAttribute('data-link')||'#'
            });
        });
    });
})();
</script>
"""

# ═══════════════════════════════════════════════════════════════════
# i18n
# ═══════════════════════════════════════════════════════════════════

I18N = {
    "zh": {
        "title": "AI 发展日报",
        "sub": "每小时自动聚合全球 AI 资讯",
        "articles": "条新闻",
        "sources_ok": "源正常",
        "last_days": "保留最近",
        "days": "天",
        "today": "今天", "yesterday": "昨天",
        "wd": ["周一","周二","周三","周四","周五","周六","周日"],
        "empty": "暂无新闻数据", "empty_hint": "请稍后刷新页面。",
        "updated": "最后更新", "tz": "北京时间",
        "sources_label": "数据来源",
        "read_more": "阅读原文",
        "powered": "由 GitHub Actions 每小时自动更新",
    },
    "en": {
        "title": "AI Daily",
        "sub": "Hourly AI news from across the web",
        "articles": "articles",
        "sources_ok": "sources OK",
        "last_days": "Last",
        "days": "days",
        "today": "Today", "yesterday": "Yesterday",
        "wd": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        "empty": "No news yet", "empty_hint": "Check back later.",
        "updated": "Last updated", "tz": "CST",
        "sources_label": "Sources",
        "read_more": "Read more",
        "powered": "Powered by GitHub Actions · Hourly updates",
    },
}


def i18n_date_label(d, lang):
    today = datetime.now(CST).date()
    t = I18N[lang]
    if d == today:
        return f"{t['today']} · {d}"
    elif d == today - timedelta(days=1):
        return f"{t['yesterday']} · {d}"
    return f"{t['wd'][d.weekday()]} · {d}"


# ═══════════════════════════════════════════════════════════════════
# HTML 生成
# ═══════════════════════════════════════════════════════════════════

def generate_html(entries_by_date, update_time, errors):
    total = sum(len(v) for v in entries_by_date.values())
    sc = len(RSS_SOURCES)
    ok = sc - len(errors)

    # ── Timeline ──
    tl_html = ""
    ds_html = ""

    if entries_by_date:
        for d, entries in sorted(entries_by_date.items(), reverse=True):
            did = f"d{d.isoformat()}"
            sl = f"{d.month}/{d.day}"
            tl_html += f'<a href="#{did}"><span class="tl-lbl">{sl}</span></a>\n'

            label_zh = html_module.escape(i18n_date_label(d, "zh"))
            label_en = html_module.escape(i18n_date_label(d, "en"))

            items = ""
            for e in entries:
                badge = (
                    f'<span class="src" style="background:{e["source_color"]}">'
                    f'{html_module.escape(e["source_name"])}</span>'
                )
                zh_title = html_module.escape(e.get("zh_title") or e.get("title", ""))
                en_title = html_module.escape(e.get("en_title") or e.get("title", ""))
                zh_sum = html_module.escape(e.get("zh_summary") or e.get("summary", ""))
                en_sum = html_module.escape(e.get("en_summary") or e.get("summary", ""))
                link = html_module.escape(e.get("link", "#"))
                color = html_module.escape(e.get("source_color", "#999"))
                src_name = html_module.escape(e.get("source_name", ""))

                items += (
                    f'<li class="ni">{badge}'
                    f'<div class="nt"'
                    f' data-zh-title="{zh_title}"'
                    f' data-en-title="{en_title}"'
                    f' data-zh-summary="{zh_sum}"'
                    f' data-en-summary="{en_sum}"'
                    f' data-source="{src_name}"'
                    f' data-color="{color}"'
                    f' data-link="{link}">'
                    f'<span data-lang="zh">{zh_title}</span>'
                    f'<span data-lang="en">{en_title}</span>'
                    f'</div></li>\n'
                )

            ds_html += (
                f'<section class="ds" id="{did}">\n'
                f'<h2><span class="d-dot"></span>'
                f'<span data-lang="zh">{label_zh}</span>'
                f'<span data-lang="en">{label_en}</span></h2>\n'
                f'<ul class="news-list">\n{items}</ul>\n</section>\n'
            )
    else:
        ds_html = (
            f'<div class="empty"><div class="ic">📭</div>'
            f'<p data-lang="zh">{I18N["zh"]["empty"]}</p>'
            f'<p data-lang="en">{I18N["en"]["empty"]}</p>'
            f'<p data-lang="zh" style="font-size:.85em;margin-top:6px">{I18N["zh"]["empty_hint"]}</p>'
            f'<p data-lang="en" style="font-size:.85em;margin-top:6px">{I18N["en"]["empty_hint"]}</p>'
            f'</div>'
        )

    # ── Errors ──
    err_html = ""
    if errors:
        for sn, em in errors:
            err_html += f'<p class="er">⚠️ {html_module.escape(sn)}: {html_module.escape(em)}</p>\n'

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    gl = f"https://github.com/{repo}" if repo else "#"
    src_list = ", ".join(html_module.escape(s["name"]) for s in RSS_SOURCES)

    return f"""<!DOCTYPE html>
<html class="lang-zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="AI 发展日报 · AI Daily — 每小时自动聚合全球 AI 资讯">
<meta name="color-scheme" content="light">
<title>🧠 AI 发展日报 · AI Daily</title>
<style>{CSS}</style>
</head>
<body>

<header>
<div class="lang-row">
<div class="lang-sw">
<button data-lang="zh">中文</button>
<button data-lang="en">English</button>
</div>
</div>
<h1 data-lang="zh">🧠 <span class="grad">AI 发展日报</span></h1>
<h1 data-lang="en">🧠 <span class="grad">AI Daily</span></h1>
<p class="sub" data-lang="zh">{html_module.escape(I18N["zh"]["sub"])}</p>
<p class="sub" data-lang="en">{html_module.escape(I18N["en"]["sub"])}</p>
</header>

<div class="stats">
<span>📰 <span class="val">{total}</span> <span data-lang="zh">{I18N["zh"]["articles"]}</span><span data-lang="en">{I18N["en"]["articles"]}</span></span>
<span>📡 <span class="val">{ok}/{sc}</span> <span data-lang="zh">{I18N["zh"]["sources_ok"]}</span><span data-lang="en">{I18N["en"]["sources_ok"]}</span></span>
<span>📆 <span data-lang="zh">{I18N["zh"]["last_days"]}</span><span data-lang="en">{I18N["en"]["last_days"]}</span> <span class="val">{MAX_DAYS}</span> <span data-lang="zh">{I18N["zh"]["days"]}</span><span data-lang="en">{I18N["en"]["days"]}</span></span>
</div>

<main-wrap>
{f'<aside class="tl"><nav class="tl-line">{tl_html}</nav></aside>' if tl_html else ''}

<main>
{ds_html}
</main>
</main-wrap>

<footer>
<p>🕐 <span data-lang="zh">{I18N["zh"]["updated"]}：{html_module.escape(update_time)}（{I18N["zh"]["tz"]}）</span><span data-lang="en">{I18N["en"]["updated"]}: {html_module.escape(update_time)} ({I18N["en"]["tz"]})</span></p>
<p><span data-lang="zh">{I18N["zh"]["sources_label"]}：{src_list}</span><span data-lang="en">{I18N["en"]["sources_label"]}: {src_list}</span></p>
{err_html}
<p style="margin-top:8px"><span data-lang="zh">{I18N["zh"]["powered"]}</span><span data-lang="en">{I18N["en"]["powered"]}</span> · <a href="{gl}">GitHub</a></p>
</footer>

<!-- Modal -->
<div id="modal-overlay" class="modal-overlay hidden" role="dialog" aria-modal="true">
<div class="modal">
<div class="modal-header">
<h3 id="modal-title-zh" data-lang="zh"></h3>
<h3 id="modal-title-en" data-lang="en"></h3>
<button class="modal-close" onclick="closeModal()" aria-label="Close">✕</button>
</div>
<div class="modal-body">
<span id="modal-src" class="m-src"></span>
<p id="modal-summary-zh" class="m-sum" data-lang="zh"></p>
<p id="modal-summary-en" class="m-sum" data-lang="en"></p>
<a id="modal-link" class="m-link" href="#" target="_blank" rel="noopener">
<span id="modal-rm-zh" data-lang="zh">阅读原文</span>
<span id="modal-rm-en" data-lang="en">Read more</span>
</a>
</div>
</div>
</div>

{JS}
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════════════════════════════════

def main():
    output_path = OUTPUT_FILE
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-o", "--output") and i + 1 < len(args):
            output_path = args[i + 1]; i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__); return
        else:
            print(f"未知参数: {args[i]}"); print(__doc__); sys.exit(1)

    print("=" * 60)
    print("🧠 AI 新闻聚合器")
    print(f"   运行时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print(f"   数据源数量: {len(RSS_SOURCES)}")
    print(f"   保留天数: {MAX_DAYS}")
    print("=" * 60)

    # ── 抓取 ──
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
    dup = len(all_entries) - len(unique_entries)
    if dup:
        print(f"\n🔍 去重: 移除 {dup} 条重复条目")

    # ── 翻译 ──
    unique_entries = translate_entries(unique_entries)

    # ── 按日期分组（北京时间） ──
    cutoff_date = datetime.now(CST).date() - timedelta(days=MAX_DAYS)
    entries_by_date = defaultdict(list)
    for entry in unique_entries:
        d = beijing_date(entry["published_dt"])
        if d >= cutoff_date:
            entries_by_date[d].append(entry)
    for d in entries_by_date:
        entries_by_date[d].sort(key=lambda e: e["published_dt"], reverse=True)

    # ── 生成 HTML ──
    print(f"\n📝 生成 HTML...")
    update_time = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    html_content = generate_html(entries_by_date, update_time, fetch_errors)

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # ── 摘要 ──
    total = sum(len(v) for v in entries_by_date.values())
    ok_sources = len(RSS_SOURCES) - len(fetch_errors)
    print(f"\n{'=' * 60}")
    print(f"✅ 完成！")
    print(f"   新闻总数: {total} 条  成功源: {ok_sources}/{len(RSS_SOURCES)}")
    if fetch_errors:
        print(f"\n⚠️  以下源抓取失败:")
        for name, msg in fetch_errors:
            print(f"   - {name}: {msg}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
