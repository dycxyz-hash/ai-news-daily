// Rebuild index.html with new Apple-style design from existing data
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync('index.html', 'utf8');

// Extract all news items with their data attributes
const itemRegex = /<li class="ni">(.*?)<\/li>/gs;
const dataRegex = /data-zt="([^"]*)"\s+data-et="([^"]*)"\s+data-zs="([^"]*)"\s+data-es="([^"]*)"\s+data-source="([^"]*)"\s+data-color="([^"]*)"\s+data-link="([^"]*)"/s;
const srcRegex = /<span class="src" style="background:([^"]*)">([^<]*)<\/span>/;

// Extract date sections
const sectionRegex = /<section class="ds" id="([^"]*)">\s*<h2><span class="d-dot"><\/span><span class="la-zh">([^<]*)<\/span><span class="la-en">([^<]*)<\/span><\/h2>\s*<ul class="news-list">(.*?)<\/ul>\s*<\/section>/gs;

// Extract stats
const statsRegex = /<span>📰 <span class="val">(\d+)<\/span>/;
const sourcesRegex = /<span>📡 <span class="val">([^<]*)<\/span>/;
const daysRegex = /<span>📆[^<]*<span class="val">(\d+)<\/span>/;

// Extract update time
const timeRegex = /<span class="la-zh">最后更新：([^<]*)（北京时间\)/;
const timeRegexEn = /Last updated: ([^<]*) \(CST\)/;

// Extract errors
const errorRegex = /<p class="er">([^<]*)<\/p>/g;

// Parse existing data
const sections = [];
let secMatch;
while ((secMatch = sectionRegex.exec(html)) !== null) {
    const items = [];
    let itemMatch;
    const itemBlock = secMatch[4];
    const itemRE = /<li class="ni">(.*?)<\/li>/gs;
    while ((itemMatch = itemRE.exec(itemBlock)) !== null) {
        const itemHtml = itemMatch[0];
        const dMatch = dataRegex.exec(itemHtml);
        const sMatch = srcRegex.exec(itemHtml);
        if (dMatch && sMatch) {
            items.push({
                zt: dMatch[1], et: dMatch[2], zs: dMatch[3], es: dMatch[4],
                source: dMatch[5], color: dMatch[6], link: dMatch[7],
                srcColor: sMatch[1], srcName: sMatch[2]
            });
        }
    }
    sections.push({ id: secMatch[1], zh: secMatch[2], en: secMatch[3], items });
}

console.log(`Found ${sections.length} date sections, ${sections.reduce((s, sec) => s + sec.items.length, 0)} total items`);

// Extract stats
const totalMatch = statsRegex.exec(html);
const sourcesMatch = sourcesRegex.exec(html);
const daysMatch = daysRegex.exec(html);
const total = totalMatch ? totalMatch[1] : '?';
const sourcesOk = sourcesMatch ? sourcesMatch[1] : '?/?';
const days = daysMatch ? daysMatch[1] : '7';

// Extract update time
const timeMatch = html.match(/最后更新：([^<]*)（北京时间\)/);
const timeMatchEn = html.match(/Last updated: ([^<]*) \(CST\)/);
const updateTime = timeMatch ? timeMatch[1] : new Date().toLocaleString('zh-CN');
const updateTimeEn = timeMatchEn ? timeMatchEn[1] : new Date().toLocaleString('en-US');

// Extract errors
const errors = [];
let errMatch;
while ((errMatch = errorRegex.exec(html)) !== null) {
    errors.push(errMatch[1]);
}

// Extract data sources list
const sourcesListMatch = html.match(/数据来源：([^<]*)/);
const sourcesListEnMatch = html.match(/Sources: ([^<]*)/);
const sourcesStr = sourcesListMatch ? sourcesListMatch[1] : '';
const sourcesStrEn = sourcesListEnMatch ? sourcesListEnMatch[1] : '';

