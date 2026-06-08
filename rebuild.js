// Rebuild index.html — Chinese-only, smooth transitions, proper CJK typography
const fs = require('fs');

const html = fs.readFileSync('index.html', 'utf8');

// Chinese source names to keep
const CN_SOURCES = new Set([
    '36氪','机器之心','量子位','虎嗅','雷锋网','IT之家','极客公园','品玩',
    '少数派','钛媒体','新浪科技','亿欧网','凤凰科技','界面新闻','腾讯科技',
    '网易科技','AI科技评论','OpenAI','Google AI','ArXiv AI','TechCrunch AI',
    'TechCrunch','VentureBeat AI','VentureBeat','Hugging Face','BBC Tech',
    'Ars Technica','MIT Tech Review'
]);

const sectionRegex = /<section class="ds" id="([^"]*)">\s*<h2><span class="d-dot"><\/span><span class="la-zh">([^<]*)<\/span><span class="la-en">([^<]*)<\/span><\/h2>\s*<ul class="news-list">([\s\S]*?)<\/ul>\s*<\/section>/g;
const itemRegex = /<li class="ni[^"]*">([\s\S]*?)<\/li>/g;
const dataRegex = /data-zt="([^"]*)"\s+data-et="([^"]*)"\s+data-zs="([^"]*)"\s+data-es="([^"]*)"\s+data-source="([^"]*)"\s+data-color="([^"]*)"\s+data-link="([^"]*)"/;
const srcRegex = /<span class="src" style="background:([^"]*)">([^<]*)<\/span>/;

const sections = [];
let secMatch;
while ((secMatch = sectionRegex.exec(html)) !== null) {
    const items = [];
    let itemMatch;
    while ((itemMatch = itemRegex.exec(secMatch[4])) !== null) {
        const dMatch = dataRegex.exec(itemMatch[1]);
        const sMatch = srcRegex.exec(itemMatch[1]);
        if (dMatch && sMatch) {
            items.push({
                zt: dMatch[1], et: dMatch[2], zs: dMatch[3], es: dMatch[4],
                source: dMatch[5], color: dMatch[6], link: dMatch[7],
                srcColor: sMatch[1], srcName: sMatch[2]
            });
        }
    }
    // Filter: keep articles with Chinese titles (has CJK Unified Ideographs)
    const cnItems = items.filter(item => {
        return /[一-鿿]/.test(item.zt);
    });
    sections.push({ id: secMatch[1], zh: secMatch[2], en: secMatch[3], items: cnItems });
}

// Cap at 10 per day
const MAX_PER_DAY = 10;
sections.forEach(sec => { if (sec.items.length > MAX_PER_DAY) sec.items = sec.items.slice(0, MAX_PER_DAY); });

const totalArticles = sections.reduce((s, sec) => s + sec.items.length, 0);
console.log(`Parsed ${sections.length} days, ${totalArticles} CN articles`);

const sourcesOk = (html.match(/<span>📡 <span class="val">([^<]*)<\/span>/) || ['','9/9'])[1];
const days = sections.length;
const updateTime = (html.match(/最后更新：([^<]*)（北京时间\)/) || ['',new Date().toLocaleString('zh-CN')])[1];
const updateTimeEn = (html.match(/Last updated: ([^<]*) \(CST\)/) || ['',new Date().toLocaleString('en-US')])[1];
const sourcesStr = (html.match(/数据来源：([^<]*)/) || ['',''])[1];
const sourcesStrEn = (html.match(/Sources: ([^<]*)/) || ['',''])[1];
const errors = [...html.matchAll(/<p class="er">([^<]*)<\/p>/g)].map(m => m[1]);

