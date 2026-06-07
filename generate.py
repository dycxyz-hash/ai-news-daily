#!/usr/bin/env python3
"""AI 新闻聚合器 — 抓取 RSS → 双语静态页面。每小时更新。"""

import feedparser, requests, html as H, sys, os, re, time
from datetime import datetime, timedelta, timezone, date
from calendar import timegm
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ═══ 配置 ═══
CST = timezone(timedelta(hours=8))
MAX_DAYS, REQUEST_TIMEOUT, OUTPUT = 7, 10, "index.html"

RSS = [
    {"name":"OpenAI","url":"https://openai.com/blog/rss.xml","color":"#10a37f"},
    {"name":"Hugging Face","url":"https://huggingface.co/blog/feed.xml","color":"#ff9d00"},
    {"name":"Google AI","url":"https://blog.google/technology/ai/rss/","color":"#4285f4"},
    {"name":"TechCrunch","url":"https://techcrunch.com/category/artificial-intelligence/feed/","color":"#0a960a"},
    {"name":"ArXiv AI","url":"https://export.arxiv.org/rss/cs.AI","color":"#b31b1b"},
    {"name":"IT之家","url":"https://www.ithome.com/rss/","color":"#d50000",
     "keywords":["AI","人工智能","大模型","GPT","LLM","智能","机器人","算力","芯片","NVIDIA",
                  "英伟达","OpenAI","ChatGPT","机器学习","深度学习","自动驾驶","Agent","智谱",
                  "模型","算法","数据中心","神经网络","GPU","Copilot","Gemini","Claude","DeepSeek"]},
    {"name":"36氪","url":"https://36kr.com/feed","color":"#3370ff",
     "keywords":["AI","人工智能","大模型","GPT","LLM","智能","机器人","算力","芯片","NVIDIA",
                  "英伟达","OpenAI","ChatGPT","机器学习","深度学习","自动驾驶","Agent","Token","数字人"]},
    {"name":"量子位","url":"https://www.qbitai.com/feed","color":"#6c5ce7"},
]