// ─── New CSS (Apple-inspired) ───
const CSS = `
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-font-smoothing:antialiased}
:root{
    --accent:#007AFF;--ad:#0056CC;--al:#E8F2FF;
    --tx:#1D1D1F;--t2:#6E6E73;--t3:#AEAEB2;
    --bg:#FFFFFF;--bg2:#F5F5F7;--br:#E5E5EA;
    --sh-sm:0 1px 3px rgba(0,0,0,.04),0 1px 2px rgba(0,0,0,.06);
    --sh-md:0 4px 16px rgba(0,0,0,.06),0 2px 6px rgba(0,0,0,.04);
    --sh-lg:0 12px 40px rgba(0,0,0,.1),0 4px 12px rgba(0,0,0,.06);
}
body{
    font-family:"SF Pro Display",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--tx);line-height:1.5;min-height:100vh;
    display:flex;flex-direction:column;font-weight:400;
}
nav#topnav{
    position:fixed;top:0;left:0;right:0;z-index:100;height:52px;
    display:flex;align-items:center;justify-content:space-between;
    padding:0 28px;
    background:rgba(255,255,255,.72);
    backdrop-filter:blur(20px) saturate(180%);
    -webkit-backdrop-filter:blur(20px) saturate(180%);
    border-bottom:1px solid rgba(0,0,0,.06);
    transition:background .3s ease,border-color .3s ease;
}
nav#topnav.scrolled{background:rgba(255,255,255,.88);border-bottom-color:rgba(0,0,0,.1)}
nav#topnav .logo{font-size:.88em;font-weight:700;color:var(--tx);letter-spacing:-.01em;white-space:nowrap}
nav#topnav .ls{display:inline-flex;gap:1px;background:rgba(0,0,0,.04);border-radius:20px;padding:2px}
nav#topnav .ls button{
    border:none;background:transparent;color:var(--t2);
    padding:5px 15px;border-radius:18px;cursor:pointer;font-size:.75em;
    font-weight:550;transition:all .25s;font-family:inherit;letter-spacing:.01em
}
nav#topnav .ls button.on{background:#fff;color:var(--tx);box-shadow:0 1px 3px rgba(0,0,0,.08)}
nav#topnav .ls button:hover:not(.on){color:var(--tx);background:rgba(0,0,0,.05)}
header{
    padding:140px 24px 64px;text-align:center;position:relative;
    background:var(--bg);overflow:hidden
}
header::before{
    content:"";position:absolute;top:-50%;left:-50%;width:200%;height:200%;
    background:radial-gradient(ellipse 60% 50% at 50% 40%,rgba(0,122,255,.04) 0%,transparent 60%),
              radial-gradient(ellipse 40% 40% at 30% 60%,rgba(88,86,214,.03) 0%,transparent 50%),
              radial-gradient(ellipse 30% 30% at 70% 50%,rgba(175,82,222,.03) 0%,transparent 50%);
    pointer-events:none
}
header h1{font-size:clamp(2.6em,5vw,3.6em);font-weight:700;letter-spacing:-.035em;line-height:1.12;position:relative}
header h1 .grad{
    background:linear-gradient(135deg,#007AFF 0%,#5856D6 45%,#AF52DE 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text
}
header .sub{font-size:1.15em;color:var(--t2);font-weight:400;margin-top:14px;position:relative}
.stats{
    display:flex;justify-content:center;gap:56px;flex-wrap:wrap;
    padding:22px 20px;background:var(--bg2);border-top:1px solid var(--br);border-bottom:1px solid var(--br);
    font-size:.8em;color:var(--t3);font-weight:450
}
.stats .val{font-weight:700;color:var(--accent);font-size:1.1em;font-variant-numeric:tabular-nums}
.wrap{display:flex;max-width:1060px;width:100%;margin:0 auto;padding:0 28px;flex:1}
main{flex:1;max-width:760px;width:100%;margin:0 auto;padding:56px 0 100px}
aside.tl{width:94px;flex-shrink:0;padding-top:60px}
aside.tl nav{position:sticky;top:80px;padding-left:18px;border-left:1.5px solid var(--br)}
aside.tl a{
    display:flex;align-items:center;gap:8px;text-decoration:none;
    color:var(--t3);font-size:.7em;font-weight:550;padding:6px 0;
    position:relative;transition:color .25s
}
aside.tl a::before{
    content:"";position:absolute;left:-22px;top:50%;transform:translateY(-50%);
    width:8px;height:8px;border-radius:50%;background:var(--bg);
    border:1.5px solid var(--br);transition:all .35s cubic-bezier(.25,.1,.25,1)
}
aside.tl a:hover{color:var(--accent)}
aside.tl a:hover::before{border-color:var(--accent);background:var(--al);box-shadow:0 0 0 5px var(--al)}
aside.tl a.on{color:var(--accent);font-weight:700}
aside.tl a.on::before{
    background:var(--accent);border-color:var(--accent);
    box-shadow:0 0 0 5px var(--al);width:10px;height:10px;left:-23px
}
aside.tl a .tl-lbl{opacity:0;transition:opacity .25s;font-variant-numeric:tabular-nums}
aside.tl a:hover .tl-lbl,aside.tl a.on .tl-lbl{opacity:1}
.ds{scroll-margin-top:64px}
.ds h2{
    font-size:1.05em;font-weight:700;color:var(--tx);padding-bottom:16px;
    border-bottom:1px solid var(--br);margin-bottom:8px;
    position:sticky;top:52px;background:var(--bg);z-index:2;
    display:flex;align-items:center;gap:10px
}
.ds h2 .d-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);flex-shrink:0}
.news-list{list-style:none;padding-top:8px}
.ni{
    display:flex;align-items:flex-start;gap:14px;border-radius:14px;
    padding:18px 22px;margin-bottom:6px;
    background:var(--bg);
    box-shadow:none;
    transition:all .35s cubic-bezier(.25,.1,.25,1);
    border:1px solid transparent;
    position:relative
}
.ni:hover{
    background:var(--bg);
    box-shadow:var(--sh-md);
    transform:translateY(-2px);
    border-color:rgba(0,0,0,.06)
}
.ni .src{
    flex-shrink:0;padding:3px 10px;border-radius:6px;
    font-size:.65em;font-weight:650;color:#fff;line-height:1.6;
    white-space:nowrap;letter-spacing:.03em;margin-top:1px
}
.ni .ntc{
    flex:1;min-width:0;padding:0;cursor:pointer;
    font-size:.95em;font-weight:450;color:var(--tx);line-height:1.55;
    transition:color .2s
}
.ni:hover .ntc{color:var(--accent)}
.ni .ntc::after{content:"›";float:right;font-size:1.35em;color:var(--t3);font-weight:300;
    transition:transform .3s cubic-bezier(.25,.1,.25,1),color .2s;margin-left:12px;line-height:1.3}
.ni:hover .ntc::after{color:var(--accent);transform:translateX(3px)}
.reveal{
    opacity:0;filter:blur(6px);transform:translateY(20px);
    transition:opacity .65s cubic-bezier(.25,.1,.25,1),
               filter .65s cubic-bezier(.25,.1,.25,1),
               transform .65s cubic-bezier(.25,.1,.25,1)
}
.reveal.visible{opacity:1;filter:blur(0);transform:translateY(0)}
.mo{
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,.32);
    backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    display:flex;align-items:center;justify-content:center;padding:28px;
    animation:moin .25s ease
}
.mo.hi{display:none}
.md{
    background:var(--bg);border-radius:22px;max-width:660px;width:100%;max-height:85vh;
    overflow-y:auto;box-shadow:var(--sh-lg),0 0 0 1px rgba(0,0,0,.06);
    animation:mdin .4s cubic-bezier(.16,1,.3,1)
}
.md-h{padding:34px 34px 0;display:flex;align-items:flex-start;gap:16px}
.md-h h3{font-size:1.2em;font-weight:700;color:var(--tx);line-height:1.45;flex:1}
.md-x{
    flex-shrink:0;width:34px;height:34px;border-radius:50%;border:none;
    background:var(--bg2);color:var(--t3);font-size:1em;cursor:pointer;
    display:flex;align-items:center;justify-content:center;transition:all .25s
}
.md-x:hover{background:#E5E5EA;color:var(--tx);transform:rotate(90deg)}
.md-b{padding:18px 34px 38px}
.md-b .m-src{display:inline-block;padding:3px 14px;border-radius:6px;
    font-size:.7em;font-weight:650;color:#fff;margin-bottom:20px;letter-spacing:.03em}
.md-b .m-sum{font-size:.9em;color:var(--t2);line-height:1.8;white-space:pre-wrap}
.md-b .rl{
    display:inline-flex;align-items:center;gap:8px;margin-top:26px;
    color:#fff;text-decoration:none;font-weight:600;font-size:.88em;
    padding:10px 22px;border-radius:22px;background:var(--accent);
    transition:all .25s;box-shadow:0 2px 10px rgba(0,122,255,.3)
}
.md-b .rl:hover{background:var(--ad);box-shadow:0 4px 16px rgba(0,122,255,.4);transform:translateY(-1px)}
.md-b .rl::after{content:"→";transition:transform .25s}
.md-b .rl:hover::after{transform:translateX(4px)}
@keyframes moin{from{opacity:0}to{opacity:1}}
@keyframes mdin{from{opacity:0;transform:translateY(28px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
.empty{text-align:center;padding:120px 24px;color:var(--t3)}
.empty .ic{font-size:3.5em;margin-bottom:18px}
.empty p{font-size:1em}
footer{
    text-align:center;padding:28px 20px;font-size:.74em;color:var(--t3);
    border-top:1px solid var(--br);margin-top:auto;background:var(--bg2)
}
footer p+p{margin-top:4px}
footer .er{color:#DC2626;font-size:.8em;margin-top:4px}
footer a{color:var(--accent);text-decoration:none;font-weight:550}
footer a:hover{text-decoration:underline}
html.lang-zh .la-zh{display:revert}
html.lang-zh .la-en{display:none!important}
html.lang-en .la-en{display:revert}
html.lang-en .la-zh{display:none!important}
@media(max-width:920px){aside.tl{display:none}}
@media(max-width:640px){
    nav#topnav{padding:0 16px}
    nav#topnav .logo{font-size:.82em}
    nav#topnav .ls button{padding:4px 12px;font-size:.72em}
    header{padding:100px 18px 44px}
    header h1{font-size:2em}
    header .sub{font-size:1em}
    .wrap{padding:0 16px}
    main{padding:32px 0 52px}
    .stats{gap:20px;font-size:.74em;padding:16px 16px}
    .ds h2{font-size:.95em}
    .ni{padding:14px 16px;gap:10px;border-radius:12px}
    .ni .ntc{font-size:.88em}
    .ni .src{font-size:.6em;padding:2px 8px}
    .md{border-radius:16px}
    .md-h{padding:24px 20px 0}
    .md-b{padding:14px 20px 28px}
}
`.trim();

