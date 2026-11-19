// Yarr staging: public product landing page plus isolated, disabled account APIs.
// Product name and public domain remain provisional. No home-server media proxy.
const JSON_HEADERS = {'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'};
const HTML_HEADERS = {'content-type':'text/html; charset=utf-8','cache-control':'public, max-age=300','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; img-src 'self' https://raw.githubusercontent.com; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"};
// Public emblem and favicon use the same square artwork as the app.
const YARR_ICON_SVG = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 900 900\" role=\"img\" aria-label=\"Yarr Media moon, pirate sail and waves\"><path fill=\"#fff\" d=\"M34,808 78,809 193,798 254,798 313,805 395,823 445,832 490,837 527,838 572,835 613,829 695,809 751,800 776,798 821,798 855,801 868,804 873,803 833,790 794,782 766,779 722,779 684,784 628,797 592,803 562,806 506,806 447,797 381,779 339,770 303,765 251,763 213,766 178,772 84,797Z M285,129 246,152 216,174 194,193 162,227 140,256 122,285 108,313 92,355 82,393 77,424 77,493 83,529 89,552 103,591 120,626 147,668 173,700 198,725 232,753 288,747 313,686 337,639 363,596 401,543 455,481 521,419 574,380 598,366 634,349 667,339 683,337 683,339 668,349 653,363 640,381 630,409 628,432 609,437 589,452 558,463 587,477 620,482 618,492 618,518 621,536 626,552 635,571 648,590 660,602 672,610 665,611 633,605 613,608 602,614 596,619 596,621 609,622 624,628 608,634 596,645 596,647 608,650 624,659 637,672 627,675 650,690 673,716 670,717 620,697 565,683 521,677 467,677 440,680 410,686 370,699 352,707 331,720 317,732 307,745 392,750 451,759 559,779 623,782 657,760 683,739 711,712 737,682 761,648 775,624 791,590 804,553 811,524 816,491 817,443 815,418 811,391 803,357 790,320 776,290 755,255 736,229 706,195 687,177 656,152 632,136 593,116 561,104 531,96 494,90 462,88 426,89 383,95 354,102 329,110Z\"/></svg>";
const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yarr Media — Your media. Your server.</title>
<meta name="description" content="Yarr Media organizes your personal movies and shows. Free local streaming; Pro remote access is in development.">
<meta name="robots" content="index,follow"><link rel="canonical" href="https://yarr.larki-brian.workers.dev/">
<style>
:root{color-scheme:dark;--bg:#0a0a0a;--ink:#f5f1e8;--accent:#a61e1e;--bright:#eb8888;--muted:#c2bcb2;--line:#ffffff25;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 85% 11%,#39101055,transparent 34%),var(--bg);min-width:280px}a{color:inherit}.wrap{max-width:1180px;margin:auto;padding:0 30px}
.nav{min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.075em;font-size:21px;white-space:nowrap}.brand img{width:46px;height:46px;object-fit:contain}.brand strong{color:var(--bright)}.brand .brand-label{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-weight:900;letter-spacing:.01em;color:var(--ink)}.brand-dot{color:#9b9b9b}.brand-media{color:#c62838}.navlinks{display:flex;align-items:center;gap:23px;flex-wrap:wrap}.navlinks a{text-decoration:none;font-size:14px;color:#d9d3c9;transition:color .2s}.navlinks a:hover{color:#fff}.nav-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.nav-actions a{font-size:13px;font-weight:750;white-space:nowrap;text-decoration:none;padding:10px 14px;border-radius:8px;border:1px solid #ffffff48;transition:background .22s,transform .22s}.nav-actions a:hover{background:#ffffff18;transform:translateY(-2px)}.nav-actions .open-app{background:#a61e1e;border-color:#a61e1e;color:#fff}.nav-actions .open-app:hover{background:#c32c2c}
.hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(230px,.8fr);gap:46px;align-items:center;min-height:570px;padding:69px 0 83px}.hero-copy{min-width:0}.hero-art{width:100%;max-height:480px;object-fit:contain;filter:drop-shadow(0 22px 35px #0009);}.eyebrow{color:var(--bright);text-transform:uppercase;font-weight:800;letter-spacing:.18em;font-size:12px}h1,h2,h3,p{margin-top:0}h1{font-size:clamp(52px,6.5vw,88px);line-height:1.04;letter-spacing:-.058em;margin:21px 0 26px}h1 em{font-style:normal;color:#e16b6b}.lead{font-size:19px;line-height:1.7;color:#ded7ce;max-width:650px}.sublead{font-size:15px;color:var(--muted);line-height:1.65;max-width:630px}
.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:30px}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:12px 21px;border:1px solid #a61e1e;border-radius:8px;font-size:14px;font-weight:750;text-decoration:none;transition:transform .25s cubic-bezier(.2,.8,.2,1),background .25s,box-shadow .25s}.btn.primary{background:#a61e1e;color:#fff}.btn:hover{background:#c32c2c;color:#fff;transform:translateY(-3px);box-shadow:0 10px 24px #a61e1e33}a:focus-visible{outline:2px solid #f3a1a1;outline-offset:4px}
.section{padding:72px 0;border-top:1px solid var(--line);scroll-margin-top:18px}.section h2{font-size:clamp(29px,3.6vw,44px);line-height:1.16;letter-spacing:-.045em;margin:14px 0 15px}.section-intro{color:var(--muted);font-size:16px;line-height:1.7;max-width:730px}.features,.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:32px}.tile{padding:28px;border:1px solid var(--line);border-radius:14px;background:#151515;min-width:0;transition:transform .35s ease,border-color .3s ease,background .3s ease,box-shadow .35s ease}.tile:hover{transform:translateY(-7px);border-color:#a61e1e95;background:#1b1515;box-shadow:0 18px 32px #0006}.tile b{color:var(--bright);font-size:12px;letter-spacing:.15em}.tile h3{font-size:19px;margin:18px 0 10px}.tile p{color:var(--muted);font-size:14px;line-height:1.65;margin:0}
.plans{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;margin-top:32px}.plan{display:flex;flex-direction:column;min-width:0;padding:32px;border:1px solid #ffffff3a;border-radius:16px;background:#151515;transition:transform .35s ease,border-color .3s ease,box-shadow .3s ease}.plan:hover{transform:translateY(-6px);box-shadow:0 20px 38px #0007}.plan.pro{border-color:#a61e1e;background:linear-gradient(145deg,#2b1111,#151515 60%)}.plan-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.plan h3{font-size:32px;letter-spacing:-.04em;margin:0}.plan-label{border-radius:50px;background:#842222;color:white;padding:6px 10px;font-weight:800;font-size:11px;letter-spacing:.07em;text-transform:uppercase}.plan-price{font-weight:750;margin:12px 0 7px}.plan-desc{color:var(--muted);font-size:14px;line-height:1.65;min-height:46px}.plan ul{padding:0;margin:15px 0 25px;list-style:none;flex:1}.plan li{padding:12px 0 12px 27px;border-bottom:1px solid #ffffff19;position:relative;font-size:14px;line-height:1.5}.plan li:before{content:"✓";position:absolute;left:0;color:#eb8888;font-weight:900}.plan li.unavailable{color:#aaa49e}.plan li.unavailable:before{content:"—";color:#aaa49e}.plan .btn{align-self:flex-start}.footnote{font-size:12px;line-height:1.6;color:#bab1a5;margin:16px 0 0}
.steps .tile{border-top:3px solid #a61e1e}.launch{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:12px;padding:26px 30px;background:#151515;max-width:850px}.launch p{line-height:1.7;color:var(--muted);margin:8px 0 0}.footer{border-top:1px solid var(--line);padding:34px 0 45px;color:#aaa49b;font-size:13px;display:grid;grid-template-columns:1.35fr repeat(3,1fr);gap:24px}.footer-title{color:var(--ink);font-size:14px;font-weight:800;margin:0 0 12px}.footer a{display:block;color:#c8c2b9;text-decoration:none;margin:9px 0;line-height:1.5}.footer a:hover{color:#fff;text-decoration:underline;text-decoration-color:#a61e1e}.footer small{display:block;margin-top:12px;color:#999188;line-height:1.6}
@keyframes rise-in{from{opacity:.25;transform:translateY(42px)}to{opacity:1;transform:translateY(0)}}@keyframes fade-in{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}.hero-copy{animation:fade-in .85s ease-out both}
@supports (animation-timeline:view()){.reveal{animation:rise-in linear both;animation-timeline:view();animation-range:entry 0% entry 75%}.reveal .tile:nth-child(2){transition-delay:.07s}.reveal .tile:nth-child(3){transition-delay:.14s}}
@media(max-width:850px){.footer{grid-template-columns:repeat(2,minmax(0,1fr))}.wrap{padding:0 20px}.nav{padding:16px 0;flex-wrap:wrap;gap:10px}.navlinks{gap:15px}.hero{grid-template-columns:1fr;min-height:0;padding:42px 0 60px;gap:15px}.hero-art{grid-row:1;justify-self:center;max-width:260px;max-height:260px}.hero h1{font-size:clamp(48px,10vw,74px)}.section{padding:51px 0}.features,.steps{grid-template-columns:1fr}.plans{grid-template-columns:1fr}.plan-desc{min-height:0}}
@media(max-width:450px){.footer{grid-template-columns:1fr}.nav-actions{width:100%}.nav-actions a{flex:1;text-align:center}.wrap{padding:0 16px}.brand{font-size:18px}.brand img{height:38px;width:38px}.navlinks{gap:12px}.navlinks a{font-size:12px}.hero h1{font-size:clamp(44px,12vw,59px)}.lead{font-size:17px}.plan{padding:24px}.tile{padding:23px}.actions .btn{width:100%}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.hero-art,.hero-copy,.reveal{animation:none!important}.btn,.tile,.plan,.navlinks a{transition:none!important}.btn:hover,.tile:hover,.plan:hover{transform:none!important}}
</style></head><body><div class="wrap">
<nav class="nav"><div class="brand"><img src="/favicon.svg?v=moon-sail-v1" alt="" aria-hidden="true"><span class="brand-label">YARR<span class="brand-dot">.</span><span class="brand-media">MEDIA</span></span></div><div class="navlinks"><a href="#features">Features</a><a href="#plans">Free vs Pro</a><a href="/how-it-works">How it works</a></div><div class="nav-actions"><a href="/account">My Account</a><a class="open-app" href="/app">Open App</a></div></nav>
<main><section class="hero"><div class="hero-copy"><div class="eyebrow">Self-hosted movies &amp; television</div><h1>Your media.<br><em>Your rules.</em></h1><p class="lead">Give your personal movie and TV collection a home. Organize your libraries, browse rich details, and watch from a server you control.</p><p class="sublead">Start free at home. Yarr Media Pro is planned to add secure remote access for watching away from home.</p><div class="actions"><a class="btn primary" href="#setup">See how it works</a><a class="btn" href="#plans">Compare Free &amp; Pro</a></div></div><img class="hero-art" src="https://raw.githubusercontent.com/blarkin13/one-eyed-willie/main/server/new%20logo.png" alt="Yarr Media pirate ship"></section>
<section id="features" class="section reveal"><div class="eyebrow">One collection. One place.</div><h2>Everything you need for your own library.</h2><p class="section-intro">Build a personal media experience without giving up control of your files.</p><div class="features">
<div class="tile"><b>01 / ORGANIZE</b><h3>Beautiful movie &amp; TV libraries</h3><p>Browse posters, cast, episodes, ratings and available metadata.</p></div>
<div class="tile"><b>02 / WATCH</b><h3>Play from your own server</h3><p>Enjoy local playback with your existing files and storage.</p></div>
<div class="tile"><b>03 / CONNECT</b><h3>Optional integrations</h3><p>Connect services like Radarr, Sonarr and SABnzbd to help manage your collection.</p></div></div></section>
<section id="plans" class="section reveal"><div class="eyebrow">Choose your experience</div><h2>Free at home. Pro wherever you go.</h2><p class="section-intro">Both versions are built around your own media server. The key planned Pro benefit is remote access outside your home network.</p>
<div class="plans"><article class="plan"><div class="plan-head"><h3>Free</h3></div><div class="plan-price">Free local use</div><p class="plan-desc">A complete personal library experience on your home network.</p><ul>
<li>Self-host your media server</li><li>Organize movies, shows, seasons and episodes</li><li>Browse available artwork, cast and metadata</li><li>Stream on your home network</li><li>Optional library integrations</li><li class="unavailable">Remote access outside your home</li></ul><a class="btn" href="#setup">Learn about setup</a></article>
<article class="plan pro"><div class="plan-head"><h3>Pro</h3><span class="plan-label">In development</span></div><div class="plan-price">Pricing to be announced</div><p class="plan-desc">Everything in Free, with secure access to your home library while you're away.</p><ul>
<li>Everything included in Free</li><li>Remote access outside your home network (planned)</li><li>Watch your own library while traveling (planned)</li><li>Account-linked server connection (in development)</li><li>Local media stays on your own server</li></ul><a class="btn primary" href="#availability">Pro availability</a><p class="footnote">Remote access is a planned Pro feature and is not a generally available paid service yet.</p></article></div></section>
<section id="setup" class="section reveal"><div class="eyebrow">How it works</div><h2>Your server. Three simple steps.</h2><div class="steps">
<div class="tile"><b>01 / INSTALL</b><h3>Run your server</h3><p>Host Yarr Media on compatible home hardware with your own storage.</p></div>
<div class="tile"><b>02 / ORGANIZE</b><h3>Add your collections</h3><p>Choose media folders and let Yarr Media assemble your libraries.</p></div>
<div class="tile"><b>03 / ENJOY</b><h3>Watch locally</h3><p>Stream on your home network. Pro remote connectivity is being developed.</p></div></div></section>
<section id="availability" class="section reveal"><div class="eyebrow">Development preview</div><h2>We're preparing Yarr Media for release.</h2><div class="launch"><strong>Public downloads and Pro purchasing are not available yet.</strong><p>Yarr Media is under active development. This site describes the planned product tiers; it does not activate remote access or require a payment.</p></div></section></main>
<footer class="footer"><div><div class="footer-title">Yarr Media</div><div>Your collection. Your server.</div><small>Development preview. Public downloads and Pro purchases are not yet available.</small></div><div><div class="footer-title">Product</div><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/remote-access">Remote access</a><a href="/how-it-works">How it works</a></div><div><div class="footer-title">Account</div><a href="/account">My Account</a><a href="/app">Open App</a></div><div><div class="footer-title">Legal</div><a href="/terms">Terms of Use</a><a href="/privacy">Privacy Policy</a><a href="/cookies">Cookie Policy</a></div></footer>
</div></body></html>`;



const SITE_HEADER = '<header class="site-header" role="banner"><a href="/" class="site-brand" aria-label="Yarr Media home"><img src="/favicon.svg?v=moon-sail-v1" alt="" aria-hidden="true"><span class="site-brand-label">YARR<span class="brand-dot">.</span><span class="brand-media">MEDIA</span></span></a><nav class="site-nav" aria-label="Main navigation"><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/how-it-works">How it works</a></nav><div class="site-actions"><a href="/account">My Account</a><a class="site-app-link" href="/app">Open App</a></div></header>';
const SITE_FOOTER = '<footer class="site-footer" role="contentinfo"><div><div class="site-foot-title">Yarr Media</div><div>Your collection. Your server.</div><small>Development preview. Public downloads and Pro purchases are not yet available.</small></div><div><div class="site-foot-title">Product</div><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/remote-access">Remote access</a><a href="/how-it-works">How it works</a></div><div><div class="site-foot-title">Account</div><a href="/account">My Account</a><a href="/app">Open App</a></div><div><div class="site-foot-title">Legal</div><a href="/terms">Terms of Use</a><a href="/privacy">Privacy Policy</a><a href="/cookies">Cookie Policy</a></div></footer>';
const SITE_CHROME_CSS = `
:root{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0a;color:#f5f1e8}html{background:#0a0a0a}body{margin:0;min-height:100vh;background:#0a0a0a;color:#f5f1e8;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}a{color:inherit}.wrap{max-width:1180px;margin:auto;padding:0 24px}
.site-header{max-width:100%;min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 0;border-bottom:1px solid #ffffff29}
.site-header .site-brand{display:flex;align-items:center;gap:12px;white-space:nowrap;text-decoration:none;color:#f5f1e8;font-size:21px;letter-spacing:.075em;font-weight:900}
.site-brand img{height:48px;width:48px;flex:none;object-fit:contain}.site-brand strong{color:#eb8888}.site-header .site-brand .site-brand-label{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:clamp(18px,1.8vw,23px);font-weight:900;letter-spacing:.01em;line-height:1;color:#f5f1e8}
.site-nav{display:flex;align-items:center;gap:22px;flex-wrap:wrap}.site-nav a{color:#d9d3c9;text-decoration:none;font-size:14px;font-weight:500}.site-nav a:hover{color:#fff}
.site-actions{display:flex;align-items:center;gap:10px}.site-actions a{display:inline-flex;justify-content:center;align-items:center;padding:10px 14px;min-height:42px;border-radius:8px;border:1px solid #ffffff48;text-decoration:none;color:#f5f1e8;font-size:13px;font-weight:750;white-space:nowrap;transition:background .2s ease,transform .2s ease}
.site-actions a:hover{background:#ffffff18;transform:translateY(-2px)}.site-actions .site-app-link{background:#a61e1e;color:white;border-color:#a61e1e}.site-actions .site-app-link:hover{background:#c32c2c}
.site-footer{border-top:1px solid #ffffff29;padding:34px 0 45px;color:#aaa49b;font-size:13px;display:grid;grid-template-columns:1.35fr repeat(3,minmax(0,1fr));gap:24px}
.site-footer .site-foot-title{color:#f5f1e8;font-size:14px;font-weight:800;margin:0 0 12px}.site-footer a{display:block;color:#c8c2b9;text-decoration:none;margin:9px 0;line-height:1.5}.site-footer a:hover{text-decoration:underline;text-decoration-color:#a61e1e;color:#fff}
.site-footer small{display:block;margin-top:12px;color:#999188;line-height:1.6}
.site-header a:focus-visible,.site-footer a:focus-visible{outline:2px solid #ef9393;outline-offset:4px}
@media(max-width:1050px){.site-header{flex-wrap:wrap}.site-nav{gap:16px}.site-footer{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.site-header{gap:13px}.site-header .site-brand{font-size:18px}.site-brand img{width:38px;height:38px}.site-nav{order:3;width:100%;gap:15px}.site-nav a{font-size:13px}.site-actions{margin-left:auto}.site-actions a{padding:9px;font-size:12px}.site-footer{grid-template-columns:1fr}}
@media(max-width:350px){.site-actions{width:100%}.site-actions a{flex:1}}
@media(prefers-reduced-motion:reduce){.site-actions a{transition:none}.site-actions a:hover{transform:none}}
`;
function siteChrome(html) {
 let out=html;
 const header=/<header class="nav">[\s\S]*?<\/header>|<nav class="nav">[\s\S]*?<\/nav>/;
 const footer=/<footer class="(?:footer|foot|note)">[\s\S]*?<\/footer>/;
 if(!header.test(out)||!footer.test(out)||!out.includes('</style>'))throw Error('Public site chrome missing');
 out=out.replace(header,SITE_HEADER).replace(footer,SITE_FOOTER);
 return out.replace('</style>',SITE_CHROME_CSS+'</style>').replace('</head>','<link rel="icon" type="image/svg+xml" href="/favicon.svg?v=moon-sail-v1"></head>');
}

const PUBLIC_PAGE_DATA = {
 '/features': {title:'Features',description:'Explore movie and TV libraries, metadata and local playback with Yarr Media.',eyebrow:'The product',heading:'Your collection, beautifully organized.',body:'Yarr Media helps you browse and play your own movie and television files on a server you control.',sections:[
 ['Movies and television','Organize your own media into libraries, seasons and episodes, with available posters, descriptions, cast and ratings.'],
 ['Local playback','Stream your media on supported devices across your home network, with playback behavior depending on file format and hardware.'],
 ['Optional connections','Connect Radarr, Sonarr and SABnzbd where configured. These services are optional and remain separately managed.']]},
 '/free-vs-pro': {title:'Free vs Pro',description:'Compare Yarr Media Free local streaming with the planned Pro remote-access features.',eyebrow:'Plans',heading:'Start free at home. Go further with Pro.',body:'Free is designed for local self-hosted libraries. Pro is planned to add secure remote access to your home server.',sections:[
 ['Free','Local library organization, browsing, compatible local playback and optional integrations. Free does not include remote access outside your home network.'],
 ['Pro — in development','Includes Free capabilities plus planned account-linked remote access, so you can reach your own library away from home.'],
 ['Availability and pricing','Pro pricing and public purchase availability have not been announced. This page is a product preview, not a checkout or an activation offer.']]},
 '/remote-access': {title:'Remote Access',description:'Learn about planned Yarr Media Pro remote playback from your self-hosted library.',eyebrow:'Planned Pro feature',heading:'Your home library, beyond home.',body:'Yarr Media Pro is planned to support remote access to a compatible, self-hosted Yarr Media server. This feature is still in development and not generally available for purchase.',sections:[
 ['Designed around your own server','Your media files remain on your server. Remote connections depend on authentication, device compatibility and your home internet connection.'],
 ['Secure account-linked access','Account-based server pairing and remote playback are being developed. Availability, networking requirements and performance will vary.'],
 ['Free stays local','The Free tier is intended for watching within your home network; external remote access is a Pro benefit.']]},
 '/how-it-works': {title:'How It Works',description:'Understand how to self-host Yarr Media, add your own libraries and watch locally.',eyebrow:'Getting started',heading:'Your server. Your movies. Your control.',body:'Yarr Media is a self-hosted product. Public installers and finalized setup documentation are being prepared.',sections:[
 ['1. Run a compatible server','Install the Yarr Media server on supported home hardware when public packages become available.'],
 ['2. Add your own media folders','Point the server at media you own or are authorized to use. It organizes titles and fetches available information from connected metadata services.'],
 ['3. Watch on your home network','Browse your library and play supported media locally. Remote access is a separate, planned Pro feature.']]}
};
const LEGAL_PAGE_DATA = {
 '/privacy': {title:'Privacy Policy',eyebrow:'Privacy',description:'How the Yarr Media preview website and connected account currently handle information.',heading:'Privacy Policy',intro:'This notice describes the current Yarr Media development-preview website and account features as implemented. Product behavior may change before public release.',sections:[
 ['Information used for accounts','If you sign in with Google, the website receives a verified account identifier, email address, display name and, if provided by Google, a profile picture URL. It stores associated account and session records to operate sign-in.'],
 ['Paired server information','Account-linked records can include server display names, identifiers, pairing status, connection credential hashes and connection status. Network diagnostics may exchange connection information to evaluate server access.'],
 ['Your media','Yarr Media is designed to operate from your own server. The public website does not provide a public media-storage service. Media access and metadata processing on your installed server are separate from the marketing website.'],
 ['Service providers','The preview runs on Cloudflare infrastructure and uses Google sign-in. These providers may process technical information needed to deliver their respective services.'],
 ['Your choices','You can sign out of your account. For questions about access, correction or deletion of account information during the preview, contact the project owner through the project repository. Automated account deletion is not represented here as available.'],
 ['Changes','This page describes the current preview rather than a finalized production policy. Material changes will require an updated notice before public launch.']]},
 '/cookies': {title:'Cookie Policy',eyebrow:'Cookies',description:'Session and Google sign-in cookies used by the Yarr Media preview.',heading:'Cookie Policy',intro:'The Yarr Media public marketing pages do not require sign-in. The account area uses essential cookies for authentication.',sections:[
 ['Session cookie','After sign-in, an HttpOnly, Secure session cookie named __Host-yarr_session allows the website to recognize the signed-in account. The code sets a maximum age of seven days.'],
 ['Google sign-in cookie','During the Google sign-in flow, a temporary HttpOnly, Secure cookie named __Host-yarr_oauth helps validate the return from Google. Its maximum age is ten minutes and it is cleared after the flow.'],
 ['Other technologies','The application may use ordinary browser storage on the connected media interface. This notice describes the public website and account cookies, not every setting of a separately installed media server.'],
 ['Controls','You can clear cookies in your browser. Removing essential sign-in cookies will sign you out or interrupt an in-progress login.'],
 ['Advertising','No advertising or analytics cookies are intentionally set by this marketing-page implementation. Infrastructure providers may independently receive standard connection information.']]},
 '/terms': {title:'Terms of Use',eyebrow:'Legal',description:'Preview terms for browsing and testing Yarr Media.',heading:'Terms of Use',intro:'Yarr Media is currently a development preview. These terms describe preview access and do not constitute finalized paid-service terms.',sections:[
 ['Preview status','Features can change, be unavailable or be interrupted during testing. Public installers, paid Pro checkout and production support commitments are not yet offered on this site.'],
 ['Your own media','You are responsible for ensuring you have the rights to store, organize and play files on your server and for complying with applicable laws. Yarr Media does not supply movies or television programs.'],
 ['Third-party services','Optional integrations and Google sign-in are subject to the terms and availability of their respective providers.'],
 ['Accounts and security','Keep account credentials secure and use the preview only for authorized access to your own installations. Do not attempt unauthorized access or interfere with the service.'],
 ['Pro availability','Remote access is a planned Pro capability, not a generally available paid entitlement. Pricing, billing, refunds and finalized subscription or license terms have not been published.'],
 ['Changes and contact','These preview disclosures will be reviewed and updated before a paid public launch. Product questions can be raised through the Yarr Media project repository.']]}
};
const PUBLIC_SITE = 'https://yarr.larki-brian.workers.dev';
const PUBLIC_URLS = ['/',...Object.keys(PUBLIC_PAGE_DATA),...Object.keys(LEGAL_PAGE_DATA)];
const legalEscape = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function infoPage(path) {
 const data=PUBLIC_PAGE_DATA[path]||LEGAL_PAGE_DATA[path];
 if(!data)return null;
 const items=data.sections.map(([heading,body])=>'<section class="info-section"><h2>'+legalEscape(heading)+'</h2><p>'+legalEscape(body)+'</p></section>').join('');
 const name=legalEscape(data.title),isLegal=!!LEGAL_PAGE_DATA[path];
 return siteChrome('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
  '<title>'+name+' | Yarr Media</title><meta name="description" content="'+legalEscape(data.description)+'"><meta name="robots" content="index,follow"><link rel="canonical" href="'+PUBLIC_SITE+path+'">'+
  '<style>:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#f5f1e8;background:#0a0a0a}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 85% 5%,#3b111144,transparent 36%),#0a0a0a}.wrap{max-width:1180px;margin:auto;padding:0 24px}a{color:#f5f1e8}a:focus-visible{outline:2px solid #ef9393;outline-offset:4px}.nav,.foot{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:18px;padding:22px 0;border-bottom:1px solid #ffffff28}.nav a,.foot a{text-decoration:none}.nav .brand{font-size:22px;font-weight:900;letter-spacing:.04em}.nav .brand span{color:#e67c7c}.navlinks{display:flex;gap:18px;flex-wrap:wrap;font-size:14px}.navlinks a:hover,.foot a:hover{text-decoration:underline;text-decoration-color:#a61e1e}main{padding:75px 0 80px}.eyebrow{color:#ea8787;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.17em}h1{font-size:clamp(40px,6vw,66px);letter-spacing:-.05em;line-height:1.1;margin:16px 0 22px}h2{font-size:23px;margin:0 0 10px}p{color:#cdc7be;line-height:1.8;font-size:16px}.intro{font-size:19px;max-width:800px;margin-bottom:38px}.info-section{padding:25px 0;border-top:1px solid #ffffff25}.info-section p{margin:0}.cta{margin-top:35px;display:inline-block;background:#a61e1e;color:#fff;border-radius:8px;padding:13px 20px;text-decoration:none;font-weight:800}.foot{border-top:1px solid #ffffff28;border-bottom:0;font-size:13px;color:#a9a29a;justify-content:flex-start}.foot a{margin-right:10px}@media(max-width:600px){main{padding:48px 0}.nav{align-items:flex-start}.navlinks{gap:11px}p{font-size:15px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}</style></head><body><div class="wrap">'+
  '<header class="nav"><a class="brand" href="/">YARR <span>MEDIA</span></a><nav class="navlinks" aria-label="Main"><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/account">My Account</a><a href="/app">Open App</a></nav></header>'+
  '<main><div class="eyebrow">'+legalEscape(data.eyebrow)+'</div><h1>'+legalEscape(data.heading)+'</h1><p class="intro">'+legalEscape(data.intro||data.body)+'</p>'+items+
  (isLegal?'':'<a class="cta" href="/#plans">Compare Free and Pro</a>')+'</main>'+
  '<footer class="foot"><span>Yarr Media · Development preview</span><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/cookies">Cookies</a><a href="/">Home</a></footer></div></body></html>');
}

const SITE = "https://yarr.larki-brian.workers.dev";
const SESSION_SECONDS = 7*24*60*60;
const FLOW_SECONDS = 10*60;
const authReady = env => Boolean(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET && env.ACCOUNTS);
const encoded = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const decoded = input => Uint8Array.from(atob(input.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-input.length%4)%4)),c=>c.charCodeAt(0));
const random = () => encoded(crypto.getRandomValues(new Uint8Array(32)));
async function digest(value) {return encoded(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))));}
const getCookie = (req,name) => (req.headers.get('cookie')||'').split(';').map(p=>p.trim()).find(p=>p.startsWith(name+'='))?.slice(name.length+1)||'';
const cookie = (name,value,age) => name+'='+value+'; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age='+age;
const json = (payload,status=200,extra={})=>new Response(JSON.stringify(payload),{status,headers:{...JSON_HEADERS,...extra}});
const redirect = (dest,extra={})=>new Response(null,{status:303,headers:{location:dest,'cache-control':'no-store',...extra}});
const html = (text,status=200,extra={})=>new Response(text,{status,headers:{...HTML_HEADERS,'cache-control':'no-store',...extra}});
const escapeHTML = value => String(value||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function currentUser(req,env) {
 const raw=getCookie(req,'__Host-yarr_session');
 if(!raw||raw.length>200)return null;
 const tokenHash=await digest(raw);
 const record=await env.ACCOUNTS.prepare(
  "SELECT users.id,users.email,users.display_name,users.avatar_url,users.created_at FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires_at > CURRENT_TIMESTAMP"
 ).bind(tokenHash).first();
 return record||null;
}
async function validateGoogleIdToken(token,clientId,nonce) {
 if(typeof token!=='string'||token.length>12000)throw Error('invalid_token');
 const parts=token.split('.');
 if(parts.length!==3)throw Error('invalid_token');
 const header=JSON.parse(new TextDecoder().decode(decoded(parts[0])));
 const payload=JSON.parse(new TextDecoder().decode(decoded(parts[1])));
 if(header.alg!=='RS256'||typeof header.kid!=='string'||!header.kid)throw Error('invalid_algorithm');
 if(payload.iss!=='https://accounts.google.com'&&payload.iss!=='accounts.google.com')throw Error('invalid_issuer');
 if(payload.aud!==clientId||(payload.azp&&payload.azp!==clientId))throw Error('invalid_audience');
 const now=Math.floor(Date.now()/1000);
 if(typeof payload.exp!=='number'||payload.exp<=now||payload.exp>now+3600)throw Error('invalid_expiration');
 if(typeof payload.iat!=='number'||payload.iat>now+60||payload.iat<now-86400)throw Error('invalid_issued_at');
 if(payload.nonce!==nonce||typeof payload.sub!=='string'||!payload.sub||payload.email_verified!==true)throw Error('invalid_identity');
 const keys=await fetch('https://www.googleapis.com/oauth2/v3/certs',{headers:{accept:'application/json'}});
 if(!keys.ok)throw Error('jwks_unavailable');
 const jwks=await keys.json();
 const jwk=jwks.keys?.find(k=>k.kid===header.kid&&k.kty==='RSA'&&(!k.use||k.use==='sig')&&(!k.alg||k.alg==='RS256'));
 if(!jwk)throw Error('unknown_signing_key');
 const key=await crypto.subtle.importKey('jwk',jwk,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
 const valid=await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,decoded(parts[2]),new TextEncoder().encode(parts[0]+'.'+parts[1]));
 if(!valid)throw Error('invalid_signature');
 return payload;
}
async function googleStart(env) {
 if(!authReady(env))return redirect('/account?setup=required');
 const state=random(),nonce=random(),verifier=random(),challenge=await digest(verifier);
 await env.ACCOUNTS.prepare("DELETE FROM oauth_flows WHERE expires_at < CURRENT_TIMESTAMP").run();
 await env.ACCOUNTS.prepare("INSERT INTO oauth_flows(state_hash,nonce,verifier,expires_at) VALUES(?,?,?,datetime('now','+10 minutes'))").bind(await digest(state),nonce,verifier).run();
 const p=new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,redirect_uri:SITE+'/auth/google/callback',response_type:'code',scope:'openid email profile',state,nonce,code_challenge:challenge,code_challenge_method:'S256',prompt:'select_account'});
 return redirect('https://accounts.google.com/o/oauth2/v2/auth?'+p,{ 'set-cookie':cookie('__Host-yarr_oauth',state,FLOW_SECONDS) });
}
async function googleCallback(req,env) {
 const u=new URL(req.url),state=u.searchParams.get('state')||'',code=u.searchParams.get('code')||'';
 const stored=getCookie(req,'__Host-yarr_oauth');
 const cleared=cookie('__Host-yarr_oauth','',0);
 if(!authReady(env)||!state||!code||state.length>256||state!==stored)return redirect('/account?login=failed',{'set-cookie':cleared});
 const row=await env.ACCOUNTS.prepare("DELETE FROM oauth_flows WHERE state_hash=? AND expires_at > CURRENT_TIMESTAMP RETURNING nonce,verifier").bind(await digest(state)).first();
 if(!row)return redirect('/account?login=expired',{'set-cookie':cleared});
 try {
  const params=new URLSearchParams({code,client_id:env.GOOGLE_CLIENT_ID,client_secret:env.GOOGLE_CLIENT_SECRET,redirect_uri:SITE+'/auth/google/callback',grant_type:'authorization_code',code_verifier:row.verifier});
  const response=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:params});
  if(!response.ok)return redirect('/account?login=failed',{'set-cookie':cleared});
  const tokens=await response.json();
  const identity=await validateGoogleIdToken(tokens.id_token,env.GOOGLE_CLIENT_ID,row.nonce);
  const id=crypto.randomUUID(),displayName=String(identity.name||'').slice(0,120),email=String(identity.email||'').slice(0,254),avatar=typeof identity.picture==='string'&&identity.picture.startsWith('https://')?identity.picture.slice(0,1000):'';
  await env.ACCOUNTS.prepare("INSERT INTO users(id,google_sub,email,display_name,avatar_url) VALUES(?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email,display_name=excluded.display_name,avatar_url=excluded.avatar_url,updated_at=CURRENT_TIMESTAMP").bind(id,identity.sub,email,displayName,avatar).run();
  const user=await env.ACCOUNTS.prepare("SELECT id FROM users WHERE google_sub=?").bind(identity.sub).first();
  if(!user)throw Error('user_not_saved');
  const session=random();
  await env.ACCOUNTS.prepare("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,datetime('now','+7 days'))").bind(crypto.randomUUID(),user.id,await digest(session)).run();
  const headers=new Headers({'location':'/account','cache-control':'no-store'});
  headers.append('set-cookie',cleared);
  headers.append('set-cookie',cookie('__Host-yarr_session',session,SESSION_SECONDS));
  return new Response(null,{status:303,headers});
 }catch(_){return redirect('/account?login=failed',{'set-cookie':cleared});}
}

function isPrivateIPv4(host) {
 const parts=host.split('.');
 if(parts.length!==4||parts.some(p=>!/^(0|[1-9][0-9]{0,2})$/.test(p)||Number(p)>255))return false;
 const [a,b]=parts.map(Number);
 return a===10||(a===172&&b>=16&&b<=31)||(a===192&&b===168);
}
function localAddress(input) {
 const value=String(input||'').trim();
 if(!value)return '';
 if(value.length>260)throw Error('Local address is too long');
 let url;try{url=new URL(value);}catch(_){throw Error('Enter a local URL including http:// or https://');}
 if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('Local address must be a direct server URL without a path or credentials');
 const host=url.hostname.toLowerCase();
 if(!(isPrivateIPv4(host)||/^[a-z0-9][a-z0-9.-]{0,180}\.local$/.test(host)))throw Error('Use a private network IP or .local hostname for the local address');
 if(url.port&&(!/^[0-9]+$/.test(url.port)||Number(url.port)<1||Number(url.port)>65535))throw Error('Invalid local port');
 return url.origin;
}
function remoteAddress(input) {
 const value=String(input||'').trim();
 if(!value)return '';
 if(value.length>260)throw Error('Remote address is too long');
 let url;try{url=new URL(value);}catch(_){throw Error('Enter a valid remote HTTPS URL');}
 if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/'||url.port)throw Error('Remote address must use HTTPS on port 443, without a path or credentials');
 const host=url.hostname.toLowerCase();
 if(host==='localhost'||host.endsWith('.local')||host.endsWith('.internal')||host.endsWith('.localhost')||host.includes(':')||isPrivateIPv4(host))throw Error('Enter a public HTTPS hostname');
 if(!/^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$/.test(host)||!host.includes('.')||host.split('.').some(s=>!s||s.startsWith('-')||s.endsWith('-')))throw Error('Enter a valid public hostname');
 const p=host.split('.');
 if(p.length===4&&p.every(x=>/^[0-9]+$/.test(x))){ const a=Number(p[0]),b=Number(p[1]);if(a===0||a===10||a===127||a>=224||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127)||(a===192&&b===0)||(a===198&&b>=18&&b<=19))throw Error('Enter a public HTTPS hostname'); }
 return url.origin;
}
async function listServers(env,userId) {
 const result=await env.ACCOUNTS.prepare("SELECT id,display_name,local_url,public_url,status,server_identity,connection_secret_hash,last_seen_at,CASE WHEN last_seen_at>=datetime('now','-150 seconds') THEN 1 ELSE 0 END AS online,created_at FROM servers WHERE owner_user_id=? ORDER BY created_at DESC,id DESC").bind(userId).all();
 return result.results||[];
}
async function serverMutation(req,env,user) {
 if(!user)return json({error:'not_authenticated'},401);
 if(req.headers.get('origin')!==SITE || req.headers.get('sec-fetch-site')==='cross-site')return json({error:'forbidden'},403);
 if(req.method!=='POST')return json({error:'method_not_allowed'},405);
 const type=req.headers.get('content-type')||'';
 if(!type.startsWith('application/x-www-form-urlencoded'))return json({error:'invalid_content_type'},415);
 const body=await req.text();
 if(body.length>2500)return json({error:'request_too_large'},413);
 const data=new URLSearchParams(body),action=data.get('action');
 if(action==='rename'){
  const id=String(data.get('id')||''),name=String(data.get('name')||'').trim();
  if(!/^[a-f0-9-]{36}$/.test(id)||!name||name.length>80)return redirect('/account?server=invalid');
  const result=await env.ACCOUNTS.prepare("UPDATE servers SET display_name=? WHERE id=? AND owner_user_id=?").bind(name,id,user.id).run();
  return redirect('/account?server='+(result.meta.changes?'renamed':'invalid'));
 }
 if(action==='delete'){
  const id=String(data.get('id')||'');
  if(!/^[a-f0-9-]{36}$/.test(id))return redirect('/account?server=invalid');
  const result=await env.ACCOUNTS.prepare("DELETE FROM servers WHERE id=? AND owner_user_id=? AND server_identity IS NULL").bind(id,user.id).run();
  return redirect('/account?server='+(result.meta.changes?'deleted':'protected'));
 }
 return redirect('/account?server=invalid');
}

const CODE_ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function normalizeCode(value){return String(value||'').toUpperCase().replace(/[\s-]/g,'');}
async function pairingStart(req,env){
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return json({error:'content_type'},415);
 const ip=req.headers.get('cf-connecting-ip')||'unknown';
 const bucket=Math.floor(Date.now()/600000),ipHash=await digest(ip);
 await env.ACCOUNTS.prepare("DELETE FROM pairing_rate_limits WHERE (window NOT LIKE 'claim:%' AND CAST(window AS INTEGER)<?) OR (window LIKE 'claim:%' AND CAST(substr(window,7) AS INTEGER)<?)").bind(bucket-2,Math.floor(Date.now()/60000)-20).run();
 await env.ACCOUNTS.prepare("INSERT INTO pairing_rate_limits(ip_hash,window,count) VALUES(?,?,1) ON CONFLICT(ip_hash,window) DO UPDATE SET count=count+1").bind(ipHash,String(bucket)).run();
 const n=await env.ACCOUNTS.prepare("SELECT count FROM pairing_rate_limits WHERE ip_hash=? AND window=?").bind(ipHash,String(bucket)).first();
 if(n.count>15)return json({error:'rate_limited'},429);
 const raw=await req.text();if(raw.length>700)return json({error:'too_large'},413);
 let body;try{body=JSON.parse(raw);}catch(_){return json({error:'invalid_json'},400);}
 const sid=String(body.server_id||''),code=normalizeCode(body.code),secret=String(body.secret||'');
 if(!/^[a-f0-9-]{36}$/.test(sid)||code.length!==16||[...code].some(c=>!CODE_ALPHABET.includes(c))||!/^[A-Za-z0-9_-]{40,100}$/.test(secret))return json({error:'invalid_request'},400);
 // An already-linked server can request credential renewal, but only its existing account owner can approve the code.
 const existing=await env.ACCOUNTS.prepare("SELECT id FROM servers WHERE server_identity=?").bind(sid).first();
 await env.ACCOUNTS.prepare("DELETE FROM pairing_requests WHERE expires_at<CURRENT_TIMESTAMP OR (server_identity=? AND status='pending')").bind(sid).run();
 const value=await env.ACCOUNTS.prepare("INSERT OR IGNORE INTO pairing_requests(code_hash,server_identity,secret_hash,expires_at) VALUES(?,?,?,datetime('now','+10 minutes'))").bind(await digest(code),sid,await digest(secret)).run();
 if(value.meta.changes!==1)return json({error:'retry_code'},409);
 return json({status:'pending',expires_in:600},201);
}
async function pairingStatus(req,env){
 const bearer=req.headers.get('authorization')||'';
 if(!bearer.startsWith('Bearer ')||bearer.length>120)return json({error:'unauthorized'},401);
 const secret=bearer.slice(7);
 if(!/^[A-Za-z0-9_-]{40,100}$/.test(secret))return json({error:'unauthorized'},401);
 const row=await env.ACCOUNTS.prepare("SELECT status,expires_at,owner_user_id,server_identity FROM pairing_requests WHERE secret_hash=?").bind(await digest(secret)).first();
 if(!row)return json({status:'expired'},404);
 if(row.status==='pending'&&row.expires_at<=new Date().toISOString().replace('T',' ').slice(0,19))return json({status:'expired'},410);
 if(row.status==='claimed'){
  const record=await env.ACCOUNTS.prepare("SELECT id FROM servers WHERE server_identity=? AND owner_user_id=?").bind(row.server_identity,row.owner_user_id).first();
  return json({status:record?'paired':'pending',server_id:record?.id||null});
 }
 return json({status:'pending'});
}
async function pairingClaim(req,env,user){
 if(!user)return json({error:'not_authenticated'},401);
 if(req.headers.get('origin')!==SITE || req.headers.get('sec-fetch-site')==='cross-site')return json({error:'forbidden'},403);
 const type=req.headers.get('content-type')||'';
 if(!type.startsWith('application/x-www-form-urlencoded'))return json({error:'content_type'},415);
 const body=await req.text();if(body.length>500)return json({error:'too_large'},413);
 const code=normalizeCode(new URLSearchParams(body).get('code'));
 if(code.length!==16||[...code].some(c=>!CODE_ALPHABET.includes(c)))return redirect('/account?pair=invalid');
 const ipHash=await digest(req.headers.get('cf-connecting-ip')||'unknown'),minute=String(Math.floor(Date.now()/60000));
 await env.ACCOUNTS.prepare("INSERT INTO pairing_rate_limits(ip_hash,window,count) VALUES(?,?,1) ON CONFLICT(ip_hash,window) DO UPDATE SET count=count+1").bind(ipHash,'claim:'+minute).run();
 const attempts=await env.ACCOUNTS.prepare("SELECT count FROM pairing_rate_limits WHERE ip_hash=? AND window=?").bind(ipHash,'claim:'+minute).first();
 if(attempts.count>8)return redirect('/account?pair=slow');
 const hash=await digest(code);
 const request=await env.ACCOUNTS.prepare("SELECT server_identity FROM pairing_requests WHERE code_hash=? AND status='pending' AND expires_at>CURRENT_TIMESTAMP").bind(hash).first();
 if(!request)return redirect('/account?pair=invalid');
 const existing=await env.ACCOUNTS.prepare("SELECT id,owner_user_id FROM servers WHERE server_identity=?").bind(request.server_identity).first();
 if(existing && existing.owner_user_id!==user.id)return redirect('/account?pair=claimed');
 if(!existing){
  const count=await env.ACCOUNTS.prepare("SELECT COUNT(*) AS n FROM servers WHERE owner_user_id=?").bind(user.id).first();
  if(Number(count?.n||0)>=5)return redirect('/account?pair=limit');
 }
 try{
  const statements=[env.ACCOUNTS.prepare("UPDATE pairing_requests SET status='claimed',owner_user_id=? WHERE code_hash=? AND status='pending' AND expires_at>CURRENT_TIMESTAMP").bind(user.id,hash)];
  if(existing){
   statements.push(env.ACCOUNTS.prepare("UPDATE servers SET connection_secret_hash=(SELECT secret_hash FROM pairing_requests WHERE code_hash=? AND owner_user_id=? AND status='claimed'),last_seen_at=NULL WHERE id=? AND owner_user_id=?").bind(hash,user.id,existing.id,user.id));
  }else{
   statements.push(env.ACCOUNTS.prepare("INSERT INTO servers(id,owner_user_id,display_name,status,server_identity,connection_secret_hash) SELECT ?,?,'Yarr Server','paired',server_identity,secret_hash FROM pairing_requests WHERE code_hash=? AND status='claimed' AND owner_user_id=?").bind(crypto.randomUUID(),user.id,hash,user.id));
  }
  const results=await env.ACCOUNTS.batch(statements);
  if(results[0]?.meta?.changes!==1||results[1]?.meta?.changes!==1)return redirect('/account?pair=invalid');
 }catch(_){return redirect('/account?pair=claimed');}
 return redirect('/account?pair=success');
}

async function connectionHeartbeat(req,env){
 if(req.method!=='POST')return json({error:'method_not_allowed'},405);
 const token=req.headers.get('authorization')||'';
 if(!token.startsWith('Bearer ')||token.length>120)return json({error:'unauthorized'},401);
 const credential=token.slice(7);
 if(!/^[A-Za-z0-9_-]{40,100}$/.test(credential))return json({error:'unauthorized'},401);
 const hash=await digest(credential);
 const result=await env.ACCOUNTS.prepare("UPDATE servers SET last_seen_at=CURRENT_TIMESTAMP WHERE connection_secret_hash=? AND status='paired' AND server_identity IS NOT NULL").bind(hash).run();
 if(result.meta.changes!==1)return json({error:'unauthorized'},401);
 return json({status:'accepted',media_access:false});
}
async function accountConnectionStatus(req,env){
 const user=await currentUser(req,env);
 if(!user)return json({error:'not_authenticated'},401);
 const rows=await env.ACCOUNTS.prepare("SELECT id,display_name,status,server_identity IS NOT NULL AS paired,last_seen_at,connection_secret_hash IS NOT NULL AS credential_ready,CASE WHEN last_seen_at>=datetime('now','-150 seconds') THEN 1 ELSE 0 END AS online FROM servers WHERE owner_user_id=? ORDER BY created_at DESC").bind(user.id).all();
 return json({servers:(rows.results||[]).map(s=>({id:s.id,display_name:s.display_name,paired:!!s.paired&&s.status==='paired',online:!!s.online,last_seen_at:s.last_seen_at,credential_ready:!!s.credential_ready})),media_access:false});
}

async function privateTunnelBootstrap(req,env) {
 if(req.method!=='POST')return json({error:'method_not_allowed'},405);
 const value=req.headers.get('authorization')||'';
 if(!value.startsWith('Bearer ')||value.length>120)return json({error:'unauthorized'},401);
 const credential=value.slice(7);
 if(!/^[A-Za-z0-9_-]{40,100}$/.test(credential))return json({error:'unauthorized'},401);
 if(req.headers.get('content-type')?.split(';')[0]!=='application/json')return json({error:'unsupported_type'},415);
 const body=await req.text();
 if(body.length>256)return json({error:'invalid_request'},400);
 let data;try{data=JSON.parse(body);}catch(_){return json({error:'invalid_request'},400);}
 const identity=String(data.server_id||'');
 if(!/^[a-f0-9-]{36}$/.test(identity))return json({error:'invalid_request'},400);
 const hash=await digest(credential);
 const server=await env.ACCOUNTS.prepare("SELECT id,owner_user_id,server_identity,status FROM servers WHERE connection_secret_hash=? AND server_identity=? AND status='paired'").bind(hash,identity).first();
 if(!server)return json({error:'unauthorized'},401);
 // Scoped single-server pilot: do not return this Cloudflare credential to other paired installs.
 if(server.id!==env.YARR_PRIVATE_SERVER_ID||!env.YARR_PILOT_TUNNEL_TOKEN)return json({error:'automatic_tunnel_not_available_for_server'},503);
 return json({status:'ready',tunnel_token:env.YARR_PILOT_TUNNEL_TOKEN,transport:'quic',automatic:true,media_access:false});
}

async function privateVPCHealth(req,env) {
 // Single-server pilot. Later versions provision isolated VPC bindings per installation.
 const user=await currentUser(req,env);
 if(!user)return json({error:'not_authenticated'},401);
 if(!env.YARR_PRIVATE_API||!env.YARR_PRIVATE_SERVER_ID)return json({error:'private_connection_not_configured'},503);
 const server=await env.ACCOUNTS.prepare(
  "SELECT id,server_identity FROM servers WHERE id=? AND owner_user_id=? AND status='paired' AND server_identity IS NOT NULL"
 ).bind(env.YARR_PRIVATE_SERVER_ID,user.id).first();
 if(!server)return json({error:'not_found'},404);
 try{
  const signal=AbortSignal.timeout(5000);
  const identityResponse=await env.YARR_PRIVATE_API.fetch('http://one-eyed-willie:8787/api/server/info',{method:'GET',signal,headers:{accept:'application/json'}});
  if(!identityResponse.ok||!(identityResponse.headers.get('content-type')||'').includes('application/json'))return json({connected:false,reason:'server_identity_unavailable'},502);
  const identity=await identityResponse.json();
  if(identity.server_id!==server.server_identity)return json({connected:false,reason:'wrong_server_identity'},403);
  const remote=await env.YARR_PRIVATE_API.fetch('http://one-eyed-willie:8787/health',{method:'GET',signal,headers:{accept:'application/json'}});
  if(!remote.ok)return json({connected:false,reason:'origin_unavailable'},502);
  const type=remote.headers.get('content-type')||'';
  if(!type.includes('application/json'))return json({connected:false,reason:'unexpected_response'},502);
  const result=await remote.json();
  if(result.application!=='one-eyed-willie'||result.status!=='ok')return json({connected:false,reason:'unexpected_origin'},502);
  return json({connected:true,server_id:server.id,application:'one-eyed-willie',version:String(result.version||'unknown').slice(0,32),media_access:false});
 }catch(_){return json({connected:false,reason:'tunnel_offline_or_unreachable'},503);}
}


async function ownedPrivateServer(req,env){
 const user=await currentUser(req,env);
 if(!user)return {error:json({error:'not_authenticated'},401)};
 if(!env.YARR_PRIVATE_API||!env.YARR_PRIVATE_SERVER_ID)return {error:json({error:'private_connection_unavailable'},503)};
 const server=await env.ACCOUNTS.prepare("SELECT id,server_identity,display_name FROM servers WHERE id=? AND owner_user_id=? AND status='paired' AND server_identity IS NOT NULL").bind(env.YARR_PRIVATE_SERVER_ID,user.id).first();
 if(!server)return {error:json({error:'server_not_found'},404)};
 return {server};
}
async function verifiedOrigin(env,server,signal){
 const r=await env.YARR_PRIVATE_API.fetch('http://one-eyed-willie:8787/api/server/info',{method:'GET',signal,headers:{accept:'application/json', 'accept-encoding':'identity'}});
 if(!r.ok || !(r.headers.get('content-type')||'').includes('json'))throw new Error('origin_identity_unavailable');
 const obj=await r.json();
 if(obj.server_id!==server.server_identity)throw new Error('wrong_origin');
}
const sharedOriginChecks=new Map();
async function verifiedOriginShared(env,server,signal){
 const key=String(server.server_identity);
 let pending=sharedOriginChecks.get(key);
 if(!pending){
  pending=verifiedOrigin(env,server,signal);
  sharedOriginChecks.set(key,pending);
  pending.then(()=>{if(sharedOriginChecks.get(key)===pending)sharedOriginChecks.delete(key);},()=>{if(sharedOriginChecks.get(key)===pending)sharedOriginChecks.delete(key);});
 }
 return pending;
}
// This single-server pilot currently streams media through the Yarr Worker;
// production multi-tenant playback needs a separate authorized data plane.
// Full Yarr Media application pilot. Every request is authorized against the
// Yarr session and the exact paired server; no arbitrary origins or host overrides.
const ORIGIN_BASE='http://one-eyed-willie:8787';
const HOP_HEADERS=new Set(['connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade','host','cookie','authorization','cf-connecting-ip','x-forwarded-for','x-forwarded-host','x-forwarded-proto','x-real-ip','x-yarr-proxy-auth','x-yarr-server-id']);
const RESPONSE_HEADERS=new Set(['content-type','content-length','content-range','accept-ranges','cache-control','etag','last-modified','content-encoding','vary','content-disposition','x-content-type-options']);
async function proxyInstalledApp(req,env,originPath) {
 const owned=await ownedPrivateServer(req,env);
 if(owned.error) {
  if(req.method==='GET'&&!(new URL(req.url)).pathname.startsWith('/api/'))return redirect('/account');
  return owned.error;
 }
 const method=req.method.toUpperCase();
 if(!['GET','HEAD','POST','PUT','PATCH','DELETE'].includes(method))return json({error:'method_not_allowed'},405);
 if(!['GET','HEAD'].includes(method)){
  const origin=req.headers.get('origin');
  const site=req.headers.get('sec-fetch-site');
  if((origin&&origin!==SITE)||(site&&site!=='same-origin')||(!origin&&site!=='same-origin'))return json({error:'forbidden'},403);
 }
 const size=Number(req.headers.get('content-length')||0);
 if(!Number.isFinite(size)||size>32*1024*1024)return json({error:'request_too_large'},413);
 const source=new URL(req.url);
 // The origin host is a compile-time constant. Browser controls only path/query.
 const path=originPath||source.pathname;
 if(!path.startsWith('/')||path.startsWith('//')||path.includes('\\'))return json({error:'invalid_path'},400);
 // Feature gate stays OFF until off-LAN media tests pass.
 // When enabled, never proxy movie bytes through the Cloudflare Worker.
 if(env.YARR_DIRECT_ENABLED==='1'&&method==='GET'&&
    (/^\/api\/watch\/[1-9][0-9]*\/stream$/.test(path)||
     /^\/api\/watch\/[1-9][0-9]*\/transcode$/.test(path)||
     /^\/api\/stream\/hls\/[a-f0-9]{32}\/(?:index\.m3u8|init\.mp4|segment_[0-9]{6}\.(?:ts|m4s))$/.test(path)))
   return json({error:'media_requires_direct_peer'},503);

 // Fail closed for video from the opt-in media test page. If its scoped service
 // worker is absent, never allow the normal Worker to proxy test movie bytes.
 const ref=req.headers.get('referer')||'';
 if(method==='GET'&&ref.startsWith(SITE+'/media-test')&&
   (/^\/api\/watch\/[1-9][0-9]*\/(?:stream|transcode)$/.test(path)||
    /^\/api\/stream\/hls\//.test(path)))
   return json({error:'direct_test_requires_service_worker'},503);
 const upstreamUrl=ORIGIN_BASE+path+source.search;
 const headers=new Headers();
 for(const [key,value] of req.headers){
  const k=key.toLowerCase();
  if(HOP_HEADERS.has(k)||k.startsWith('cf-')||k.startsWith('x-forwarded-'))continue;
  if(['accept','accept-language','accept-encoding','content-type','content-length','range','if-range','if-none-match','if-modified-since','user-agent','x-requested-with'].includes(k))headers.set(k,value);
 }
 headers.set('accept-encoding','identity');
 if(!['GET','HEAD'].includes(method)){
  headers.set('origin',ORIGIN_BASE);
  headers.set('referer',ORIGIN_BASE+'/');
 }
 const identitySignal=AbortSignal.timeout(7000);
 try {
  await verifiedOriginShared(env,owned.server,identitySignal);
  const upstream=await env.YARR_PRIVATE_API.fetch(upstreamUrl,{method,headers,body:['GET','HEAD'].includes(method)?undefined:req.body,redirect:'manual'});
  if(upstream.status>=300&&upstream.status<400){
   const location=upstream.headers.get('location');
   if(!location)return new Response(null,{status:502});
   const target=new URL(location,upstreamUrl);
   if(target.origin!==ORIGIN_BASE)return json({error:'external_redirect_blocked'},502);
   return new Response(null,{status:upstream.status,headers:{location:target.pathname+target.search+target.hash,'cache-control':'private, no-store'}});
  }
  const responseHeaders=new Headers();
  for(const [key,value] of upstream.headers){
   if(RESPONSE_HEADERS.has(key.toLowerCase()))responseHeaders.set(key,value);
  }
  responseHeaders.set('cache-control', method==='GET' && upstream.status===200 && /^image\/(?:jpeg|png|webp|gif|avif|svg\+xml)$/.test((upstream.headers.get('content-type')||'').split(';')[0].toLowerCase()) ? 'private, max-age=120' : 'private, no-store');
  responseHeaders.set('x-content-type-options','nosniff');
  responseHeaders.set('referrer-policy','same-origin');
  responseHeaders.set('x-frame-options','DENY');
  const mime=(upstream.headers.get('content-type')||'').split(';')[0].toLowerCase();
  if(mime==='text/html'){
   // Existing local page uses inline scripts and absolute /assets and /api URLs.
   responseHeaders.set('content-security-policy',"default-src 'self' data: blob: https:; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
  }
  // Legacy server builds redirect playback from ANY workers.dev host to an old
  // sslip.io HTTPS origin. Normalize that one player condition for Yarr while
  // installations update; do not rewrite any other application scripts or media.
  if(path==='/assets/player.js'&&method==='GET'&&upstream.ok&&
     (mime==='text/javascript'||mime==='application/javascript')){
   const script=await upstream.text();
   if(script.length>180000)return json({error:'player_script_too_large'},502);
   const legacy="if(location.hostname.endsWith('.workers.dev')){";
   const corrected="if(location.hostname.endsWith('.workers.dev') && !/^yarr\\./i.test(location.hostname) && !/^app-yarr\\./i.test(location.hostname)){";
   const fixed=script.includes(legacy)?script.replace(legacy,corrected):script;
   responseHeaders.delete('content-length');
   responseHeaders.delete('content-encoding');
   responseHeaders.set('cache-control','private, no-store');
   return new Response(fixed,{status:200,headers:responseHeaders});
  }
  if(env.YARR_DIRECT_ENABLED==='1'&&method==='GET'&&upstream.ok&&mime==='text/html'){
   const htmlBody=await upstream.text();
   if(htmlBody.length>650000)return json({error:'html_too_large_for_direct_client'},502);
   const tag='<script src="/assets/yarr-direct-client.js" defer></script>';
   const output=htmlBody.includes('</body>')?
     htmlBody.replace('</body>',tag+'</body>'):htmlBody+tag;
   responseHeaders.delete('content-length');
   responseHeaders.delete('content-encoding');
   responseHeaders.set('cache-control','private, no-store');
   return new Response(output,{status:upstream.status,headers:responseHeaders});
  }
  // Keep video, HLS, images and HTTP Range responses streamed, not buffered.
  return new Response(method==='HEAD'||[204,205,304].includes(upstream.status)?null:upstream.body,{status:upstream.status,headers:responseHeaders});
 }catch(_){return json({error:'private_server_unavailable'},503);}
}


const YARR_TEST_PAGE="<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Yarr Media direct connection test</title><style>body{font:16px system-ui,sans-serif;background:#0c101b;color:#f4f2ef;max-width:680px;padding:40px 22px;margin:auto}h1{font-size:35px}p{line-height:1.55;color:#bfc4cc}a{color:#ba9dff}button{border:0;background:#9e84eb;color:#141020;padding:14px 18px;font:700 16px system-ui;border-radius:8px;cursor:pointer}button:disabled{opacity:.5}pre{white-space:pre-wrap;word-break:break-word;line-height:1.55;background:#252b38;padding:20px;border-radius:8px}small{color:#bfc4cc}</style></head><body><a href=\"/app\">Yarr</a><h1>Direct connection test</h1><p>Check whether your current Wi-Fi can exchange encrypted test data directly with your home Yarr server. No videos or personal files are accessed. Cloudflare carries only the connection setup.</p><button id=\"go\">Test connection</button><pre id=\"out\" role=\"status\" aria-live=\"polite\">Ready.</pre><small>The working Yarr video player is not changed by this test.</small><script>\n(()=>{'use strict';const btn=document.getElementById('go'),out=document.getElementById('out');const log=s=>{out.textContent+='\\n'+s};\nconst candidates=sdp=>{const list=(sdp||'').split(/\\r?\\n/).filter(x=>x.startsWith('a=candidate:'));return {total:list.length,host:list.filter(x=>/ typ host(?: |$)/.test(x)).length,srflx:list.filter(x=>/ typ srflx(?: |$)/.test(x)).length,relay:list.filter(x=>/ typ relay(?: |$)/.test(x)).length}};\nconst explain=pc=>{if(!pc)return 'No peer connection was initialized';const local=candidates(pc.localDescription?.sdp),remote=candidates(pc.remoteDescription?.sdp);return 'ICE='+pc.iceConnectionState+'; peer='+pc.connectionState+'; signaling='+pc.signalingState+'; gathering='+pc.iceGatheringState+'; candidates local='+JSON.stringify(local)+' remote='+JSON.stringify(remote)};\nfunction waitIce(pc){return new Promise((ok,no)=>{if(pc.iceGatheringState==='complete')return ok();const timer=setTimeout(()=>no(Error('STUN candidate discovery timed out')),25000);pc.addEventListener('icegatheringstatechange',function fn(){if(pc.iceGatheringState==='complete'){clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',fn);ok()}})})}\nasync function route(pc){const stats=await pc.getStats();const t=[...stats.values()].find(s=>s.type==='transport'&&s.selectedCandidatePairId);const pair=(t&&stats.get(t.selectedCandidatePairId))||[...stats.values()].find(s=>s.type==='candidate-pair'&&s.nominated&&s.state==='succeeded');if(!pair)return 'Candidate path was not reported';const l=stats.get(pair.localCandidateId),r=stats.get(pair.remoteCandidateId),a=l?.candidateType||'unknown',b=r?.candidateType||'unknown';return 'ICE path: '+a+' / '+b+(a==='relay'||b==='relay'?' (relayed)':' (no TURN relay)')}\nbtn.onclick=async()=>{btn.disabled=true;out.textContent='Starting encrypted connection…';let pc;try{\npc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});const dc=pc.createDataChannel('yarr-network-probe-v1');dc.binaryType='arraybuffer';pc.addEventListener('iceconnectionstatechange',()=>log('ICE state: '+pc.iceConnectionState));pc.addEventListener('connectionstatechange',()=>log('Peer state: '+pc.connectionState));dc.addEventListener('close',()=>log('Data channel closed'));let size=0,received=0,good=true;const begin=performance.now();\nconst done=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Peer data transfer timed out')),45000);dc.onopen=()=>{log('Peer connected; testing 256 KiB');dc.send('test')};dc.onerror=()=>reject(Error('Data-channel error'));dc.onmessage=({data})=>{if(typeof data==='string'){const obj=JSON.parse(data);if(obj.type==='start')size=obj.length;else if(obj.type==='done'){clearTimeout(timer);resolve()}}else{const bytes=new Uint8Array(data);for(let i=0;i<bytes.length;i++)if(bytes[i]!==((received+i)%251))good=false;received+=bytes.length}}});\nawait pc.setLocalDescription(await pc.createOffer());await waitIce(pc);log('Negotiating with the paired home server…');\nconst res=await fetch('/api/network-test/offer',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'content-type':'application/json'},body:JSON.stringify({type:'offer',sdp:pc.localDescription.sdp})});\nif(!res.ok)throw Error('Home diagnostic unavailable (HTTP '+res.status+')');\nconst answer=await res.json();log('Diagnostic backend: '+(answer.diagnostic_origin||'unknown; server may be on an older version'));log('Home server answer: '+JSON.stringify(candidates(answer.sdp)));await pc.setRemoteDescription({type:answer.type,sdp:answer.sdp});log('Answer accepted; waiting for ICE and the data channel…');await done;\nif(!good||received!==262144||size!==262144)throw Error('Test data integrity mismatch ('+received+' bytes)');\nlog('PASS: '+received+' correct bytes in '+Math.round(performance.now()-begin)+' ms');log(await route(pc));log('Synthetic-data connectivity verified; real media playback not yet proven.');\n}catch(e){log('FAILED: '+(e?.message||String(e)));log('Diagnostics: '+explain(pc));log('If ICE stays checking or failed, the internet connections may block direct UDP. This does not mean your Yarr sign-in or Cloudflare connection is broken.')}finally{pc?.close();btn.disabled=false}};\n})();\n</script></body></html>";
const YARR_MEDIA_TEST_PAGE="<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Yarr Media • Direct movie playback test</title>\n<style>\nbody{font:16px system-ui,sans-serif;background:#0c101b;color:#f4f2ef;max-width:920px;padding:30px 18px;margin:auto}\nh1{font-size:30px}p,small{color:#bfc4cc;line-height:1.5}a{color:#ba9dff}\ninput{background:#1d2533;color:white;border:1px solid #64708b;padding:12px;border-radius:8px;max-width:150px;font-size:16px}\nbutton{border:0;background:#9573dc;color:#141020;padding:12px 18px;font:700 16px system-ui;border-radius:8px;cursor:pointer;margin:0 10px 10px 0}\nbutton:disabled{opacity:.4;cursor:not-allowed}video{width:100%;max-height:60vh;background:#000;border-radius:10px;margin:10px 0}\npre{white-space:pre-wrap;word-break:break-word;line-height:1.5;background:#202a3b;padding:16px;border-radius:10px}\nlabel{display:block;margin:12px 0}strong{color:#f4f2ef}\n</style>\n<script>window.YARR_DIRECT_TEST_MODE=true;</script>\n<script src=\"/assets/yarr-direct-client.js\" defer></script>\n</head><body>\n<a href=\"/app\">Back to Yarr</a>\n<h1>Direct movie playback test</h1>\n<p>This test streams video directly from your home server over WebRTC UDP 3478. The normal Yarr movie player is unchanged. Use a <strong>browser-playable MP4</strong> movie from your library to test video and seeking. Other formats will be tested separately.</p>\n<p>Find the media ID in the normal Yarr watch URL, for example <code>/watch/42</code> means ID <code>42</code>.</p>\n<label for=\"id\">Movie ID <input id=\"id\" type=\"number\" min=\"1\" step=\"1\" placeholder=\"42\" inputmode=\"numeric\"></label>\n<button id=\"play\" disabled>Play direct</button>\n<button id=\"seek\" disabled>Seek +60 seconds</button>\n<button id=\"stop\" disabled>Stop</button>\n<video id=\"video\" controls preload=\"none\" playsinline></video>\n<pre id=\"status\" role=\"status\" aria-live=\"polite\">Connecting direct peer…</pre>\n<small>Only use this test when your home server is running the experimental direct-media pilot. No normal video playback is changed.</small>\n<script>\n(()=>{'use strict';\nconst video=document.getElementById('video'),out=document.getElementById('status'),id=document.getElementById('id'),\n play=document.getElementById('play'),seek=document.getElementById('seek'),stop=document.getElementById('stop');\nconst log=txt=>{out.textContent+='\\n'+txt};\nfunction status(msg){log('Peer: '+msg);play.disabled=msg!=='connected';}\nwindow.addEventListener('yarr:peer:status',event=>status(event.detail));\nwindow.addEventListener('yarr:peer:bytes',event=>{document.title='Direct test: '+Math.round(event.detail/1024)+' KiB received';});\nif(window.YarrDirectPeerStatus)status(window.YarrDirectPeerStatus);\nplay.onclick=()=>{\n const number=Number(id.value);\n if(!Number.isSafeInteger(number)||number<1){log('Enter the numeric media ID from your /watch/<id> URL');return}\n window.YarrDirectTestBytes=0;\n video.src='/api/watch/'+number+'/stream?viewing=direct-pilot';\n video.load();\n video.play().then(()=>log('Video playing directly through peer')).catch(e=>log('Play: '+e.message));\n stop.disabled=false;seek.disabled=true;log('Opening movie '+number+' over direct WebRTC; watching for video bytes…');\n};\nseek.onclick=()=>{\n if(!Number.isFinite(video.duration)){log('Duration unavailable; cannot seek yet');return}\n const from=video.currentTime,to=Math.min(Math.max(0,video.duration-1),from+60);\n if(to<=from){log('Already near the end');return}\n video.currentTime=to;log('Seeking '+Math.round(from)+'s → '+Math.round(to)+'s over WebRTC');\n};\nstop.onclick=()=>{video.pause();video.removeAttribute('src');video.load();seek.disabled=true;stop.disabled=true;log('Stopped');};\nvideo.addEventListener('loadedmetadata',()=>{log('Metadata received; duration '+Math.round(video.duration)+'s');seek.disabled=!Number.isFinite(video.duration)});\nvideo.addEventListener('seeking',()=>log('Video seeking…'));\nvideo.addEventListener('seeked',()=>log('Seek completed at '+Math.round(video.currentTime)+'s'));\nvideo.addEventListener('playing',()=>log('Video playing; '+(window.YarrDirectTestBytes||0)+' direct peer bytes received so far'));\nvideo.addEventListener('error',()=>log('Video failed: '+(video.error?.message||'unsupported codec or media request failed')+'; peer bytes '+(window.YarrDirectTestBytes||0)));\nsetInterval(()=>{if(!video.paused&&video.readyState>0)out.dataset.bytes=String(window.YarrDirectTestBytes||0)},1000);\n})();\n</script></body></html>";
async function directPeerOffer(req,env){
 if(env.YARR_DIRECT_ENABLED!=='1'&&(new URL(req.url)).pathname!=='/api/yarr/direct/test-offer')return json({error:'direct_media_disabled'},404);
 if(req.headers.get('origin')!==SITE)return json({error:'forbidden'},403);
 const owned=await ownedPrivateServer(req,env);
 if(owned.error)return owned.error;
 if(!env.YARR_PILOT_TUNNEL_TOKEN)return json({error:'direct_peer_not_configured'},503);
 const size=Number(req.headers.get('content-length')||0);
 if(!Number.isFinite(size)||size>72000)return json({error:'request_too_large'},413);
 const body=await req.text();
 if(body.length>72000)return json({error:'request_too_large'},413);
 let parsed;try{parsed=JSON.parse(body)}catch(_){return json({error:'invalid_offer'},400)}
 if(parsed?.type!=='offer'||typeof parsed.sdp!=='string'||parsed.sdp.length>65536||parsed.sdp.length===0)
   return json({error:'invalid_offer'},400);
 // Do not reuse or expose the tunnel token; derive an independent key.
 const raw='yarr-direct-offer-v1'+String.fromCharCode(0)+env.YARR_PILOT_TUNNEL_TOKEN;
 const keyBytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));
 const secret=Array.from(new Uint8Array(keyBytes)).map(n=>n.toString(16).padStart(2,'0')).join('');
 try{
  await verifiedOrigin(env,owned.server,AbortSignal.timeout(7000));
  const upstream=await env.YARR_PRIVATE_API.fetch(ORIGIN_BASE+'/api/yarr/direct/offer',{
   method:'POST',
   headers:{'content-type':'application/json','x-yarr-direct-secret':secret},
   body:JSON.stringify(parsed),redirect:'manual',signal:AbortSignal.timeout(20000)
  });
  if(!(upstream.headers.get('content-type')||'').includes('application/json'))
   return json({error:'unexpected_direct_offer_response'},502);
  if(!upstream.ok)return json({error:'direct_peer_offer_unavailable',status:upstream.status},upstream.status===403?503:upstream.status);
  const result=await upstream.json();
  if(result?.type!=='answer'||typeof result.sdp!=='string'||result.sdp.length>65536)
    return json({error:'invalid_direct_answer'},502);
  return json({type:'answer',sdp:result.sdp});
 }catch(_){return json({error:'direct_peer_origin_unreachable'},503)}
}
async function yarrWifiOffer(req,env){
 if(req.headers.get('origin')!==SITE)return json({error:'forbidden'},403);
 const owned=await ownedPrivateServer(req,env);if(owned.error)return owned.error;
 if(!env.YARR_PILOT_TUNNEL_TOKEN)return json({error:'not_configured'},503);
 const size=Number(req.headers.get('content-length')||0);
 if(!Number.isFinite(size)||size>42000)return json({error:'invalid_length'},413);
 const raw=await req.text();if(raw.length>42000)return json({error:'offer_too_large'},413);
 let offer;try{offer=JSON.parse(raw)}catch(_){return json({error:'bad_offer'},400)}
 if(offer?.type!=='offer'||typeof offer.sdp!=='string'||offer.sdp.length<20||offer.sdp.length>32768)return json({error:'bad_offer'},400);
 const salt='yarr-ice-diagnostic-v1'+String.fromCharCode(0)+env.YARR_PILOT_TUNNEL_TOKEN;
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(salt));
 const secret=Array.from(new Uint8Array(hash)).map(x=>x.toString(16).padStart(2,'0')).join('');
 try{
  await verifiedOrigin(env,owned.server,AbortSignal.timeout(7000));
  const upstream=await env.YARR_PRIVATE_API.fetch('http://one-eyed-willie:8787/api/yarr/ice-probe/offer',{
   method:'POST',headers:{'content-type':'application/json','x-yarr-ice-key':secret},
   body:JSON.stringify(offer),redirect:'manual',signal:AbortSignal.timeout(30000)});
  if(!upstream.ok)return json({error:'origin_not_ready',status:upstream.status},503);
  const answer=await upstream.json();
  if(answer?.type!=='answer'||typeof answer.sdp!=='string'||answer.sdp.length>32768)return json({error:'invalid_answer'},502);
  return json({type:'answer',sdp:answer.sdp,diagnostic_origin:
    answer.diagnostic_origin==='host-network-sidecar'?'host-network-sidecar':
    answer.diagnostic_origin==='docker-bridge'?'docker-bridge':'older-server-unidentified'});
 }catch(_){return json({error:'home_server_unreachable'},503)}
}

function serverCardsHTML(servers) {
 if(!servers.length)return '<div class="account-empty"><div class="empty-emblem" aria-hidden="true">◇</div><h3>No connected servers yet</h3><p>Connect your home media server using a pairing code to manage it here.</p><a class="account-secondary" href="#pair-server">Pair your first server</a></div>';
 return '<div class="account-server-list">'+servers.map(s=>{
  const linked=s.status==='paired'&&!!s.server_identity;
  const state=linked?(s.online?'Online':'Offline'):'Not paired';
  const statusClass=linked?(s.online?'status-online':'status-offline'):'status-unpaired';
  const description=linked?(s.online?'Connected and reporting securely.':s.connection_secret_hash?'Paired, but not currently reporting.':'Paired. Reconnect in your server settings to restore reporting.'):'Registration only — no installed server is paired.';
  const rename='<form method="post" action="/account/servers" class="account-form"><input type="hidden" name="action" value="rename"><input type="hidden" name="id" value="'+escapeHTML(s.id)+'"><label for="server-name-'+escapeHTML(s.id)+'">Server name</label><div class="account-form-row"><input id="server-name-'+escapeHTML(s.id)+'" required maxlength="80" name="name" value="'+escapeHTML(s.display_name)+'"><button class="account-secondary" type="submit">Save name</button></div></form>';
  const remove=linked?'':'<form method="post" action="/account/servers" class="account-remove"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="'+escapeHTML(s.id)+'"><button class="account-text-button" type="submit">Remove unused registration</button></form>';
  return '<article class="account-server"><div class="account-server-header"><div><h3>'+escapeHTML(s.display_name)+'</h3><p class="account-note">'+description+'</p></div><span class="server-status '+statusClass+'"><span class="status-dot" aria-hidden="true"></span>'+state+'</span></div><details class="account-manage"><summary>Manage server</summary><div class="account-manage-body">'+rename+remove+'</div></details></article>';
 }).join('')+'</div>';
}
function accountHTML(user,enabled,message='',servers=[]) {
 const signedIn=!!user,title=signedIn?'My Account':'Sign in to Yarr Media';
 const paired=servers.filter(s=>s.status==='paired'&&!!s.server_identity),online=paired.filter(s=>!!s.online);
 const feedback=message?'<div class="account-feedback" role="status">'+escapeHTML(message)+'</div>':'';
 const main=signedIn?
  '<div class="account-top"><div><p class="account-kicker">Account overview</p><h1>My Account</h1><p class="account-subtitle">Manage your profile and connected home servers.</p></div></div>'+
  feedback+
  '<div class="account-dashboard">'+
  '<div class="account-primary-column">'+
   '<section class="account-panel" id="profile"><div class="panel-top"><div><p class="account-kicker">Profile</p><h2>Account details</h2></div><span class="account-label">Google account</span></div><div class="account-profile"><div class="account-avatar" aria-hidden="true">'+escapeHTML((user.display_name||user.email||'Y').trim().charAt(0).toUpperCase())+'</div><div><strong>'+escapeHTML(user.display_name||'Yarr Media member')+'</strong><p>'+escapeHTML(user.email||'')+'</p></div></div><div class="account-profile-actions"><span>Your account is used to identify and pair your servers.</span><form method="post" action="/auth/logout"><button type="submit" class="account-text-button">Sign out</button></form></div></section>'+
   '<section class="account-panel" id="servers"><div class="panel-top"><div><p class="account-kicker">My library connections</p><h2>Connected servers</h2></div><span class="account-count">'+servers.length+' total</span></div>'+
    '<div class="account-stats"><div><strong>'+paired.length+'</strong><span>Paired</span></div><div><strong>'+online.length+'</strong><span>Online</span></div><div><strong>'+servers.length+'</strong><span>Registered</span></div></div>'+
    serverCardsHTML(servers)+'</section>'+
  '</div>'+
  '<aside class="account-aside"><section class="account-panel account-pair-panel" id="pair-server"><div class="panel-top"><div><p class="account-kicker">Add a connection</p><h2>Pair a server</h2></div></div><p class="account-note">On your installed Yarr Media server, open <strong>Settings → General → Connect to Yarr</strong>, then enter the pairing code here.</p><form class="account-form" method="post" action="/account/pair"><label for="pairing-code">Pairing code</label><input id="pairing-code" name="code" required maxlength="22" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-XXXX-XXXX"><button class="account-submit" type="submit">Pair server</button></form><p class="account-small">Pairing links your installation to this account. Remote access is a planned Pro feature and is not enabled by pairing alone.</p></section>'+
   '<section class="account-panel account-help"><p class="account-kicker">About your plan</p><h2>Yarr Media preview</h2><p class="account-note">Your personal libraries are hosted on your server. Pro remote access is still in development.</p><a href="/free-vs-pro" class="account-secondary">Compare Free and Pro</a></section></aside></div>'
  :
  '<div class="account-signin"><p class="account-kicker">Your Yarr Media account</p><h1>Sign in</h1><p class="account-subtitle">Connect your home server to your account, review paired devices and manage your library connections.</p>'+feedback+
   '<div class="account-panel account-login"><h2>Continue to your account</h2><p class="account-note">Use your Google account to sign in securely.</p>'+
   (enabled?'<a class="account-submit" href="/auth/google/start">Continue with Google</a>':'<p class="account-note">Google Sign-In is being configured. Account creation is not available yet.</p>')+
   '<p class="account-small">Your media stays on your own server. Remote playback is still in development.</p></div></div>';
 return siteChrome('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+title+' — Yarr Media</title><style>'+accountCSS+'</style></head><body><div class="wrap"><nav class="nav"><a href="/" class="brand">YARR MEDIA</a><a href="/" class="link">Home</a></nav><main class="account-main">'+main+'</main><footer class="note">Yarr Media development preview · <a href="/terms">Terms</a> · <a href="/privacy">Privacy</a> · <a href="/cookies">Cookies</a></footer></div></body></html>');
}
const accountCSS = `
.account-main{color:#f5f1e8}.account-main h1,.account-main h2,.account-main h3,.account-main strong{color:#f5f1e8}.account-panel{color:#f5f1e8}.account-panel .account-profile strong{color:#f5f1e8}
.account-main{padding:54px 0 86px;min-height:62vh}.account-main *{box-sizing:border-box}.account-main h1{font-size:clamp(38px,5vw,58px);letter-spacing:-.052em;margin:6px 0 8px;line-height:1.12}.account-main h2{font-size:23px;letter-spacing:-.03em;margin:3px 0 0}.account-main h3{font-size:17px;margin:0 0 6px}.account-main p{margin:0}.account-kicker{color:#e68a8a;text-transform:uppercase;letter-spacing:.15em;font-weight:800;font-size:11px}.account-subtitle{color:#c6beb5;line-height:1.6;font-size:16px}.account-top{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;flex-wrap:wrap;margin-bottom:28px}.account-open,.account-submit{display:inline-flex;justify-content:center;align-items:center;gap:10px;background:#a61e1e;border:1px solid #a61e1e;color:#fff;font:700 14px system-ui,sans-serif;border-radius:9px;text-decoration:none;padding:13px 18px;min-height:47px;cursor:pointer;transition:background .2s,transform .2s}.account-open:hover,.account-submit:hover{background:#c32c2c;transform:translateY(-2px)}
.account-dashboard{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(295px,.85fr);gap:22px;align-items:start}.account-primary-column,.account-aside{display:grid;gap:22px;min-width:0}.account-panel{padding:26px;background:#151515;border:1px solid #ffffff28;border-radius:15px;min-width:0}.panel-top{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:22px;flex-wrap:wrap}.account-label,.account-count{font-size:12px;color:#c9c1b7;border:1px solid #ffffff30;border-radius:50px;padding:6px 10px;white-space:nowrap}
.account-profile{display:flex;align-items:center;gap:16px;min-width:0}.account-profile strong{font-size:18px;display:block;overflow-wrap:anywhere}.account-profile p{color:#b8b0a6;font-size:14px;margin-top:5px;overflow-wrap:anywhere}.account-avatar{height:56px;width:56px;flex:0 0 56px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:24px;font-weight:800;background:linear-gradient(145deg,#ad3535,#5b1414)}.account-profile-actions{display:flex;justify-content:space-between;gap:15px;align-items:center;flex-wrap:wrap;margin-top:24px;padding-top:18px;border-top:1px solid #ffffff1e;color:#a9a29b;font-size:13px}.account-text-button{border:0;padding:5px 0;background:transparent;color:#eca1a1;font:700 13px system-ui,sans-serif;cursor:pointer;text-decoration:underline;text-underline-offset:3px}.account-text-button:hover{color:white}
.account-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:24px}.account-stats>div{background:#1e1e1e;border:1px solid #ffffff18;padding:15px;border-radius:10px;display:flex;flex-direction:column;gap:3px}.account-stats strong{font-size:24px}.account-stats span{font-size:12px;color:#bdb4aa}.account-server-list{display:grid;gap:12px}.account-server{border:1px solid #ffffff20;border-radius:11px;padding:18px;background:#191919}.account-server-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}.account-note{font-size:14px;color:#bcb4ab;line-height:1.65}.server-status{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:50px;font-size:12px;font-weight:700;white-space:nowrap}.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor}.status-online{color:#a8e4be;background:#193225}.status-offline{color:#e9c391;background:#332719}.status-unpaired{color:#c9c0b6;background:#303030}
.account-manage{margin-top:16px;padding-top:13px;border-top:1px solid #ffffff1d}.account-manage summary{cursor:pointer;color:#e8d7d2;font-size:13px;font-weight:750;list-style-position:inside}.account-manage-body{margin-top:15px}.account-form{display:grid;gap:10px;margin-top:16px}.account-form label{color:#ddd4ca;font-weight:700;font-size:13px}.account-form input{min-width:0;width:100%;background:#0d0d0d;border:1px solid #ffffff42;border-radius:8px;color:#fff;font:inherit;padding:12px;min-height:46px}.account-form input:focus-visible{outline:2px solid #ec8888;outline-offset:2px}.account-form-row{display:flex;align-items:center;gap:9px}.account-secondary{display:inline-flex;justify-content:center;align-items:center;padding:11px 14px;min-height:42px;border:1px solid #9c5959;border-radius:8px;background:transparent;color:#f5f1e8;text-decoration:none;font:700 13px system-ui,sans-serif;cursor:pointer;white-space:nowrap}.account-secondary:hover{background:#462323}.account-form .account-submit{width:100%;margin-top:5px}.account-remove{margin-top:16px}.account-small{font-size:12px;color:#aaa29b;line-height:1.65;margin-top:17px!important}.account-empty{padding:30px 16px;text-align:center;border:1px dashed #ffffff40;border-radius:12px}.account-empty h3{margin:8px 0}.account-empty p{color:#bcb4ab;line-height:1.6;font-size:14px;margin-bottom:18px}.empty-emblem{font-size:30px;color:#dd8989}.account-feedback{background:#281a1a;border-left:3px solid #a61e1e;border-radius:7px;padding:14px 16px;margin-bottom:24px;color:#f3dbd7;font-size:14px}.account-help h2{margin:10px 0 14px}.account-help .account-secondary{margin-top:20px}.account-signin{max-width:590px;margin:10px auto 0;text-align:center}.account-signin .account-panel{text-align:left;margin-top:30px}.account-signin .account-login h2{margin-bottom:13px}.account-signin .account-login .account-submit{width:100%;margin-top:22px}
@media(max-width:850px){.account-dashboard{grid-template-columns:1fr}.account-main{padding:42px 0 65px}}@media(max-width:520px){.account-panel{padding:20px}.account-stats>div{padding:12px}.account-form-row{flex-direction:column;align-items:stretch}.account-form-row button{width:100%}.account-top .account-open{width:100%}.account-main h1{font-size:40px}}@media(prefers-reduced-motion:reduce){.account-open,.account-submit{transition:none}.account-open:hover,.account-submit:hover{transform:none}}
`;
export default { async fetch(req,env) {
 const u=new URL(req.url);
 try {
  if((req.method==='GET'||req.method==='HEAD')&&u.pathname==='/favicon.svg')return new Response(req.method==='HEAD'?null:YARR_ICON_SVG,{headers:{'content-type':'image/svg+xml; charset=utf-8','cache-control':'public, max-age=3600','x-content-type-options':'nosniff'}});
  if((req.method==='GET'||req.method==='HEAD')&&u.pathname==='/favicon.ico')return redirect('/favicon.svg?v=moon-sail-v1');
  if(req.method==='GET'&&(u.pathname==='/health'||u.pathname==='/__edge/health')) {
   let database='unavailable';try{await env.ACCOUNTS.prepare('SELECT 1 AS ok').first();database='ready'}catch(_){}
   return json({service:'yarr',status:'staging',database,authentication:authReady(env)?'configured':'not_configured',media_proxy:false},database==='ready'?200:503);
  }
  if(req.method==='GET'&&u.pathname==='/robots.txt')return new Response('User-agent: *\nDisallow: /\n',{headers:{'content-type':'text/plain; charset=utf-8'}});
  if(req.method==='GET'&&u.pathname==='/auth/google/start')return googleStart(env);
  if(req.method==='GET'&&u.pathname==='/auth/google/callback')return googleCallback(req,env);
  if(req.method==='POST'&&u.pathname==='/auth/logout') {
   if(req.headers.get('origin')!==SITE)return json({error:'forbidden'},403);
   const token=getCookie(req,'__Host-yarr_session');
   if(token)await env.ACCOUNTS.prepare("DELETE FROM sessions WHERE token_hash=?").bind(await digest(token)).run();
   return redirect('/account',{'set-cookie':cookie('__Host-yarr_session','',0)});
  }
  if(req.method==='POST'&&u.pathname==='/api/connection/heartbeat')return connectionHeartbeat(req,env);
  if(req.method==='GET'&&u.pathname==='/api/connection/status')return accountConnectionStatus(req,env);
  if(req.method==='POST'&&u.pathname==='/api/pairing/start')return pairingStart(req,env);
  if(req.method==='GET'&&u.pathname==='/api/pairing/status')return pairingStatus(req,env);
  if(req.method==='POST'&&u.pathname==='/account/pair')return pairingClaim(req,env,await currentUser(req,env));
  if(req.method==='POST'&&u.pathname==='/account/servers') {
   return serverMutation(req,env,await currentUser(req,env));
  }
  if(req.method==='POST'&&u.pathname==='/api/connection/tunnel/bootstrap')return privateTunnelBootstrap(req,env);
  if(req.method==='GET'&&u.pathname==='/api/private/health')return privateVPCHealth(req,env);
  if(req.method==='GET'&&u.pathname==='/network-test'){
   const owned=await ownedPrivateServer(req,env);if(owned.error)return redirect('/account');
   return new Response(YARR_TEST_PAGE,{status:200,headers:{
    'content-type':'text/html; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff','x-frame-options':'DENY',
    'content-security-policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self' https:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}});
  }
  if(req.method==='POST'&&u.pathname==='/api/network-test/offer')return yarrWifiOffer(req,env);
  if(req.method==='POST'&&u.pathname==='/api/yarr/direct/offer')return directPeerOffer(req,env);
  if(req.method==='POST'&&u.pathname==='/api/yarr/direct/test-offer')return directPeerOffer(req,env);
  if(req.method==='GET'&&u.pathname==='/media-test'){
   const owned=await ownedPrivateServer(req,env);if(owned.error)return redirect('/account');
   return new Response(YARR_MEDIA_TEST_PAGE,{status:200,headers:{
    'content-type':'text/html; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff','x-frame-options':'DENY',
    'content-security-policy':"default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self' blob:; connect-src 'self' https:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
   }});
  }
  if(req.method==='GET'&&u.pathname==='/api/servers'){
   const user=await currentUser(req,env);
   if(!user)return json({error:'not_authenticated'},401);
   return json({servers:(await listServers(env,user.id)).map(s=>({id:s.id,display_name:s.display_name,status:s.status,paired:s.status==='paired'&&!!s.server_identity,online:!!s.online,last_seen_at:s.last_seen_at,credential_ready:!!s.connection_secret_hash,created_at:s.created_at})),verified_access:false});
  }
  if(req.method==='GET'&&u.pathname==='/api/me') {
   const user=await currentUser(req,env);
   if(!user)return json({authenticated:false},401);
   return json({authenticated:true,user});
  }
  if(req.method==='GET'&&u.pathname==='/app') {
   const user=await currentUser(req,env);
   if(!user)return redirect('/account');
   return proxyInstalledApp(req,env,'/');
  }
  if(req.method==='GET'&&u.pathname==='/account') {
   const user=await currentUser(req,env);
   const message=u.searchParams.get('login')?'Sign-in was not completed. Please try again.':'';
   const statuses={renamed:'Server name saved.',deleted:'Unused registration removed.',protected:'Paired servers require a secure unpair flow before removal.',invalid:'Check the server name and try again.'};
   const pairStatuses={success:'Server linked to your account. Remote access is not enabled yet.',invalid:'The pairing code is invalid, expired or already used.',claimed:'That server is already linked. Unpairing is not enabled yet.',slow:'Too many attempts. Try again shortly.',limit:'You can link up to five servers during testing.'};
   const message2=message||pairStatuses[u.searchParams.get('pair')]||statuses[u.searchParams.get('server')]||'';
   const servers=user?await listServers(env,user.id):[];
   return html(accountHTML(user,authReady(env),message2,servers));
  }
  if(req.method==='GET'||req.method==='HEAD') {
   if(u.pathname==='/robots.txt')return new Response(req.method==='HEAD'?null:'User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /account\nDisallow: /api/\nDisallow: /auth/\nSitemap: '+PUBLIC_SITE+'/sitemap.xml\n',{headers:{'content-type':'text/plain; charset=utf-8','cache-control':'public, max-age=3600'}});
   if(u.pathname==='/sitemap.xml')return new Response(req.method==='HEAD'?null:'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+PUBLIC_URLS.map(p=>'<url><loc>'+PUBLIC_SITE+p+'</loc></url>').join('')+'</urlset>',{headers:{'content-type':'application/xml; charset=utf-8','cache-control':'public, max-age=3600'}});
   const info=infoPage(u.pathname);
   if(info)return new Response(req.method==='HEAD'?null:info,{headers:{...HTML_HEADERS,'cache-control':'public, max-age=300'}});
  }
  if(u.pathname.startsWith('/auth/'))return json({error:'not_found'},404);
  if(u.pathname==='/api/private' || u.pathname.startsWith('/api/private/'))return json({error:'not_found'},404);
  // This Worker owns account, login and pairing routes. All other application
  // paths are served by the paired local Yarr Media server.
  if(u.pathname!=='/'&&u.pathname!=='/index.html')return proxyInstalledApp(req,env);
  if(req.method!=='GET'&&req.method!=='HEAD')return json({error:'method_not_allowed'},405);
  if(u.pathname==='/'||u.pathname==='/index.html') {
   const user=await currentUser(req,env);
   // The public product homepage must remain visible even for signed-in users.
   // The media UI is available explicitly at /app; account settings at /account.
   const cta=user?'<a class="btn primary" href="/app">Open App</a>':authReady(env)?'<a class="btn primary" href="/auth/google/start">Sign in with Google</a>':'<a class="btn primary" href="/account">Account setup</a>';
   const rendered=page.replace('<a class="btn primary" href="#setup">See how it works</a>',cta+'<a class="btn" href="#setup">See how it works</a>')
     .replace('Server download & sign-in are coming.','Server downloads are coming.')
     .replace('Public downloads, Google Sign-In, and account-based pairing are not available yet.','Public downloads and account-based server pairing are not available yet.');
   return new Response(req.method==='HEAD'?null:siteChrome(rendered),{headers:{...HTML_HEADERS,'cache-control':'private, no-store'}});
  }
  return json({error:'not_found'},404);
 }catch(_) {return json({error:'temporarily_unavailable'},503);}
}};