# ═══ RSS 抓取 ═══
def parse_entry_date(entry, src):
    for a in ("published_parsed","updated_parsed"):
        v = getattr(entry,a,None)
        if v:
            try: return datetime.fromtimestamp(timegm(v),tz=timezone.utc), None
            except: pass
    ps = getattr(entry,"published","") or ""
    if ps:
        for f in ("%a, %d %b %Y %H:%M:%S %z","%a, %d %b %Y %H:%M:%S %Z",
                  "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ","%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(ps.strip(),f)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                return dt, None
            except: pass
    return datetime.now(timezone.utc), "无法解析日期"

def fetch_feed(src):
    n,u,c = src["name"], src["url"], src["color"]
    try:
        r = requests.get(u,timeout=REQUEST_TIMEOUT,headers={
            "User-Agent":"Mozilla/5.0 (compatible; AI-News/1.0)",
            "Accept":"application/rss+xml, application/xml, text/xml, */*"})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        if feed.bozo and not feed.entries:
            try: r.encoding="utf-8"; feed=feedparser.parse(r.text)
            except: pass
        if feed.bozo and not feed.entries:
            return n,[],f"RSS解析失败: {getattr(feed.bozo_exception,'getMessage',lambda:'?')()}"
        entries=[]
        for e in feed.entries:
            t=getattr(e,"title","").strip(); lk=getattr(e,"link","").strip()
            if not t: continue
            t=re.sub(r"<[^>]+>","",t); t=H.unescape(t)
            kw=src.get("keywords")
            if kw and not any(k.lower() in t.lower() for k in kw): continue
            sm=""
            for a in ("summary","description"):
                v=getattr(e,a,None)
                if v:
                    raw=v[0].get("value","") if isinstance(v,list) else str(v)
                    raw=re.sub(r"<[^>]+>","",raw); sm=H.unescape(raw).strip()
                    break
            pd,de=parse_entry_date(e,n)
            entries.append({"title":t,"link":lk or "#","summary":sm,
                           "published_dt":pd,"source_name":n,"source_color":c,"date_error":de})
        s="✓" if entries else "(空)"
        print(f"  [{s}] {n}: {len(entries)} 条")
        return n,entries,None
    except requests.exceptions.Timeout: return n,[],f"超时({REQUEST_TIMEOUT}s)"
    except requests.exceptions.ConnectionError as e: return n,[],f"连接失败:{str(e)[:80]}"
    except requests.exceptions.HTTPError as e:
        return n,[],f"HTTP {e.response.status_code if e.response else '?'}"
    except Exception as e: return n,[],f"错误:{str(e)[:150]}"

def beijing_date(dt): return dt.astimezone(CST).date()

def nt(t): return re.sub(r"\s+"," ",t.strip().lower())

# ═══ i18n ═══
I18N={
    "zh":{"title":"AI 发展日报","sub":"每小时聚合 · 全球 AI 资讯",
          "articles":"条新闻","sources_ok":"源正常","last_days":"最近","days":"天",
          "today":"今天","yesterday":"昨天",
          "wd":["周一","周二","周三","周四","周五","周六","周日"],
          "empty":"暂无新闻","empty_hint":"稍后刷新页面",
          "updated":"最后更新","tz":"北京时间","sources_label":"数据来源",
          "read_more":"阅读原文","powered":"GitHub Actions 每小时自动更新"},
    "en":{"title":"AI Daily","sub":"Hourly AI news from across the web",
          "articles":"articles","sources_ok":"sources OK","last_days":"Last","days":"days",
          "today":"Today","yesterday":"Yesterday",
          "wd":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
          "empty":"No news","empty_hint":"Check back later",
          "updated":"Last updated","tz":"CST","sources_label":"Sources",
          "read_more":"Read more","powered":"Powered by GitHub Actions · Hourly"},
}

def dl(d,l):
    today=datetime.now(CST).date(); t=I18N[l]
    if d==today: return f"{t['today']} · {d}"
    elif d==today-timedelta(days=1): return f"{t['yesterday']} · {d}"
    return f"{t['wd'][d.weekday()]} · {d}"

# ═══ CSS ═══
CSS=r"""
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-font-smoothing:antialiased}
:root{
    --g:#059669;--gd:#047857;--gl:#34d399;--gll:#d1fae5;--glg:#ecfdf5;
    --tx:#0f172a;--t2:#475569;--t3:#94a3b8;
    --bg:#fff;--bg2:#f8fafc;--br:#e2e8f0;
}
body{
    font-family:"SF Pro Display",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--tx);line-height:1.6;min-height:100vh;
    display:flex;flex-direction:column;font-weight:420;
}

/* ── Header ── */
header{
    position:relative;padding:80px 24px 56px;text-align:center;
    background:linear-gradient(170deg,#022c22 0%,#064e3b 30%,#065f46 60%,#047857 100%);
    color:#fff;overflow:hidden;
}
header::before{
    content:"";position:absolute;inset:0;
    background:radial-gradient(ellipse 80% 60% at 50% 0%,rgba(52,211,153,.12) 0%,transparent 60%),
              radial-gradient(ellipse 40% 50% at 20% 100%,rgba(5,150,105,.15) 0%,transparent 50%),
              radial-gradient(ellipse 30% 40% at 80% 80%,rgba(16,185,129,.1) 0%,transparent 50%);
    pointer-events:none
}
header .topbar{
    display:flex;justify-content:flex-end;max-width:760px;margin:0 auto 28px;position:relative;z-index:1
}
header .ls{
    display:inline-flex;gap:0;background:rgba(255,255,255,.1);border-radius:24px;
    padding:3px;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    border:1px solid rgba(255,255,255,.12)
}
header .ls button{
    border:none;background:transparent;color:rgba(255,255,255,.65);
    padding:7px 18px;border-radius:22px;cursor:pointer;font-size:.8em;
    font-weight:550;transition:all .25s;font-family:inherit;letter-spacing:.01em
}
header .ls button.on{background:#fff;color:#047857;box-shadow:0 2px 8px rgba(0,0,0,.15)}
header .ls button:hover:not(.on){color:#fff;background:rgba(255,255,255,.08)}
header h1{font-size:2.8em;font-weight:800;letter-spacing:-.025em;position:relative;z-index:1;line-height:1.2}
header h1 .grad{
    background:linear-gradient(135deg,#fff 0%,#a7f3d0 50%,#6ee7b7 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text
}
header .sub{margin-top:12px;font-size:1em;opacity:.55;font-weight:400;position:relative;z-index:1}

/* ── Stats ── */
.stats{
    display:flex;justify-content:center;gap:56px;flex-wrap:wrap;
    padding:18px 20px;background:var(--bg2);border-bottom:1px solid var(--br);
    font-size:.84em;color:var(--t3);
}
.stats .val{font-weight:700;color:var(--g);font-size:1.12em;font-variant-numeric:tabular-nums}

/* ── Layout ── */
.wrap{display:flex;max-width:1120px;width:100%;margin:0 auto;padding:0 20px;flex:1}
main{flex:1;max-width:740px;width:100%;margin:0 auto;padding:44px 0 72px}

/* ── Timeline ── */
aside.tl{width:130px;flex-shrink:0;padding-top:48px}
aside.tl nav{position:sticky;top:80px;padding-left:24px;border-left:2px solid var(--gll)}
aside.tl a{
    display:flex;align-items:center;gap:10px;text-decoration:none;
    color:var(--t3);font-size:.72em;font-weight:550;padding:7px 0;
    position:relative;transition:color .2s
}
aside.tl a::before{
    content:"";position:absolute;left:-30px;top:50%;transform:translateY(-50%);
    width:10px;height:10px;border-radius:50%;background:var(--bg);
    border:2px solid var(--gll);transition:all .3s cubic-bezier(.4,0,.2,1)
}
aside.tl a:hover{color:var(--g)}
aside.tl a:hover::before{border-color:var(--gl);background:var(--gll);box-shadow:0 0 0 6px var(--gll)}
aside.tl a.on{color:var(--g);font-weight:700}
aside.tl a.on::before{
    background:var(--g);border-color:var(--g);
    box-shadow:0 0 0 6px var(--gll);width:12px;height:12px;left:-31px
}
aside.tl a .tl-lbl{opacity:0;transition:opacity .25s;font-variant-numeric:tabular-nums}
aside.tl a:hover .tl-lbl,aside.tl a.on .tl-lbl{opacity:1}

/* ── Date section ── */
.ds{margin-bottom:56px;scroll-margin-top:60px}
.ds h2{
    font-size:.95em;font-weight:650;color:var(--t2);padding-bottom:14px;
    border-bottom:1px solid var(--br);margin-bottom:6px;position:sticky;
    top:0;background:var(--bg);z-index:2;display:flex;align-items:center;gap:10px;
}
.ds h2 .d-dot{width:7px;height:7px;border-radius:50%;background:var(--gl);flex-shrink:0}

/* ── News items ── */
.news-list{list-style:none}
.ni{
    display:flex;align-items:flex-start;gap:12px;border-radius:10px;
    transition:background .15s,transform .15s;margin-bottom:0;
}
.ni:hover{background:var(--glg);transform:translateX(2px)}
.ni .src{
    flex-shrink:0;padding:3px 10px;border-radius:5px;
    font-size:.68em;font-weight:650;color:#fff;line-height:1.7;
    white-space:nowrap;letter-spacing:.02em;margin-top:11px;
}
.ni .ntc{
    flex:1;min-width:0;padding:11px 14px;cursor:pointer;
    font-size:.95em;font-weight:480;color:var(--tx);
    transition:color .15s;border-radius:10px;
}
.ni:hover .ntc{color:var(--g)}
.ni .ntc::after{content:"›";float:right;font-size:1.2em;color:var(--t3);font-weight:300;
    transition:transform .2s,color .2s;margin-left:8px;line-height:1.4}
.ni:hover .ntc::after{color:var(--g);transform:translateX(3px)}

/* ── Modal ── */
.mo{
    position:fixed;inset:0;z-index:9999;background:rgba(2,44,34,.45);
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    display:flex;align-items:center;justify-content:center;padding:28px;
    animation:moin .25s ease
}
.mo.hi{display:none}
.md{
    background:var(--bg);border-radius:24px;max-width:680px;width:100%;max-height:85vh;
    overflow-y:auto;box-shadow:0 32px 100px rgba(0,0,0,.2),0 0 0 1px rgba(0,0,0,.04);
    animation:mdin .35s cubic-bezier(.16,1,.3,1)
}
.md-h{padding:36px 36px 0;display:flex;align-items:flex-start;gap:16px}
.md-h h3{font-size:1.25em;font-weight:700;color:var(--tx);line-height:1.45;flex:1}
.md-x{
    flex-shrink:0;width:36px;height:36px;border-radius:50%;border:none;
    background:var(--bg2);color:var(--t3);font-size:1.1em;cursor:pointer;
    display:flex;align-items:center;justify-content:center;transition:all .2s
}
.md-x:hover{background:#e2e8f0;color:var(--tx);transform:rotate(90deg)}
.md-b{padding:20px 36px 40px}
.md-b .m-src{display:inline-block;padding:3px 14px;border-radius:6px;
    font-size:.72em;font-weight:650;color:#fff;margin-bottom:22px;letter-spacing:.02em}
.md-b .m-sum{font-size:.92em;color:var(--t2);line-height:1.85;white-space:pre-wrap}
.md-b .rl{
    display:inline-flex;align-items:center;gap:8px;margin-top:28px;
    color:#fff;text-decoration:none;font-weight:600;font-size:.9em;
    padding:11px 24px;border-radius:28px;background:var(--g);
    transition:all .2s;box-shadow:0 4px 14px rgba(5,150,105,.3)
}
.md-b .rl:hover{background:var(--gd);box-shadow:0 6px 20px rgba(5,150,105,.4);transform:translateY(-1px)}
.md-b .rl::after{content:"→";transition:transform .2s}
.md-b .rl:hover::after{transform:translateX(4px)}
@keyframes moin{from{opacity:0}to{opacity:1}}
@keyframes mdin{from{opacity:0;transform:translateY(24px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}

/* ── Empty ── */
.empty{text-align:center;padding:120px 24px;color:var(--t3)}
.empty .ic{font-size:3.5em;margin-bottom:18px}
.empty p{font-size:1em}

/* ── Footer ── */
footer{
    text-align:center;padding:32px 20px;font-size:.76em;color:var(--t3);
    border-top:1px solid var(--br);margin-top:auto;background:var(--bg2)
}
footer p+p{margin-top:5px}
footer .er{color:#dc2626;font-size:.82em;margin-top:4px}
footer a{color:var(--g);text-decoration:none;font-weight:550}
footer a:hover{text-decoration:underline}

/* ── Language visibility ── */
html.lang-zh .la-zh{display:revert}
html.lang-zh .la-en{display:none!important}
html.lang-en .la-en{display:revert}
html.lang-en .la-zh{display:none!important}

/* ── Responsive ── */
@media(max-width:920px){aside.tl{display:none}}
@media(max-width:640px){
    header{padding:56px 18px 40px}
    header h1{font-size:1.9em}
    header .ls button{padding:6px 14px;font-size:.76em}
    .wrap{padding:0 14px}
    main{padding:28px 0 44px}
    .stats{gap:24px;font-size:.78em}
    .ni .ntc{font-size:.9em;padding:10px 8px}
    .ni .src{font-size:.63em;padding:2px 8px;margin-top:10px}
    .ni{gap:6px}
    .md{padding:0;border-radius:18px}
    .md-h{padding:28px 24px 0}
    .md-b{padding:16px 24px 32px}
    .ds{margin-bottom:40px}
}
"""

# ═══ JS ═══
JS=r"""
<script>
(function(){
var H=document.documentElement,btns=document.querySelectorAll('.ls button');
var L=localStorage.getItem('ai-news-lang')||'zh';
function sl(l){
    H.className='lang-'+l;
    localStorage.setItem('ai-news-lang',l);
    btns.forEach(function(b){b.classList.toggle('on',b.dataset.lang===l)});
}
btns.forEach(function(b){b.addEventListener('click',function(){sl(this.dataset.lang)})});
sl(L);

// Timeline scroll-spy
var tls=document.querySelectorAll('.tl a');
if(tls.length){
    var sec=[];
    tls.forEach(function(a){
        var el=document.getElementById(a.getAttribute('href').slice(1));
        if(el)sec.push({el:el,a:a});
    });
    function up(){
        var sy=window.scrollY+120,ac=null;
        sec.forEach(function(s){if(s.el.offsetTop<=sy)ac=s.a;});
        tls.forEach(function(a){a.classList.remove('on')});
        if(ac)ac.classList.add('on');
    }
    window.addEventListener('scroll',up,{passive:true});up();
}

// Modal
var ov=document.getElementById('mo');
var mTz=document.getElementById('mt-zh'),mTe=document.getElementById('mt-en');
var mSz=document.getElementById('ms-zh'),mSe=document.getElementById('ms-en');
var mSrc=document.getElementById('msrc'),mLk=document.getElementById('mlk');
function om(d){
    mTz.textContent=d.zt||'';mTe.textContent=d.et||'';
    mSrc.textContent=d.s||'';mSrc.style.background=d.c||'#999';
    if(d.zs){mSz.style.display='';mSz.textContent=d.zs}else{mSz.style.display='none'}
    if(d.es){mSe.style.display='';mSe.textContent=d.es}else{mSe.style.display='none'}
    if(d.l&&d.l!=='#'){mLk.style.display='';mLk.href=d.l}else{mLk.style.display='none'}
    ov.classList.remove('hi');document.body.style.overflow='hidden';
}
window.clm=function(){ov.classList.add('hi');document.body.style.overflow=''};
ov.addEventListener('click',function(e){if(e.target===ov)clm()});
document.addEventListener('keydown',function(e){if(e.key==='Escape')clm()});
document.querySelectorAll('.ntc').forEach(function(el){
    el.addEventListener('click',function(){
        om({zt:el.dataset.zt,et:el.dataset.et,zs:el.dataset.zs,es:el.dataset.es,
            s:el.dataset.source,c:el.dataset.color,l:el.dataset.link});
    });
});
})();
</script>
"""

# ═══ HTML ═══
def gen_html(ebd, ut, errors):
    total=sum(len(v) for v in ebd.values())
    sc=len(RSS); ok=sc-len(errors)
    tl=""; ds=""

    if ebd:
        for d,entries in sorted(ebd.items(),reverse=True):
            did=f"d{d.isoformat()}"
            sl=f"{d.month}/{d.day}"
            tl+=f'<a href="#{did}"><span class="tl-lbl">{sl}</span></a>\n'
            lbl_zh=H.escape(dl(d,"zh")); lbl_en=H.escape(dl(d,"en"))
            items=""
            for e in entries:
                badge=(f'<span class="src" style="background:{e["source_color"]}">'
                       f'{H.escape(e["source_name"])}</span>')
                zt=H.escape(e.get("zh_title")or e.get("title",""))
                et=H.escape(e.get("en_title")or e.get("title",""))
                zs=H.escape(e.get("zh_summary")or e.get("summary",""))
                es_=H.escape(e.get("en_summary")or e.get("summary",""))
                lk_=H.escape(e.get("link","#"))
                co_=H.escape(e.get("source_color","#999"))
                sn_=H.escape(e.get("source_name",""))
                items+=(f'<li class="ni">{badge}'
                        f'<div class="ntc la-zh" data-zt="{zt}" data-et="{et}" '
                        f'data-zs="{zs}" data-es="{es_}" data-source="{sn_}" '
                        f'data-color="{co_}" data-link="{lk_}">{zt}</div>'
                        f'<div class="ntc la-en" data-zt="{zt}" data-et="{et}" '
                        f'data-zs="{zs}" data-es="{es_}" data-source="{sn_}" '
                        f'data-color="{co_}" data-link="{lk_}">{et}</div></li>\n')
            ds+=(f'<section class="ds" id="{did}">'
                 f'<h2><span class="d-dot"></span>'
                 f'<span class="la-zh">{lbl_zh}</span>'
                 f'<span class="la-en">{lbl_en}</span></h2>'
                 f'<ul class="news-list">{items}</ul></section>\n')
    else:
        ds=(f'<div class="empty"><div class="ic">📭</div>'
            f'<p class="la-zh">{I18N["zh"]["empty"]}</p>'
            f'<p class="la-en">{I18N["en"]["empty"]}</p></div>')

    err_html=""
    if errors:
        for sn,em in errors: err_html+=f'<p class="er">⚠ {H.escape(sn)}: {H.escape(em)}</p>\n'

    repo=os.environ.get("GITHUB_REPOSITORY","")
    gl=f"https://github.com/{repo}" if repo else "#"
    slist=", ".join(H.escape(s["name"]) for s in RSS)

    return f"""<!DOCTYPE html>
<html class="lang-zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="AI 发展日报 · AI Daily">
<meta name="color-scheme" content="light">
<title>🧠 AI 发展日报 · AI Daily</title>
<style>{CSS}</style>
</head>
<body>

<header>
<div class="topbar"><div class="ls">
<button data-lang="zh">中文</button>
<button data-lang="en">English</button>
</div></div>
<h1><span class="la-zh">🧠 <span class="grad">AI 发展日报</span></span>
<span class="la-en">🧠 <span class="grad">AI Daily</span></span></h1>
<p class="sub la-zh">{H.escape(I18N["zh"]["sub"])}</p>
<p class="sub la-en">{H.escape(I18N["en"]["sub"])}</p>
</header>

<div class="stats">
<span>📰 <span class="val">{total}</span> <span class="la-zh">{I18N["zh"]["articles"]}</span><span class="la-en">{I18N["en"]["articles"]}</span></span>
<span>📡 <span class="val">{ok}/{sc}</span> <span class="la-zh">{I18N["zh"]["sources_ok"]}</span><span class="la-en">{I18N["en"]["sources_ok"]}</span></span>
<span>📆 <span class="la-zh">{I18N["zh"]["last_days"]}</span><span class="la-en">{I18N["en"]["last_days"]}</span> <span class="val">{MAX_DAYS}</span> <span class="la-zh">{I18N["zh"]["days"]}</span><span class="la-en">{I18N["en"]["days"]}</span></span>
</div>

<div class="wrap">
{f'<aside class="tl"><nav>{tl}</nav></aside>' if tl else ''}
<main>{ds}</main>
</div>

<footer>
<p>🕐 <span class="la-zh">{I18N["zh"]["updated"]}：{H.escape(ut)}（{I18N["zh"]["tz"]}）</span><span class="la-en">{I18N["en"]["updated"]}: {H.escape(ut)} ({I18N["en"]["tz"]})</span></p>
<p><span class="la-zh">{I18N["zh"]["sources_label"]}：{slist}</span><span class="la-en">{I18N["en"]["sources_label"]}: {slist}</span></p>
{err_html}
<p style="margin-top:10px"><span class="la-zh">{I18N["zh"]["powered"]}</span><span class="la-en">{I18N["en"]["powered"]}</span> · <a href="{gl}">GitHub</a></p>
</footer>

<!-- Modal -->
<div id="mo" class="mo hi" role="dialog" aria-modal="true">
<div class="md">
<div class="md-h">
<h3 class="la-zh" id="mt-zh"></h3>
<h3 class="la-en" id="mt-en"></h3>
<button class="md-x" onclick="clm()" aria-label="Close">✕</button>
</div>
<div class="md-b">
<span id="msrc" class="m-src"></span>
<p class="m-sum la-zh" id="ms-zh"></p>
<p class="m-sum la-en" id="ms-en"></p>
<a id="mlk" class="rl" href="#" target="_blank" rel="noopener">
<span class="la-zh">阅读原文</span><span class="la-en">Read more</span></a>
</div></div></div>

{JS}
</body>
</html>"""

# ═══ Main ═══
def main():
    op=OUTPUT; args=sys.argv[1:]; i=0
    while i<len(args):
        if args[i] in ("-o","--output") and i+1<len(args): op=args[i+1]; i+=2
        elif args[i] in ("-h","--help"): print(__doc__); return
        else: print(f"未知参数: {args[i]}"); sys.exit(1)

    print("="*60)
    print("🧠 AI 新闻聚合器")
    print(f"   运行时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print(f"   数据源: {len(RSS)} | 保留: {MAX_DAYS} 天")
    print("="*60)

    print("\n📡 正在抓取 RSS 源...\n")
    all_entries=[]; fetch_errors=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures={ex.submit(fetch_feed,s):s for s in RSS}
        for f in as_completed(futures):
            try:
                n,entries,err=f.result()
                all_entries.extend(entries)
                if err: fetch_errors.append((n,err))
            except Exception as e:
                fetch_errors.append((futures[f]["name"],f"异常:{str(e)[:150]}"))

    seen=set(); unique=[]
    for e in all_entries:
        k=(nt(e["title"]),e["source_name"])
        if k not in seen: seen.add(k); unique.append(e)
    if len(all_entries)-len(unique):
        print(f"\n🔍 去重: {len(all_entries)-len(unique)} 条")

    # 初始化双语字段（原文填充，翻译留待后续接入）
    for e in unique:
        t=e.get("title",""); s=e.get("summary","")
        e["zh_title"]=t; e["en_title"]=t
        e["zh_summary"]=s; e["en_summary"]=s

    cutoff=datetime.now(CST).date()-timedelta(days=MAX_DAYS)
    ebd=defaultdict(list)
    for e in unique:
        d=beijing_date(e["published_dt"])
        if d>=cutoff: ebd[d].append(e)
    for d in ebd: ebd[d].sort(key=lambda e:e["published_dt"],reverse=True)

    print(f"\n📝 生成 HTML...")
    ut=datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    html=gen_html(ebd,ut,fetch_errors)
    d_=os.path.dirname(os.path.abspath(op))
    if d_ and not os.path.exists(d_): os.makedirs(d_,exist_ok=True)
    with open(op,"w",encoding="utf-8") as f: f.write(html)

    total=sum(len(v) for v in ebd.values())
    ok_s=len(RSS)-len(fetch_errors)
    print(f"\n{'='*60}")
    print(f"✅ 完成！{total} 条新闻 | {ok_s}/{len(RSS)} 源正常")
    if fetch_errors:
        print(f"⚠️ 失败源:")
        for n,m in fetch_errors: print(f"   - {n}: {m}")
    print(f"{'='*60}")

if __name__=="__main__": main()