// ─── Build timeline ───
let tlHtml = '';
sections.forEach(sec => {
    const parts = sec.id.replace('d', '').split('-');
    const label = `${parseInt(parts[1])}/${parseInt(parts[2])}`;
    tlHtml += `<a href="#${sec.id}"><span class="tl-lbl">${label}</span></a>\n`;
});

// ─── Build date sections ───
let dsHtml = '';
sections.forEach(sec => {
    let itemsHtml = '';
    sec.items.forEach(item => {
        const badge = `<span class="src" style="background:${item.srcColor}">${item.srcName}</span>`;
        itemsHtml += `<li class="ni reveal">${badge}
<div class="ntc la-zh" data-zt="${item.zt}" data-et="${item.et}" data-zs="${item.zs}" data-es="${item.es}" data-source="${item.source}" data-color="${item.color}" data-link="${item.link}">${item.zt}</div>
<div class="ntc la-en" data-zt="${item.zt}" data-et="${item.et}" data-zs="${item.zs}" data-es="${item.es}" data-source="${item.source}" data-color="${item.color}" data-link="${item.link}">${item.et}</div></li>\n`;
    });
    dsHtml += `<section class="ds" id="${sec.id}">
<h2><span class="d-dot"></span><span class="la-zh">${sec.zh}</span><span class="la-en">${sec.en}</span></h2>
<ul class="news-list">${itemsHtml}</ul></section>\n`;
});