// ─── CSS — CJK-optimized typography + silky transitions ───
const CSS = `*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
:root{
    --accent:#007AFF;--ad:#0056CC;--al:#E8F2FF;
    --tx:#1D1D1F;--t2:#6E6E73;--t3:#AEAEB2;
    --bg:#FFFFFF;--bg2:#F5F5F7;--br:#E5E5EA;
    --sh-md:0 4px 16px rgba(0,0,0,.05),0 2px 6px rgba(0,0,0,.03);
    --sh-lg:0 12px 40px rgba(0,0,0,.08),0 4px 12px rgba(0,0,0,.04);
}
body{
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","WenQuanYi Micro Hei",sans-serif;
    background:var(--bg);color:var(--tx);line-height:1.8;min-height:100vh;
    display:flex;flex-direction:column;font-weight:400;
    text-rendering:optimizeLegibility;
    -webkit-font-feature-settings:"kern" 1,"liga" 1;
    font-feature-settings:"kern" 1,"liga" 1;
}

nav#topnav{
    position:fixed;top:0;left:0;right:0;z-index:100;height:52px;
    display:flex;align-items:center;justify-content:space-between;
    padding:0 28px;
    background:rgba(255,255,255,.68);
    backdrop-filter:blur(20px) saturate(180%);
    -webkit-backdrop-filter:blur(20px) saturate(180%);
    border-bottom:1px solid transparent;
    transition:background .5s ease,border-color .5s ease,box-shadow .5s ease;
}
nav#topnav.scrolled{background:rgba(255,255,255,.88);border-bottom-color:rgba(0,0,0,.06);box-shadow:0 1px 3px rgba(0,0,0,.04)}
nav#topnav .logo{font-size:.9em;font-weight:700;color:var(--tx);white-space:nowrap;letter-spacing:.02em}
nav#topnav .ls{display:inline-flex;gap:1px;background:rgba(0,0,0,.04);border-radius:20px;padding:2px}
nav#topnav .ls button{
    border:none;background:transparent;color:var(--t2);
    padding:5px 15px;border-radius:18px;cursor:pointer;font-size:.78em;
    font-weight:550;transition:all .3s ease;font-family:inherit;letter-spacing:.02em
}
nav#topnav .ls button.on{background:#fff;color:var(--tx);box-shadow:0 1px 3px rgba(0,0,0,.08)}
nav#topnav .ls button:hover:not(.on){color:var(--tx);background:rgba(0,0,0,.05)}

header{padding:160px 24px 80px;text-align:center;position:relative;background:var(--bg);overflow:hidden}
header::before{
    content:"";position:absolute;top:-50%;left:-50%;width:200%;height:200%;
    background:radial-gradient(ellipse 60% 50% at 50% 40%,rgba(0,122,255,.04) 0%,transparent 60%),
              radial-gradient(ellipse 40% 40% at 30% 60%,rgba(88,86,214,.03) 0%,transparent 50%),
              radial-gradient(ellipse 30% 30% at 70% 50%,rgba(175,82,222,.03) 0%,transparent 50%);
    pointer-events:none
}
header .hero-inner{transition:transform .8s cubic-bezier(.16,1,.3,1)}
header h1{font-size:clamp(2.6em,5vw,3.6em);font-weight:700;letter-spacing:.02em;line-height:1.25;position:relative}
header h1 .grad{
    background:linear-gradient(135deg,#007AFF 0%,#5856D6 45%,#AF52DE 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text
}
header .sub{font-size:1.15em;color:var(--t2);font-weight:400;margin-top:16px;letter-spacing:.04em}

.stats{
    display:flex;justify-content:center;gap:56px;flex-wrap:wrap;
    padding:22px 20px;background:var(--bg2);border-top:1px solid var(--br);border-bottom:1px solid var(--br);
    font-size:.82em;color:var(--t3);font-weight:450;letter-spacing:.03em
}
.stats .val{font-weight:700;color:var(--accent);font-size:1.1em}

.wrap{display:flex;max-width:1200px;width:100%;margin:0 auto;padding:0 24px;flex:1}
main{flex:1;max-width:900px;width:100%;margin:0 auto;padding:56px 0 100px}

aside.tl{width:80px;flex-shrink:0;padding-top:60px}
aside.tl nav{position:sticky;top:80px;padding-left:18px;border-left:1.5px solid var(--br)}
aside.tl a{
    display:flex;align-items:center;gap:8px;text-decoration:none;
    color:var(--t3);font-size:.72em;font-weight:550;padding:6px 0;
    position:relative;transition:color .35s ease;letter-spacing:.03em
}
aside.tl a::before{
    content:"";position:absolute;left:-22px;top:50%;transform:translateY(-50%);
    width:8px;height:8px;border-radius:50%;background:var(--bg);
    border:1.5px solid var(--br);transition:all .5s cubic-bezier(.16,1,.3,1)
}
aside.tl a:hover{color:var(--accent)}
aside.tl a:hover::before{border-color:var(--accent);background:var(--al);box-shadow:0 0 0 5px var(--al)}
aside.tl a.on{color:var(--accent);font-weight:700}
aside.tl a.on::before{background:var(--accent);border-color:var(--accent);box-shadow:0 0 0 5px var(--al);width:10px;height:10px;left:-23px}
aside.tl a .tl-lbl{opacity:0;transition:opacity .35s ease}
aside.tl a:hover .tl-lbl,aside.tl a.on .tl-lbl{opacity:1}

.ds{scroll-margin-top:64px;margin-bottom:56px}
.ds h2{
    font-size:.92em;font-weight:700;color:var(--t2);padding-bottom:14px;
    border-bottom:1px solid var(--br);margin-bottom:14px;
    position:sticky;top:52px;background:var(--bg);z-index:2;
    display:flex;align-items:center;gap:8px;letter-spacing:.06em;
}
.ds h2 .d-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);flex-shrink:0}

.news-list{list-style:none}
.ni{
    display:flex;align-items:flex-start;gap:14px;border-radius:14px;
    padding:18px 22px;margin-bottom:8px;
    background:var(--bg);
    transition:all .5s cubic-bezier(.16,1,.3,1);
    border:1px solid transparent;
    border-left:3px solid var(--src-color, #E5E5EA);
    position:relative;
}
.ni:hover{box-shadow:var(--sh-md);transform:translateY(-1px);border-color:rgba(0,0,0,.05)}
.ni .src{
    flex-shrink:0;padding:4px 10px;border-radius:6px;
    font-size:.68em;font-weight:650;color:#fff;line-height:1.7;
    white-space:nowrap;letter-spacing:.04em;margin-top:2px;opacity:.92
}
.ni .ntc{
    flex:1;min-width:0;padding:0;cursor:pointer;
    font-size:.95em;font-weight:440;color:var(--tx);line-height:1.75;
    transition:color .3s ease;letter-spacing:.02em;
    word-break:break-all;overflow-wrap:break-word;
}
.ni:hover .ntc{color:var(--accent)}
.ni .ntc::after{content:"›";float:right;font-size:1.4em;color:var(--t3);font-weight:300;
    transition:transform .4s cubic-bezier(.16,1,.3,1),color .3s ease;margin-left:12px;line-height:1.2}
.ni:hover .ntc::after{color:var(--accent);transform:translateX(3px)}

.ni.featured{
    padding:24px 26px;border-left-width:4px;
    background:linear-gradient(105deg,#fff 0%,#fafbff 50%,#fff 100%);
    margin-bottom:16px
}
.ni.featured::before{content:"📌";position:absolute;top:-11px;right:20px;font-size:.88em;opacity:.7}
.ni.featured .ntc{font-size:1.02em;font-weight:520;line-height:1.75}
.ni.featured .ntc::after{font-size:1.55em}
.ni.featured .card-excerpt{
    font-size:.84em;color:var(--t2);line-height:1.8;
    margin-top:8px;display:-webkit-box;-webkit-line-clamp:2;
    -webkit-box-orient:vertical;overflow:hidden;letter-spacing:.02em
}
.ni.featured:hover{transform:translateY(-2px)}

.ni.compact{padding:12px 18px;border-left-width:2px;margin-bottom:4px}
.ni.compact .ntc{font-size:.86em;line-height:1.7}
.ni.compact .src{font-size:.62em;padding:2px 8px}

/* Silky reveal — no blur, no stagger, early trigger, long ease */
.reveal{
    opacity:0;transform:translateY(20px);
    transition:opacity .9s cubic-bezier(.16,1,.3,1),transform .9s cubic-bezier(.16,1,.3,1)
}
.reveal.visible{opacity:1;transform:translateY(0)}

.mo{
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,.28);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    display:flex;align-items:center;justify-content:center;padding:28px;
    animation:moin .35s ease
}
.mo.hi{display:none}
.md{
    background:var(--bg);border-radius:22px;max-width:660px;width:100%;max-height:85vh;
    overflow-y:auto;box-shadow:var(--sh-lg),0 0 0 1px rgba(0,0,0,.06);
    animation:mdin .5s cubic-bezier(.16,1,.3,1)
}
.md-h{padding:34px 34px 0;display:flex;align-items:flex-start;gap:16px}
.md-h h3{font-size:1.2em;font-weight:700;color:var(--tx);line-height:1.6;flex:1;letter-spacing:.03em}
.md-x{
    flex-shrink:0;width:34px;height:34px;border-radius:50%;border:none;
    background:var(--bg2);color:var(--t3);font-size:1em;cursor:pointer;
    display:flex;align-items:center;justify-content:center;transition:all .35s ease
}
.md-x:hover{background:#E5E5EA;color:var(--tx);transform:rotate(90deg)}
.md-b{padding:18px 34px 38px}
.md-b .m-src{display:inline-block;padding:4px 14px;border-radius:6px;font-size:.72em;font-weight:650;color:#fff;margin-bottom:20px;letter-spacing:.04em}
.md-b .m-sum{font-size:.92em;color:var(--t2);line-height:1.9;white-space:pre-wrap;letter-spacing:.02em}
.md-b .rl{
    display:inline-flex;align-items:center;gap:8px;margin-top:26px;
    color:#fff;text-decoration:none;font-weight:600;font-size:.9em;
    padding:10px 22px;border-radius:22px;background:var(--accent);
    transition:all .35s ease;box-shadow:0 2px 10px rgba(0,122,255,.3);letter-spacing:.03em
}
.md-b .rl:hover{background:var(--ad);box-shadow:0 4px 16px rgba(0,122,255,.4);transform:translateY(-1px)}
.md-b .rl::after{content:"→";transition:transform .35s ease}
.md-b .rl:hover::after{transform:translateX(4px)}
@keyframes moin{from{opacity:0}to{opacity:1}}
@keyframes mdin{from{opacity:0;transform:translateY(32px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}

.empty{text-align:center;padding:120px 24px;color:var(--t3)}
.empty .ic{font-size:3.5em;margin-bottom:18px}
.empty p{font-size:1em}

footer{
    text-align:center;padding:28px 20px;font-size:.76em;color:var(--t3);
    border-top:1px solid var(--br);margin-top:auto;background:var(--bg2);letter-spacing:.03em
}
footer p+p{margin-top:4px}
footer .er{color:#DC2626;font-size:.82em;margin-top:4px}
footer a{color:var(--accent);text-decoration:none;font-weight:550}
footer a:hover{text-decoration:underline}

html.lang-zh .la-zh{display:revert}
html.lang-zh .la-en{display:none!important}
html.lang-en .la-en{display:revert}
html.lang-en .la-zh{display:none!important}

@media(max-width:920px){aside.tl{display:none}}
@media(max-width:640px){
    nav#topnav{padding:0 16px}
    nav#topnav .logo{font-size:.84em}
    nav#topnav .ls button{padding:4px 12px;font-size:.74em}
    header{padding:110px 18px 48px}
    header h1{font-size:2em}
    header .sub{font-size:1em}
    .wrap{padding:0 16px}
    main{padding:32px 0 52px}
    .stats{gap:20px;font-size:.76em;padding:16px 16px}
    .ds h2{font-size:.86em}
    .ni{padding:14px 16px;gap:10px;border-radius:12px;border-left-width:2px}
    .ni.featured{padding:16px 18px}
    .ni .ntc{font-size:.88em;line-height:1.7}
    .ni .src{font-size:.62em;padding:2px 8px}
    .md{border-radius:16px}
    .md-h{padding:24px 20px 0}
    .md-b{padding:14px 20px 28px}
}`;

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