// ─── Error HTML ───
let errHtml = '';
errors.forEach(e => {
    errHtml += `<p class="er">⚠ ${e}</p>\n`;
});

// ─── Assemble final HTML ───
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
<h1><span class="la-zh">全球<span class="grad"> AI 大事</span>精选</span>
<span class="la-en"><span class="grad">AI Daily</span> Highlights</span></h1>
<p class="sub la-zh">每日聚合 · 国内外 AI 要闻</p>
<p class="sub la-en">Daily AI news from China and beyond</p>
</header>

<div class="stats">
<span>📰 <span class="val">${total}</span> <span class="la-zh">条新闻</span><span class="la-en">articles</span></span>
<span>📡 <span class="val">${sourcesOk}</span> <span class="la-zh">源正常</span><span class="la-en">sources OK</span></span>
<span>📆 <span class="la-zh">最近</span><span class="la-en">Last</span> <span class="val">${days}</span> <span class="la-zh">天</span><span class="la-en">days</span></span>
</div>

<div class="wrap">
${tlHtml ? `<aside class="tl"><nav>${tlHtml}</nav></aside>` : ''}
<main>${dsHtml}</main>
</div>

<footer>
<p>🕐 <span class="la-zh">最后更新：${updateTime}（北京时间）</span><span class="la-en">Last updated: ${updateTimeEn} (CST)</span></p>
<p><span class="la-zh">数据来源：${sourcesStr}</span><span class="la-en">Sources: ${sourcesStrEn}</span></p>
${errHtml}
<p style="margin-top:10px"><span class="la-zh">GitHub Actions 每小时自动更新</span><span class="la-en">Powered by GitHub Actions · Hourly</span> · <a href="https://github.com/dycxyz-hash/ai-news-daily">GitHub</a></p>
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
function upNav(){
    if(window.scrollY>10)nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
}
window.addEventListener('scroll',upNav,{passive:true});upNav();

var tls=document.querySelectorAll('.tl a');
if(tls.length){
    var sec=[];
    tls.forEach(function(a){
        var el=document.getElementById(a.getAttribute('href').slice(1));
        if(el)sec.push({el:el,a:a});
    });
    function up(){
        var sy=window.scrollY+160,ac=null;
        sec.forEach(function(s){if(s.el.offsetTop<=sy)ac=s.a;});
        tls.forEach(function(a){a.classList.remove('on')});
        if(ac)ac.classList.add('on');
    }
    window.addEventListener('scroll',up,{passive:true});up();
}

var observer=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
        if(e.isIntersecting){
            e.target.classList.add('visible');
            observer.unobserve(e.target);
        }
    });
},{threshold:0.12,rootMargin:'0px 0px -30px 0px'});
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
console.log(`✅ Done! Generated index.html (${(newHtml.length/1024).toFixed(0)} KB)`);
console.log(`   ${sections.length} days, ${sections.reduce((s,sec)=>s+sec.items.length,0)} articles`);