let tlHtml = '';
sections.forEach(sec => {
    const parts = sec.id.replace('d', '').split('-');
    tlHtml += `<a href="#${sec.id}"><span class="tl-lbl">${parseInt(parts[1])}/${parseInt(parts[2])}</span></a>\n`;
});

let dsHtml = '';
sections.forEach(sec => {
    let itemsHtml = '';
    sec.items.forEach((item, i) => {
        let cardClass = 'ni reveal';
        let excerptHtml = '';
        if (i === 0) {
            cardClass += ' featured';
            const zhEx = item.zs || '';
            const enEx = item.es || '';
            if (zhEx || enEx) {
                excerptHtml = `<div class="card-excerpt la-zh">${esc(zhEx.substring(0, 200))}</div>
<div class="card-excerpt la-en">${esc(enEx.substring(0, 200))}</div>`;
            }
        } else if (i % 5 === 0) {
            cardClass += ' compact';
        }
        const badge = `<span class="src" style="background:${item.srcColor}">${esc(item.srcName)}</span>`;
        itemsHtml += `<li class="${cardClass}" style="--src-color:${item.srcColor}">${badge}
<div class="ntc la-zh" data-zt="${esc(item.zt)}" data-et="${esc(item.et)}" data-zs="${esc(item.zs)}" data-es="${esc(item.es)}" data-source="${esc(item.source)}" data-color="${esc(item.color)}" data-link="${esc(item.link)}">${esc(item.zt)}</div>
<div class="ntc la-en" data-zt="${esc(item.zt)}" data-et="${esc(item.et)}" data-zs="${esc(item.zs)}" data-es="${esc(item.es)}" data-source="${esc(item.source)}" data-color="${esc(item.color)}" data-link="${esc(item.link)}">${esc(item.et)}</div>
${excerptHtml}</li>\n`;
    });
    dsHtml += `<section class="ds" id="${sec.id}">
<h2><span class="d-dot"></span><span class="la-zh">${esc(sec.zh)}</span><span class="la-en">${esc(sec.en)}</span></h2>
<ul class="news-list">${itemsHtml}</ul></section>\n`;
});

let errHtml = '';
errors.forEach(e => { errHtml += `<p class="er">⚠ ${esc(e)}</p>\n`; });

const newHtml = `<!DOCTYPE html>
<html class="lang-zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="AI 发展日报 · AI Daily">
<meta name="color-scheme" content="light">
<title>🧠 AI 发展日报 · AI Daily</title>
<style>${CSS}</style>
</head>
<body>

<nav id="topnav">
<a href="#" class="logo" style="text-decoration:none"><span class="la-zh">🧠 AI 日报</span><span class="la-en">🧠 AI Daily</span></a>
<div class="ls">
<button data-lang="zh">中文</button>
<button data-lang="en">English</button>
</div>
</nav>

<header>
<div class="hero-inner">
<h1><span class="la-zh">全球<span class="grad"> AI 大事</span>精选</span>
<span class="la-en"><span class="grad">AI Daily</span> Highlights</span></h1>
<p class="sub la-zh">每日精选 · 国内外 AI 要闻</p>
<p class="sub la-en">Curated daily AI highlights</p>
</div>
</header>

<div class="stats">
<span>📰 <span class="val">${totalArticles}</span> <span class="la-zh">条精选</span><span class="la-en">curated</span></span>
<span>📡 <span class="val">${sourcesOk}</span> <span class="la-zh">源正常</span><span class="la-en">sources OK</span></span>
<span>📆 <span class="la-zh">最近</span><span class="la-en">Last</span> <span class="val">${days}</span> <span class="la-zh">天</span><span class="la-en">days</span></span>
</div>

<div class="wrap">
${tlHtml ? `<aside class="tl"><nav>${tlHtml}</nav></aside>` : ''}
<main>${dsHtml}</main>
</div>

<footer>
<p>🕐 <span class="la-zh">最后更新：${esc(updateTime)}（北京时间）</span><span class="la-en">Last updated: ${esc(updateTimeEn)} (CST)</span></p>
<p><span class="la-zh">数据来源：${esc(sourcesStr)}</span><span class="la-en">Sources: ${esc(sourcesStrEn)}</span></p>
${errHtml}
<p style="margin-top:10px"><span class="la-zh">GitHub Actions 每小时自动更新</span><span class="la-en">Powered by GitHub Actions · Hourly</span> · <a href="https://github.com/dycxyz-hash/ai-news-daily">GitHub</a></p>
</footer>

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

var nav=document.getElementById('topnav');
function onScroll(){
    var y=window.scrollY;
    nav.classList.toggle('scrolled',y>10);
    var hero=document.querySelector('header .hero-inner');
    if(hero&&y<600) hero.style.transform='translateY('+(y*0.06)+'px)';
}
window.addEventListener('scroll',onScroll,{passive:true});onScroll();

var tls=document.querySelectorAll('.tl a');
if(tls.length){
    var sec=[];
    tls.forEach(function(a){
        var el=document.getElementById(a.getAttribute('href').slice(1));
        if(el)sec.push({el:el,a:a});
    });
    function up(){
        var sy=window.scrollY+180,ac=null;
        sec.forEach(function(s){if(s.el.offsetTop<=sy)ac=s.a;});
        tls.forEach(function(a){a.classList.remove('on')});
        if(ac)ac.classList.add('on');
    }
    window.addEventListener('scroll',up,{passive:true});up();
}

// Reveal: long ease, early trigger, no stagger
var observer=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
        if(e.isIntersecting){e.target.classList.add('visible');observer.unobserve(e.target)}
    });
},{threshold:0,rootMargin:'0px 0px -100px 0px'});
document.querySelectorAll('.reveal').forEach(function(el){observer.observe(el)});

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
</body>
</html>`;

fs.writeFileSync('index.html', newHtml, 'utf8');
console.log('Done:', (newHtml.length/1024).toFixed(0)+'KB', sections.length+'d', totalArticles+'a (CN only)');
