import {ownerAllowed,ownerPage,ownerNotFound} from './owner-dashboard.js';
import {handleSupportMail,receiveSupportMail} from './support-mail.js';
import {createProCheckout,proStripeWebhook,proCheckoutAvailable} from './stripe-checkout.js';
import {oneTimeProEnabled,oneTimeProActive} from './entitlements.js';
import {how2Html,HOW2_PATHS} from './how2s.js';
// Yarr Media production public site and account control plane.
// Media stays on the owner\u0027s server; the public Worker does not store movies.
const JSON_HEADERS = {'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'};
const HTML_HEADERS = {'content-type':'text/html; charset=utf-8','cache-control':'public, max-age=300','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; img-src 'self' https://raw.githubusercontent.com; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"};
// First-party Yarr Media logo and favicon.
const YARR_ICON_SVG = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 900 900\" role=\"img\" aria-label=\"Yarr Media moon, pirate sail and waves\"><path fill=\"#fff\" d=\"M34,808 78,809 193,798 254,798 313,805 395,823 445,832 490,837 527,838 572,835 613,829 695,809 751,800 776,798 821,798 855,801 868,804 873,803 833,790 794,782 766,779 722,779 684,784 628,797 592,803 562,806 506,806 447,797 381,779 339,770 303,765 251,763 213,766 178,772 84,797Z M285,129 246,152 216,174 194,193 162,227 140,256 122,285 108,313 92,355 82,393 77,424 77,493 83,529 89,552 103,591 120,626 147,668 173,700 198,725 232,753 288,747 313,686 337,639 363,596 401,543 455,481 521,419 574,380 598,366 634,349 667,339 683,337 683,339 668,349 653,363 640,381 630,409 628,432 609,437 589,452 558,463 587,477 620,482 618,492 618,518 621,536 626,552 635,571 648,590 660,602 672,610 665,611 633,605 613,608 602,614 596,619 596,621 609,622 624,628 608,634 596,645 596,647 608,650 624,659 637,672 627,675 650,690 673,716 670,717 620,697 565,683 521,677 467,677 440,680 410,686 370,699 352,707 331,720 317,732 307,745 392,750 451,759 559,779 623,782 657,760 683,739 711,712 737,682 761,648 775,624 791,590 804,553 811,524 816,491 817,443 815,418 811,391 803,357 790,320 776,290 755,255 736,229 706,195 687,177 656,152 632,136 593,116 561,104 531,96 494,90 462,88 426,89 383,95 354,102 329,110Z\"/></svg>";
const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yarr Media | Self-Hosted Movie &amp; TV Server</title>
<meta name="description" content="Organize and stream your own movies and TV shows with Yarr Media. Free self-hosted media server, Google TV app, and $29 one-time Pro remote access.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Yarr Media">
<meta property="og:title" content="Yarr Media — Your media. Your server.">
<meta property="og:description" content="Your own movies and television on a media server you control.">
<meta property="og:url" content="https://yarr.media/">
<meta property="og:image" content="https://yarr.media/assets/yarr-media-og-v2.jpg">
<meta property="og:image:secure_url" content="https://yarr.media/assets/yarr-media-og-v2.jpg">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Yarr Media moon and sail above an off-white and crimson YARR.MEDIA wordmark on black">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Yarr Media — Your media. Your server.">
<meta name="twitter:description" content="Your own movies and shows on your server.">
<meta name="twitter:image" content="https://yarr.media/assets/yarr-media-og-v2.jpg">
<meta name="robots" content="index,follow"><link rel="canonical" href="https://yarr.media/">
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
<main><section class="hero"><div class="hero-copy"><div class="eyebrow">Self-hosted movies &amp; television</div><h1>Your media.<br><em>Your rules.</em></h1><p class="lead">Give your personal movie and TV collection a home. Organize your libraries, browse rich details, and watch from a server you control.</p><p class="sublead">Start free at home, then unlock account-linked remote access with Yarr Media Pro for a one-time $29 purchase.</p><div class="actions"><a class="btn primary" href="#setup">See how it works</a><a class="btn" href="#plans">Compare Free &amp; Pro</a></div></div><img class="hero-art" src="https://raw.githubusercontent.com/blarkin13/one-eyed-willie/main/server/new%20logo.png" alt="Yarr Media pirate ship"></section>
<section id="features" class="section reveal"><div class="eyebrow">One collection. One place.</div><h2>Everything you need for your own library.</h2><p class="section-intro">Build a personal media experience without giving up control of your files.</p><div class="features">
<div class="tile"><b>01 / ORGANIZE</b><h3>Beautiful movie &amp; TV libraries</h3><p>Browse posters, cast, episodes, ratings and available metadata.</p></div>
<div class="tile"><b>02 / WATCH</b><h3>Play from your own server</h3><p>Enjoy local playback with your existing files and storage.</p></div>
<div class="tile"><b>03 / CONNECT</b><h3>Optional integrations</h3><p>Connect services like Radarr, Sonarr and SABnzbd to help manage your collection.</p></div></div></section>
<section id="plans" class="section reveal"><div class="eyebrow">Choose your experience</div><h2>Free at home. Pro wherever you go.</h2><p class="section-intro">Both versions are built around your own media server. The Pro upgrade adds account-linked remote access outside your home network.</p>
<div class="plans"><article class="plan"><div class="plan-head"><h3>Free</h3></div><div class="plan-price">Free local use</div><p class="plan-desc">A complete personal library experience on your home network.</p><ul>
<li>Self-host your media server</li><li>Organize movies, shows, seasons and episodes</li><li>Browse available artwork, cast and metadata</li><li>Stream on your home network</li><li>Optional library integrations</li><li class="unavailable">Remote access outside your home</li></ul><a class="btn" href="#setup">Learn about setup</a></article>
<article class="plan pro"><div class="plan-head"><h3>Pro</h3><span class="plan-label">One-time purchase</span></div><div class="plan-price">$29 one-time, plus applicable tax</div><p class="plan-desc">Everything in Free, with secure access to your home library while you're away.</p><ul>
<li>Everything included in Free</li><li>Account-linked remote access outside your home network</li><li>Watch your own library while traveling on supported devices</li><li>Account-linked server connection</li><li>Local media stays on your own server</li></ul><a class="btn primary" href="/account">Buy Pro — $29</a><p class="footnote">Remote access depends on your server, internet connection, and device compatibility.</p></article></div></section>
<section id="setup" class="section reveal"><div class="eyebrow">How it works</div><h2>Your server. Three simple steps.</h2><div class="steps">
<div class="tile"><b>01 / INSTALL</b><h3>Run your server</h3><p>Host Yarr Media on compatible home hardware with your own storage.</p></div>
<div class="tile"><b>02 / ORGANIZE</b><h3>Add your collections</h3><p>Choose media folders and let Yarr Media assemble your libraries.</p></div>
<div class="tile"><b>03 / ENJOY</b><h3>Watch locally</h3><p>Stream on your home network. Pro remote connectivity is being developed.</p></div></div></section>
<section id="availability" class="section reveal"><div class="eyebrow">Get Yarr Media</div><h2>Yarr Media downloads are available.</h2><div class="launch"><strong>Install the server and Google TV app from the Downloads section below.</strong><p>Self-host Yarr Media for free, or purchase Pro for account-linked remote access. Media files are not included.</p></div></section></main>
<footer class="footer"><div><div class="footer-title">Yarr Media</div><div>Your collection. Your server.</div><small>Free local streaming. Optional $29 one-time Pro upgrade.</small></div><div><div class="footer-title">Product</div><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/remote-access">Remote access</a><a href="/how-it-works">How it works</a><a href="/how2s">Setup guides</a></div><div><div class="footer-title">Account</div><a href="/account">My Account</a><a href="/app">Open App</a></div><div><div class="footer-title">Legal</div><a href="/terms">Terms of Use</a><a href="/privacy">Privacy Policy</a><a href="/cookies">Cookie Policy</a><a href="/refunds">Refund Policy</a></div></footer>
</div></body></html>`;



const APK_URL = "https://github.com/blarkin13/one-eyed-willie/releases/latest/download/yarr-media-google-tv.apk";
const PHONE_APK_URL = "https://github.com/blarkin13/one-eyed-willie/releases/latest/download/yarr-media-android.apk";
const DOWNLOADS_PLACEHOLDERS = '<section id="downloads" class="section reveal" aria-labelledby="downloads-title"><div class="eyebrow">Get Yarr Media</div><h2 id="downloads-title">Downloads</h2><p class="section-intro">Install the server on the computer that holds your media, then watch on your TV or in any browser.</p><div class="features"><article class="tile"><b>SERVER · LINUX</b><h3>One-line install</h3><p>On Ubuntu, Debian or another Linux computer (Intel or ARM), run:</p><p><code style="display:block;margin:12px 0;padding:12px;border-radius:8px;background:#0a0a0a;border:1px solid #ffffff2a;color:#f5f1e8;font:13px ui-monospace,monospace;overflow-wrap:anywhere;user-select:all">curl -fsSL https://yarr.media/install.sh | sudo bash</code></p><p>It sets up Docker if needed, keeps itself updated, and prepares remote access. Or with apt: <a href="/apt">add the Yarr Media repository</a>.</p></article><article class="tile"><b>GOOGLE TV · ANDROID</b><h3>TV and phone apps</h3><p>On a Google TV, open the free Downloader app and enter <strong>yarr.media/tv</strong> (<a href="'+APK_URL+'">TV APK</a>). On an Android phone, open <strong>yarr.media/android</strong> (<a href="'+PHONE_APK_URL+'">phone APK</a>). Sign in to your Yarr account in the app to watch away from home.</p></article><article class="tile"><b>ANY BROWSER</b><h3>app.yarr.media</h3><p>Open <a href="https://app.yarr.media/">app.yarr.media</a> on a phone, tablet or computer. At home it is free; away from home it needs Pro.</p></article></div></section>';
const SITE_HEADER = '<header class="site-header" role="banner"><a href="/" class="site-brand" aria-label="Yarr Media home"><img src="/favicon.svg?v=moon-sail-v1" alt="" aria-hidden="true"><span class="site-brand-label">YARR<span class="brand-dot">.</span><span class="brand-media">MEDIA</span></span></a><nav class="site-nav" aria-label="Main navigation"><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/how-it-works">How it works</a><a href="/#downloads">Downloads</a></nav><div class="site-actions"><a href="/account">My Account</a><a class="site-app-link" href="/app">Open App</a></div></header>';
const SITE_FOOTER = '<footer class="site-footer" role="contentinfo"><div><div class="site-foot-title">Yarr Media</div><div>Your collection. Your server.</div><small>Free local streaming. Optional $29 one-time Pro upgrade.</small></div><div><div class="site-foot-title">Product</div><a href="/features">Features</a><a href="/free-vs-pro">Free vs Pro</a><a href="/remote-access">Remote access</a><a href="/how-it-works">How it works</a><a href="/how2s">Setup guides</a></div><div><div class="site-foot-title">Account</div><a href="/account">My Account</a><a href="/app">Open App</a></div><div><div class="site-foot-title">Legal</div><a href="/terms">Terms of Use</a><a href="/privacy">Privacy Policy</a><a href="/cookies">Cookie Policy</a><a href="/refunds">Refund Policy</a></div></footer>';
const SITE_CHROME_CSS = `
:root{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0a;color:#f5f1e8}html{background:#0a0a0a}body{margin:0;min-height:100vh;background:#0a0a0a;color:#f5f1e8;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}a{color:inherit}.wrap{max-width:1180px;margin:auto;padding:0 24px}
.site-header{max-width:100%;min-height:90px;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 0;border-bottom:1px solid #ffffff29}
.site-header .site-brand{display:flex;align-items:center;gap:12px;white-space:nowrap;text-decoration:none;color:#f5f1e8;font-size:21px;letter-spacing:.075em;font-weight:900}
.site-brand img{height:46px;width:46px;object-fit:contain}.site-header .site-brand .site-brand-label{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:clamp(18px,1.8vw,23px);font-weight:900;letter-spacing:.01em;line-height:1;color:#f5f1e8}.site-header .site-brand .site-wordmark{width:clamp(160px,23vw,255px);height:auto;max-height:76px;object-fit:contain}.site-brand strong{color:#eb8888}
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

/* Unified public and account chrome: same width, spacing, sizing and logo. */
.wrap{width:100%;max-width:1440px;margin-inline:auto;padding-inline:clamp(18px,3vw,48px)}
.site-header{box-sizing:border-box;min-height:118px;padding:18px 0;gap:24px}
.site-header .site-brand .site-wordmark{width:245px;height:76px;max-width:100%;max-height:76px;object-fit:contain}
.site-nav{gap:24px}.site-nav a{font-size:15px;font-weight:600}.site-actions a{font-size:14px;min-height:46px;padding:11px 17px}
.account-main{padding-top:64px}
@media(max-width:1050px){.site-header{min-height:104px;gap:16px}.site-header .site-brand .site-wordmark{width:205px;height:65px}}
@media(max-width:560px){.wrap{padding-inline:16px}.site-header{min-height:88px;padding:14px 0}.site-header .site-brand .site-wordmark{width:168px;height:54px}.site-nav a{font-size:13px}.site-actions a{font-size:12px;min-height:40px;padding:9px 11px}.account-main{padding-top:42px}}
/* Keep shared site header and buttons inside the viewport. */
html,body{max-width:100%}
.wrap{box-sizing:border-box;width:100%;max-width:1440px;margin-inline:auto;padding-inline:clamp(16px,3vw,48px)}
.site-header{box-sizing:border-box;display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;column-gap:clamp(12px,2vw,30px);width:100%;max-width:100%}
.site-header .site-brand{min-width:0;justify-self:start}
.site-header .site-brand .site-wordmark{display:block;width:clamp(150px,17vw,245px);max-width:100%;height:auto;max-height:76px}
.site-nav{min-width:0;justify-content:center;gap:clamp(12px,1.5vw,24px)}
.site-nav a{white-space:nowrap}
.site-actions{justify-self:end;min-width:0;max-width:100%;gap:10px}
.site-actions a{box-sizing:border-box;white-space:nowrap}
@media(max-width:1100px){.site-header{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"brand actions" "nav nav";row-gap:13px;padding-block:16px}.site-header .site-brand{grid-area:brand}.site-nav{grid-area:nav;justify-content:center;width:100%;flex-wrap:wrap}.site-actions{grid-area:actions;justify-self:end}}
@media(max-width:620px){.site-header{gap:12px}.site-header .site-brand .site-wordmark{width:clamp(130px,34vw,185px)}.site-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px}.site-actions a{font-size:12px;padding:8px 10px;min-height:38px}.site-nav{gap:10px 16px;justify-content:center}}
@media(max-width:430px){.site-header{grid-template-columns:1fr;grid-template-areas:"brand" "actions" "nav"}.site-actions{justify-self:stretch;width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.site-actions a{min-width:0;white-space:normal;text-align:center}}
@media(prefers-reduced-motion:reduce){.site-actions a{transition:none}.site-actions a:hover{transform:none}}
/* The wordmark is text (not an image): keep the same accent colors on all pages. */
.site-header .site-brand .site-brand-label{display:inline-block;white-space:nowrap;font-weight:900}
.site-header .site-brand .brand-dot{color:#9b9b9b!important}
.site-header .site-brand .brand-media{color:#c62838!important}
@media(max-width:620px){.site-header .site-brand .site-brand-label{font-size:clamp(17px,4.5vw,23px)}}
`;
/* Shared metadata for every public marketing, legal, and setup-guide page.
   Account and app pages have no public canonical URL and remain noindex. */
const SEO_ARTWORK='https://yarr.media/assets/yarr-media-og-v2.jpg';
const SEO_ORG_ID='https://yarr.media/#organization';
const SEO_WEBSITE_ID='https://yarr.media/#website';
function seoPlain(value){
 return String(value||'').replace(/&amp;/g,'&').replace(/&quot;/g,'"')
  .replace(/&#39;|&apos;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>');
}
function seoEnhance(html){
 const canonical=html.match(/<link rel="canonical" href="(https:\/\/yarr\.media\/[^"]*)">/i)?.[1];
 if(!canonical)return html; // Private account, authentication and app pages.
 const title=seoPlain(html.match(/<title>([^<]+)<\/title>/i)?.[1]||'Yarr Media');
 const description=seoPlain(html.match(/<meta name="description" content="([^"]+)">/i)?.[1]||'Yarr Media is a self-hosted media server for your personal movie and TV libraries.');
 const pathname=new URL(canonical).pathname;
 const org={'@type':'Organization','@id':SEO_ORG_ID,name:'Yarr Media',url:PUBLIC_SITE,
  logo:{'@type':'ImageObject',url:PUBLIC_SITE+'/favicon.svg'}};
 const website={'@type':'WebSite','@id':SEO_WEBSITE_ID,url:PUBLIC_SITE+'/',name:'Yarr Media',
  publisher:{'@id':SEO_ORG_ID},inLanguage:'en-US'};
 const page={'@type':pathname==='/how2s'?'CollectionPage':'WebPage',
  '@id':canonical+'#webpage',url:canonical,name:title,description,
  isPartOf:{'@id':SEO_WEBSITE_ID},inLanguage:'en-US'};
 const graph=[org,website,page];
 if(pathname==='/'){
  graph.push({'@type':'SoftwareApplication',name:'Yarr Media',
   url:PUBLIC_SITE+'/',description,
   applicationCategory:'MultimediaApplication',operatingSystem:'Linux',
   downloadUrl:PUBLIC_SITE+'/install.sh',
   offers:[{'@type':'Offer',name:'Yarr Media Free',price:'0',priceCurrency:'USD',url:PUBLIC_SITE+'/#downloads'},
    {'@type':'Offer',name:'Yarr Media Pro',price:'29',priceCurrency:'USD',url:'https://accounts.yarr.media/'}]});
 }else{
  const crumbs=[{'@type':'ListItem',position:1,name:'Home',item:PUBLIC_SITE+'/'}];
  if(pathname.startsWith('/how2s/'))crumbs.push({'@type':'ListItem',position:2,name:'Setup guides',item:PUBLIC_SITE+'/how2s'});
  crumbs.push({'@type':'ListItem',position:crumbs.length+1,name:title.replace(/\s*[|—-]\s*Yarr Media$/,''),
   item:canonical});
  graph.push({'@type':'BreadcrumbList',itemListElement:crumbs});
  if(pathname.startsWith('/how2s/')){
   graph.push({'@type':'TechArticle',headline:title.replace(/\s*[|—-]\s*Yarr Media$/,''),
    description,mainEntityOfPage:canonical,inLanguage:'en-US',
    author:{'@id':SEO_ORG_ID},publisher:{'@id':SEO_ORG_ID}});
  }
 }
 const attr=v=>String(v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
 const metadata='<link rel="canonical" href="'+attr(canonical)+'">'+
  '<meta property="og:locale" content="en_US"><meta property="og:type" content="'+(pathname.startsWith('/how2s/')?'article':'website')+'">'+
  '<meta property="og:site_name" content="Yarr Media"><meta property="og:url" content="'+attr(canonical)+'">'+
  '<meta property="og:title" content="'+attr(title)+'"><meta property="og:description" content="'+attr(description)+'">'+
  '<meta property="og:image" content="'+attr(SEO_ARTWORK)+'"><meta property="og:image:secure_url" content="'+attr(SEO_ARTWORK)+'">'+
  '<meta property="og:image:type" content="image/jpeg"><meta property="og:image:width" content="1200">'+
  '<meta property="og:image:height" content="630"><meta property="og:image:alt" content="Yarr Media moon and sail logo">'+
  '<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="'+attr(title)+'">'+
  '<meta name="twitter:description" content="'+attr(description)+'"><meta name="twitter:image" content="'+attr(SEO_ARTWORK)+'">'+
  '<script type="application/ld+json">'+JSON.stringify({'@context':'https://schema.org','@graph':graph}).replace(/</g,'\\u003c')+'</script>';
 return html.replace(/<meta\s+(?:property="og:[^"]+"|name="twitter:[^"]+")[^>]*>/gi,'')
  .replace(/<link rel="canonical" href="[^"]+">/gi,'')
  .replace('</head>',metadata+'</head>');
}

function siteChrome(html) {
 let out=html;
 const header=/<header class="nav">[\s\S]*?<\/header>|<nav class="nav">[\s\S]*?<\/nav>/;
 const footer=/<footer class="(?:footer|foot|note)">[\s\S]*?<\/footer>/;
 if(!header.test(out)||!footer.test(out)||!out.includes('</style>'))throw Error('Public site chrome missing');
 out=out.replace(header,SITE_HEADER).replace(footer,SITE_FOOTER);
 return seoEnhance(out.replace('</style>',SITE_CHROME_CSS+'</style>').replace('</head>','<link rel="icon" type="image/svg+xml" href="/favicon.svg?v=moon-sail-v1"></head>').replaceAll('href=\"/app\"','href=\"'+APP_SITE+'/\"').replaceAll('href=\"/account\"','href=\"'+ACCOUNTS_SITE+'/\"').replaceAll('href=\"/\"','href=\"'+PUBLIC_SITE+'/\"').replaceAll('href=\"/#downloads\"','href=\"'+PUBLIC_SITE+'/#downloads\"').replace(/href=\"\/(features|free-vs-pro|how-it-works|remote-access|how2s|terms|privacy|cookies|refunds)\"/g,(_,path)=>'href=\"'+PUBLIC_SITE+'/'+path+'\"'));
}

const PUBLIC_PAGE_DATA = {
 '/features': {title:'Features',description:'Explore movie and TV libraries, metadata and local playback with Yarr Media.',eyebrow:'The product',heading:'Your collection, beautifully organized.',body:'Yarr Media helps you browse and play your own movie and television files on a server you control.',sections:[
 ['Movies and television','Organize your own media into libraries, seasons and episodes, with available posters, descriptions, cast and ratings.'],
 ['Local playback','Stream your media on supported devices across your home network, with playback behavior depending on file format and hardware.'],
 ['Optional connections','Connect Radarr, Sonarr and SABnzbd where configured. These services are optional and remain separately managed.']]},
 '/free-vs-pro': {title:'Free vs Pro',description:'Compare Yarr Media Free local streaming with its one-time $29 Pro remote-access upgrade.',eyebrow:'Plans',heading:'Start free at home. Go further with Pro.',body:'Free supports local self-hosted playback. The one-time $29 Pro upgrade adds account-linked remote access.',sections:[
 ['Free','Local library organization, browsing, compatible local playback and optional integrations. Free does not include remote access outside your home network.'],
 ['Pro — $29 one-time','Includes Free capabilities plus remote access to your own home library on compatible networks and devices.'],
 ['Availability and pricing','Pro is $29 USD as a one-time purchase, plus applicable sales tax. Sign in to My Account to purchase.']]},
 '/remote-access': {title:'Remote Access',description:'Learn how Yarr Media Pro connects you to your own home movie and TV library when away.',eyebrow:'Yarr Media Pro',heading:'Your home library, beyond home.',body:'Yarr Media Pro provides account-linked remote access to a compatible home server. Availability and playback quality depend on your devices, internet connection, and server configuration.',sections:[
 ['Designed around your own server','Your media files remain on your server. Remote connections depend on authentication, device compatibility and your home internet connection.'],
 ['Secure account-linked access','Sign in and pair your server for remote playback. Availability and performance depend on your network and server.'],
 ['Free stays local','The Free tier is intended for watching within your home network; external remote access is a Pro benefit.']]},
 '/apt': {title:'Install with apt',description:'Install the Yarr Media server on Ubuntu or Debian from the signed Yarr Media apt repository.',eyebrow:'Downloads',heading:'Install with apt',body:'For Ubuntu, Debian and other apt-based Linux. The package sets up the Yarr Media server in Docker and updates it nightly.',sections:[
 ['1. Trust the Yarr Media signing key','curl -fsSL https://yarr.media/apt/yarr-media.gpg | sudo tee /usr/share/keyrings/yarr-media.gpg > /dev/null'],
 ['2. Add the repository','echo "deb [signed-by=/usr/share/keyrings/yarr-media.gpg] https://yarr.media/apt stable main" | sudo tee /etc/apt/sources.list.d/yarr-media.list'],
 ['3. Install','sudo apt update && sudo apt install yarr-media'],
 ['4. Choose your media folder','sudo yarr-media-setup'],
 ['Prefer one command?','curl -fsSL https://yarr.media/install.sh | sudo bash does the same without adding a repository.']]},
 '/how-it-works': {title:'How It Works',description:'Understand how to self-host Yarr Media, add your own libraries and watch locally.',eyebrow:'Getting started',heading:'Your server. Your movies. Your control.',body:'Install Yarr Media on a compatible Linux server, organize your personal media, and watch on Google TV or a browser.',sections:[
 ['1. Run a compatible server','Download the Linux installer from the Downloads section. Setup guides cover installation and Docker.'],
 ['2. Add your own media folders','Point the server at media you own or are authorized to use. It organizes titles and fetches available information from connected metadata services.'],
 ['3. Watch on your home network','Browse your library and play supported media locally. Pro adds account-linked remote access.']]}
};
const LEGAL_PAGE_DATA = {
 '/refunds': {title:'Refund Policy',eyebrow:'Pro purchases',description:'Yarr Media Pro refunds: full refunds within 14 days, eligibility, payment timing, and what happens to Pro access.',heading:'Refund Policy',intro:'Effective November 19, 2026. Yarr Media Pro is a $29 USD one-time digital software purchase, plus applicable sales tax. There are no recurring Pro payments.',sections:[
 ['14-day refund policy','You can request a full refund for any reason within 14 calendar days of completing your Pro purchase. Your request must be sent within this period. This guarantee applies to the optional Pro upgrade; the local media server is free.'],
 ['Request a refund','Email refunds@yarr.media from the email address associated with your Yarr Media account. Include the date of purchase and your receipt or transaction reference, if available. Do not email card numbers, passwords, or sensitive payment details.'],
 ['After 14 days','We also review duplicate or incorrect charges, failures to receive or activate the purchased Pro entitlement, material defects that cannot reasonably be resolved, and refunds required under applicable law. Please contact us with the details; nothing in this policy limits your statutory consumer rights.'],
 ['How refunds are paid','Approved refunds go back to the original payment method. A full refund includes any applicable sales tax paid. After processing, refunds commonly appear within 5 to 10 business days, but your bank and payment provider determine timing.'],
 ['What happens to Pro','A refund of the Pro purchase revokes its associated Pro entitlement. Your free Yarr Media server, personal media files, and local libraries remain unaffected. Deleting your account does not itself initiate a refund; you can still contact us about an eligible purchase.'],
 ['Payment disputes','A formal payment dispute or chargeback may suspend or revoke the associated Pro entitlement during investigation. If a dispute is resolved in your favor, contact refunds@yarr.media about restoring eligible access. You retain any applicable cardholder dispute rights.'],
 ['Contact','Send refund requests and related questions to refunds@yarr.media. Requests submitted within the 14-day window are eligible even if processing takes longer.']]},

 '/privacy': {title:'Privacy Policy',eyebrow:'Privacy',description:'How Yarr Media handles account, device, streaming, and purchase information.',heading:'Privacy Policy',intro:'This notice describes Yarr Media website, account, connected-device, and purchase data practices.',sections:[
 ['Information used for accounts','If you sign in with Google, the website receives a verified account identifier, email address, display name and, if provided by Google, a profile picture URL. It stores associated account and session records to operate sign-in.'],
 ['Paired server information','Account-linked records can include server display names, identifiers, pairing status, connection credential hashes and connection status. Network diagnostics may exchange connection information to evaluate server access.'],
 ['Your media','Yarr Media is designed to operate from your own server. The public website does not provide a public media-storage service. Media access and metadata processing on your installed server are separate from the marketing website.'],
 ['Service providers','The service runs on Cloudflare infrastructure and uses Google sign-in. These providers may process technical information needed to deliver their respective services.'],
 ['Signed-in TVs and apps','When you sign in a TV or app with a code, the account stores the device name, type, app version, sign-in date and last-used date, plus a hashed credential. You can sign a device out at any time from My Account.'],
 ['Remote access','When you open your server remotely, the website issues a short-lived signed pass naming your account and server. Your media streams directly between your server and your device; it is not stored on the website.'],
 ['Payments','One-time Pro purchases are processed by Stripe. Card details are entered with Stripe and are not received by Yarr Media. We retain purchase references, payment and tax amounts, and entitlement status to manage Pro, refunds, and required business records.'],
 ['Security records','Sign-ins, device approvals, plan changes and account deletion are logged with a one-way hash of the network address, and kept for up to one year.'],
 ['Retention and deletion','Sessions expire after seven days and device credentials after one year unless renewed. You can permanently delete your account from My Account; this removes any Pro license, signs out every device and unlinks your servers. A minimal, anonymized deletion record and purchase and tax records required by law may be kept.'],
 ['Your choices','You can sign out, sign out individual devices, or delete your account at any time from My Account.'],
 ['Changes','Changes to this notice will be published here as the product develops.']]},
 '/cookies': {title:'Cookie Policy',eyebrow:'Cookies',description:'Essential Yarr Media session and Google sign-in cookies.',heading:'Cookie Policy',intro:'The Yarr Media public marketing pages do not require sign-in. The account area uses essential cookies for authentication.',sections:[
 ['Session cookie','After sign-in, an HttpOnly, Secure session cookie named __Host-yarr_session allows the website to recognize the signed-in account. The code sets a maximum age of seven days.'],
 ['Google sign-in cookie','During the Google sign-in flow, a temporary HttpOnly, Secure cookie named __Host-yarr_oauth helps validate the return from Google. Its maximum age is ten minutes and it is cleared after the flow.'],
 ['Other technologies','The application may use ordinary browser storage on the connected media interface. This notice describes the public website and account cookies, not every setting of a separately installed media server.'],
 ['Controls','You can clear cookies in your browser. Removing essential sign-in cookies will sign you out or interrupt an in-progress login.'],
 ['Advertising','No advertising or analytics cookies are intentionally set by this marketing-page implementation. Infrastructure providers may independently receive standard connection information.']]},
 '/terms': {title:'Terms of Use',eyebrow:'Legal',description:'Terms for Yarr Media self-hosted software and one-time Pro purchases.',heading:'Terms of Use',intro:'These terms cover the Yarr Media self-hosted server, account functions, and optional Pro purchase.',sections:[
 ['Software availability','Yarr Media software is available for compatible devices. Features may change, and access depends on your hardware, networking, and software version.'],
 ['Your own media','You are responsible for ensuring you have the rights to store, organize and play files on your server and for complying with applicable laws. Yarr Media does not supply movies or television programs.'],
 ['Third-party services','Optional integrations and Google sign-in are subject to the terms and availability of their respective providers.'],
 ['Accounts and security','Keep account credentials secure and use the service only for authorized access to your own installations. Do not attempt unauthorized access or interfere with the service.'],
 ['Pro purchase','Yarr Media Pro is a $29 USD one-time purchase plus applicable tax, associated with your account. It is not a recurring subscription. Our 14-day Refund Policy is available at yarr.media/refunds. Refunded purchases revoke the associated Pro entitlement, and disputed charges may suspend or revoke it. Statutory consumer rights remain unchanged.'],
 ['Remote access','Pro remote access connects your devices to your own server. It depends on your server being online and reachable and on your home internet connection, and may be unavailable at times.'],
 ['Changes and contact','Terms updates will be published here. For purchases and refunds contact refunds@yarr.media and review yarr.media/refunds.']]}
};
const PUBLIC_SITE = 'https://yarr.media';
const PUBLIC_URLS = ['/',...Object.keys(PUBLIC_PAGE_DATA),...HOW2_PATHS,...Object.keys(LEGAL_PAGE_DATA)];
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
  (path==='/refunds'?'<a class="cta" href="mailto:refunds@yarr.media?subject=Yarr%20Media%20Pro%20refund%20request">Request a refund by email</a>':isLegal?'':'<a class="cta" href="/#plans">Compare Free and Pro</a>')+'</main>'+
  '<footer class="foot"><span>Yarr Media · Your collection. Your server.</span><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/cookies">Cookies</a><a href="/refunds">Refunds</a><a href="/">Home</a></footer></div></body></html>');
}

const SITE = "https://yarr.larki-brian.workers.dev";
const APP_SITE = "https://app.yarr.media";
const ACCOUNTS_SITE = "https://accounts.yarr.media";
const SHARED_SESSION_NAME = "__Secure-yarr_session";
const sharedSessionCookie=(value,age)=>SHARED_SESSION_NAME+"="+value+"; Domain=yarr.media; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age="+age;
// Exact-host allowlist. Never derive OAuth redirects from arbitrary forwarded hosts.
const allowedSite=req=>{const u=new URL(req.url);return [PUBLIC_SITE,SITE,APP_SITE,ACCOUNTS_SITE,DEV_SITE].includes(u.origin)?u.origin:null;};
const validOrigin=req=>{const site=allowedSite(req);return !!site && req.headers.get('origin')===site;};
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
 const host=new URL(req.url).hostname;
  const raw=(host==='yarr.media'||host.endsWith('.yarr.media')?getCookie(req,SHARED_SESSION_NAME):'')||getCookie(req,'__Host-yarr_session');
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
async function googleStart(req,env) {
 const site=allowedSite(req);if(!site)return json({error:'invalid_host'},403);
 if(!authReady(env))return redirect('/account?setup=required');
 const state=random(),nonce=random(),verifier=random(),challenge=await digest(verifier);
 await env.ACCOUNTS.prepare("DELETE FROM oauth_flows WHERE expires_at < CURRENT_TIMESTAMP").run();
 const returnTo=safeReturnPath(new URL(req.url).searchParams.get('return'))||null;
 await env.ACCOUNTS.prepare("INSERT INTO oauth_flows(state_hash,nonce,verifier,expires_at,return_to) VALUES(?,?,?,datetime('now','+10 minutes'),?)").bind(await digest(state),nonce,verifier,returnTo).run();
 const p=new URLSearchParams({client_id:env.GOOGLE_CLIENT_ID,redirect_uri:site+'/auth/google/callback',response_type:'code',scope:'openid email profile',state,nonce,code_challenge:challenge,code_challenge_method:'S256',prompt:'select_account'});
 return redirect('https://accounts.google.com/o/oauth2/v2/auth?'+p,{ 'set-cookie':cookie('__Host-yarr_oauth',state,FLOW_SECONDS) });
}
async function googleCallback(req,env) {
 const site=allowedSite(req);if(!site)return json({error:'invalid_host'},403);
 const u=new URL(req.url),state=u.searchParams.get('state')||'',code=u.searchParams.get('code')||'';
 const stored=getCookie(req,'__Host-yarr_oauth');
 const cleared=cookie('__Host-yarr_oauth','',0);
 if(!authReady(env)||!state||!code||state.length>256||state!==stored)return redirect('/account?login=failed',{'set-cookie':cleared});
 const row=await env.ACCOUNTS.prepare("DELETE FROM oauth_flows WHERE state_hash=? AND expires_at > CURRENT_TIMESTAMP RETURNING nonce,verifier,return_to").bind(await digest(state)).first();
 if(!row)return redirect('/account?login=expired',{'set-cookie':cleared});
 try {
  const params=new URLSearchParams({code,client_id:env.GOOGLE_CLIENT_ID,client_secret:env.GOOGLE_CLIENT_SECRET,redirect_uri:site+'/auth/google/callback',grant_type:'authorization_code',code_verifier:row.verifier});
  const response=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:params});
  if(!response.ok)return redirect('/account?login=failed',{'set-cookie':cleared});
  const tokens=await response.json();
  const identity=await validateGoogleIdToken(tokens.id_token,env.GOOGLE_CLIENT_ID,row.nonce);
  const id=crypto.randomUUID(),displayName=String(identity.name||'').slice(0,120),email=String(identity.email||'').slice(0,254),avatar=typeof identity.picture==='string'&&identity.picture.startsWith('https://')?identity.picture.slice(0,1000):'';
  await env.ACCOUNTS.prepare("INSERT INTO users(id,google_sub,email,display_name,avatar_url) VALUES(?,?,?,?,?) ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email,display_name=excluded.display_name,avatar_url=excluded.avatar_url,updated_at=CURRENT_TIMESTAMP").bind(id,identity.sub,email,displayName,avatar).run();
  const user=await env.ACCOUNTS.prepare("SELECT id FROM users WHERE google_sub=?").bind(identity.sub).first();
  if(!user)throw Error('user_not_saved');
  await env.ACCOUNTS.prepare("INSERT INTO user_identities(provider,subject,user_id,email,email_verified,last_login_at) VALUES('google',?,?,?,1,CURRENT_TIMESTAMP) ON CONFLICT(provider,subject) DO UPDATE SET email=excluded.email,last_login_at=CURRENT_TIMESTAMP").bind(identity.sub,user.id,email).run();
  await audit(env,user.id,'signed_in','google',req);
  const session=random();
  await env.ACCOUNTS.prepare("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,datetime('now','+7 days'))").bind(crypto.randomUUID(),user.id,await digest(session)).run();
  const hostOnly=HOST_ONLY_SITES.has(site),returnTo=safeReturnPath(row.return_to);
  const headers=new Headers({'location':hostOnly?(returnTo||'/account'):ACCOUNTS_SITE+(returnTo||'/account'),'cache-control':'no-store'});
  headers.append('set-cookie',cleared);
  headers.append('set-cookie',hostOnly?cookie('__Host-yarr_session',session,SESSION_SECONDS):sharedSessionCookie(session,SESSION_SECONDS));
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
 const result=await env.ACCOUNTS.prepare("SELECT id,display_name,local_url,public_url,public_ip,status,server_identity,connection_secret_hash,last_seen_at,CASE WHEN last_seen_at>=datetime('now','-150 seconds') THEN 1 ELSE 0 END AS online,created_at FROM servers WHERE owner_user_id=? ORDER BY created_at DESC,id DESC").bind(userId).all();
 return result.results||[];
}
async function serverMutation(req,env,user) {
 if(!user)return json({error:'not_authenticated'},401);
 if(!validOrigin(req) || req.headers.get('sec-fetch-site')==='cross-site')return json({error:'forbidden'},403);
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
 if(!validOrigin(req) || req.headers.get('sec-fetch-site')==='cross-site')return json({error:'forbidden'},403);
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
 const ip=publicIPv4(req.headers.get('cf-connecting-ip'));
 const result=ip
  ?await env.ACCOUNTS.prepare("UPDATE servers SET last_seen_at=CURRENT_TIMESTAMP,public_ip=?,public_ip_seen_at=CURRENT_TIMESTAMP WHERE connection_secret_hash=? AND status='paired' AND server_identity IS NOT NULL").bind(ip,hash).run()
  :await env.ACCOUNTS.prepare("UPDATE servers SET last_seen_at=CURRENT_TIMESTAMP WHERE connection_secret_hash=? AND status='paired' AND server_identity IS NOT NULL").bind(hash).run();
 if(result.meta.changes!==1)return json({error:'unauthorized'},401);
 return json({status:'accepted',media_access:false,public_ip:ip||null});
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
// Full One-Eyed Willie application pilot. Every request is authorized against the
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
  if(!allowedSite(req)||(origin&&origin!==allowedSite(req))||(site&&site!=='same-origin')||(!origin&&site!=='same-origin'))return json({error:'forbidden'},403);
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
 if(method==='GET'&&ref.startsWith(allowedSite(req)+'/media-test')&&
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
 if(!validOrigin(req))return json({error:'forbidden'},403);
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
 if(!validOrigin(req))return json({error:'forbidden'},403);
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
  const address=linked?remoteAddressFormHTML(s):'';
  return '<article class="account-server"><div class="account-server-header"><div><h3>'+escapeHTML(s.display_name)+'</h3><p class="account-note">'+description+'</p></div><span class="server-status '+statusClass+'"><span class="status-dot" aria-hidden="true"></span>'+state+'</span></div><details class="account-manage"><summary>Manage server</summary><div class="account-manage-body">'+rename+address+remove+'</div></details></article>';
 }).join('')+'</div>';
}
function accountHTML(user,enabled,message='',servers=[],extra=null) {
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
   (extra?devicesPanelHTML(extra)+DANGER_HTML:'')+
  '</div>'+
  '<aside class="account-aside"><section class="account-panel account-pair-panel" id="pair-server"><div class="panel-top"><div><p class="account-kicker">Add a connection</p><h2>Pair a server</h2></div></div><p class="account-note">On your installed Yarr Media server, open <strong>Settings → General → Connect to Yarr</strong>, then enter the pairing code here.</p><form class="account-form" method="post" action="/account/pair"><label for="pairing-code">Pairing code</label><input id="pairing-code" name="code" required maxlength="22" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-XXXX-XXXX"><button class="account-submit" type="submit">Pair server</button></form><p class="account-small">Pairing links your installation to this account. Watching away from home also needs Pro and port 443 open to the server.</p></section>'+
   (extra?planPanelHTML(extra):'<section class="account-panel account-help"><p class="account-kicker">About your plan</p><h2>Yarr Media</h2><p class="account-note">Your personal libraries stay on your server. Pro enables account-linked remote access.</p><a href="/free-vs-pro" class="account-secondary">Compare Free and Pro</a></section>')+'</aside></div>'
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
// ---------------------------------------------------------------------------
// Accounts v2: remote-access passes, Google TV sign-in, Pro status, account
// deletion and scheduled cleanup. Inert until its secrets are set: no
// PASS_SIGNING_KEY means no passes. Pro is bought with the one-time $29
// checkout in stripe-checkout.js. Owner-only for now: a pass is only ever issued to the
// account that paired the server.
// ---------------------------------------------------------------------------
const DEV_SITE = 'https://yarr-dev.larki-brian.workers.dev';
const HOST_ONLY_SITES = new Set([SITE, DEV_SITE]);
const PASS_SECONDS = 60*60;
// Browser passes cover an evening of viewing; apps request fresh 1-hour passes.
const BROWSER_PASS_SECONDS = 12*60*60;
const DEVICE_CODE_SECONDS = 10*60;
const DEVICE_TOKEN_DAYS = 365;
const PRO_GRACE_DAYS = 3;
const DEVICE_TYPES = new Set(['google_tv','android','web']);

const sqlTime = date => date.toISOString().replace('T',' ').slice(0,19);
const parseSqlTime = value => value ? Date.parse(String(value).replace(' ','T')+'Z') : NaN;
const base64urlJSON = obj => encoded(new TextEncoder().encode(JSON.stringify(obj)));
const formatUserCode = code => code.slice(0,4)+'-'+code.slice(4);

// Paths a sign-in may return to. Anything else goes to the account page.
function safeReturnPath(value) {
 const v=String(value||'');
 if(v==='/owner/'||v==='/mail/')return v;
 if(/^\/open-app(?:\?path=%2F[A-Za-z0-9%._~-]{0,300})?$/.test(v))return v;
 if(/^\/activate(?:\?code=[A-Z0-9-]{1,12})?$/.test(v))return v;
 if(/^\/remote\/open\?server=[A-Za-z0-9-]{1,64}(?:&return=%2F[A-Za-z0-9%._~-]{0,300})?$/.test(v))return v;
 return '';
}

async function audit(env,userId,event,detail='',req=null) {
 try{
  const ip=req?.headers.get('cf-connecting-ip');
  await env.ACCOUNTS.prepare("INSERT INTO audit_log(user_id,event,detail,ip_hash) VALUES(?,?,?,?)")
   .bind(userId||null,event,String(detail||'').slice(0,300),ip?await digest('audit\0'+ip):null).run();
 }catch(_){}
}

// Fixed-window rate limit stored in pairing_rate_limits as "<scope>:<window start minute>".
async function rateLimited(env,req,scope,windowMinutes,limit) {
 const minute=Math.floor(Date.now()/60000),start=minute-minute%windowMinutes;
 const ipHash=await digest(req.headers.get('cf-connecting-ip')||'unknown');
 const key=scope+':'+start;
 await env.ACCOUNTS.prepare("INSERT INTO pairing_rate_limits(ip_hash,window,count) VALUES(?,?,1) ON CONFLICT(ip_hash,window) DO UPDATE SET count=count+1").bind(ipHash,key).run();
 const row=await env.ACCOUNTS.prepare("SELECT count FROM pairing_rate_limits WHERE ip_hash=? AND window=?").bind(ipHash,key).first();
 return Number(row?.count||0)>limit;
}

async function readJSON(req,max=4000) {
 if((req.headers.get('content-type')||'').split(';')[0].trim()!=='application/json')throw Object.assign(Error('content_type'),{status:415});
 const raw=await req.text();
 if(raw.length>max)throw Object.assign(Error('too_large'),{status:413});
 try{const v=JSON.parse(raw);if(v&&typeof v==='object'&&!Array.isArray(v))return v;}catch(_){}
 throw Object.assign(Error('invalid_json'),{status:400});
}
async function readForm(req,max=2000) {
 if(!(req.headers.get('content-type')||'').startsWith('application/x-www-form-urlencoded'))throw Object.assign(Error('content_type'),{status:415});
 const raw=await req.text();
 if(raw.length>max)throw Object.assign(Error('too_large'),{status:413});
 return new URLSearchParams(raw);
}
const sameSiteForm = req => validOrigin(req) && req.headers.get('sec-fetch-site')!=='cross-site';

// ---- Pro status ------------------------------------------------------------
// Pro = an active one-time license, or an active manual grant in subscriptions
// (no end date = indefinitely; used for the owner, testing and comps).
async function proStatus(env,userId) {
 // The one-time $29 license (stripe-checkout.js) is the purchase path. The
 // subscriptions table now only holds manual grants (provider 'manual').
 const oneTime=await oneTimeProActive(env,userId);
 const rows=(await env.ACCOUNTS.prepare("SELECT status,current_period_end FROM subscriptions WHERE user_id=?").bind(userId).all()).results||[];
 const now=Date.now(),grace=PRO_GRACE_DAYS*86400000;
 let active=false,until=null,forever=false;
 for(const r of rows){
  if(r.status!=='active'&&r.status!=='trialing')continue;
  const end=parseSqlTime(r.current_period_end);
  if(r.current_period_end&&!(end+grace>now))continue;
  active=true;
  if(!r.current_period_end)forever=true;
  else if(!until||end>until)until=end;
 }
 return {active:active||oneTime,until:(forever||oneTime)?null:(until?new Date(until).toISOString():null),forever:forever||oneTime,one_time:oneTime};
}

// ---- Device (TV/app) credentials --------------------------------------------
async function deviceFromRequest(req,env) {
 const auth=req.headers.get('authorization')||'';
 if(!auth.startsWith('Bearer ydv_')||auth.length>120)return null;
 const token=auth.slice(7);
 if(!/^ydv_[A-Za-z0-9_-]{40,60}$/.test(token))return null;
 const row=await env.ACCOUNTS.prepare(
  "SELECT devices.id AS device_id,devices.device_name,devices.device_type,devices.last_seen_at,users.id,users.email,users.display_name FROM devices JOIN users ON users.id=devices.owner_user_id WHERE devices.token_hash=? AND devices.revoked_at IS NULL AND devices.token_expires_at>CURRENT_TIMESTAMP"
 ).bind(await digest(token)).first();
 if(!row)return null;
 if(!row.last_seen_at||parseSqlTime(row.last_seen_at)<Date.now()-3600000)
  await env.ACCOUNTS.prepare("UPDATE devices SET last_seen_at=CURRENT_TIMESTAMP WHERE id=?").bind(row.device_id).run();
 return {user:{id:row.id,email:row.email,display_name:row.display_name},device:{id:row.device_id,name:row.device_name,type:row.device_type}};
}

async function deviceCodeStart(req,env) {
 if(await rateLimited(env,req,'devcode',10,20))return json({error:'slow_down'},429);
 let body;try{body=await readJSON(req,1000);}catch(e){return json({error:e.message},e.status||400);}
 const name=String(body.device_name||'Google TV').replace(/[\u0000-\u001f]/g,'').trim().slice(0,60)||'Google TV';
 const type=DEVICE_TYPES.has(body.device_type)?body.device_type:'google_tv';
 for(let attempt=0;attempt<4;attempt++){
  const userCode=[...crypto.getRandomValues(new Uint8Array(8))].map(b=>CODE_ALPHABET[b%CODE_ALPHABET.length]).join('');
  const deviceCode=random();
  const result=await env.ACCOUNTS.prepare("INSERT OR IGNORE INTO device_login_requests(device_code_hash,user_code_hash,device_name,device_type,expires_at) VALUES(?,?,?,?,datetime('now','+10 minutes'))")
   .bind(await digest(deviceCode),await digest('user\0'+userCode),name,type).run();
  if(result.meta.changes!==1)continue;
  const shown=formatUserCode(userCode);
  return json({device_code:deviceCode,user_code:shown,verification_uri:PUBLIC_SITE+'/activate',
   verification_uri_complete:PUBLIC_SITE+'/activate?code='+shown,expires_in:DEVICE_CODE_SECONDS,interval:5},201);
 }
 return json({error:'retry'},503);
}

async function deviceCodeToken(req,env) {
 let body;try{body=await readJSON(req,500);}catch(e){return json({error:e.message},e.status||400);}
 const code=String(body.device_code||'');
 if(!/^[A-Za-z0-9_-]{40,60}$/.test(code))return json({error:'invalid_grant'},400);
 const hash=await digest(code);
 const row=await env.ACCOUNTS.prepare("SELECT status,expires_at,poll_interval_s,last_polled_at FROM device_login_requests WHERE device_code_hash=?").bind(hash).first();
 if(!row)return json({error:'invalid_grant'},400);
 if(parseSqlTime(row.expires_at)<=Date.now())return json({error:'expired_token'},400);
 if(row.status==='denied')return json({error:'access_denied'},400);
 if(row.status==='used')return json({error:'invalid_grant'},400);
 if(row.status==='pending'){
  const tooSoon=row.last_polled_at&&parseSqlTime(row.last_polled_at)>Date.now()-(Number(row.poll_interval_s)-1)*1000;
  if(tooSoon){
   await env.ACCOUNTS.prepare("UPDATE device_login_requests SET poll_interval_s=MIN(poll_interval_s+5,30),last_polled_at=CURRENT_TIMESTAMP WHERE device_code_hash=?").bind(hash).run();
   return json({error:'slow_down',interval:Math.min(Number(row.poll_interval_s)+5,30)},400);
  }
  await env.ACCOUNTS.prepare("UPDATE device_login_requests SET last_polled_at=CURRENT_TIMESTAMP WHERE device_code_hash=?").bind(hash).run();
  return json({error:'authorization_pending'},400);
 }
 // Approved: hand out exactly one credential.
 const claimed=await env.ACCOUNTS.prepare("UPDATE device_login_requests SET status='used' WHERE device_code_hash=? AND status='approved' AND expires_at>CURRENT_TIMESTAMP RETURNING user_id,device_name,device_type").bind(hash).first();
 if(!claimed||!claimed.user_id)return json({error:'invalid_grant'},400);
 const token='ydv_'+random(),deviceId=crypto.randomUUID();
 await env.ACCOUNTS.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at,last_seen_at,app_version) VALUES(?,?,?,?,?,datetime('now','+"+DEVICE_TOKEN_DAYS+" days'),CURRENT_TIMESTAMP,?)")
  .bind(deviceId,claimed.user_id,claimed.device_name||'Google TV',claimed.device_type||'google_tv',await digest(token),String(req.headers.get('x-yarr-app-version')||'').slice(0,40)||null).run();
 await audit(env,claimed.user_id,'device_signed_in',claimed.device_name,req);
 return json({access_token:token,token_type:'Bearer',device_id:deviceId,expires_in:DEVICE_TOKEN_DAYS*86400});
}

async function deviceMe(req,env) {
 const auth=await deviceFromRequest(req,env);
 if(!auth)return json({error:'unauthorized'},401);
 const pro=await proStatus(env,auth.user.id);
 const servers=(await listServers(env,auth.user.id)).filter(s=>s.status==='paired'&&s.server_identity)
  .map(s=>({id:s.id,server_identity:s.server_identity,display_name:s.display_name,online:!!s.online,remote_address:serverOrigin(env,s)}));
 return json({user:auth.user,device:auth.device,pro:{active:pro.active,until:pro.until},servers});
}

async function deviceSignOut(req,env) {
 const auth=await deviceFromRequest(req,env);
 if(!auth)return json({error:'unauthorized'},401);
 await env.ACCOUNTS.prepare("UPDATE devices SET revoked_at=CURRENT_TIMESTAMP,token_hash=NULL WHERE id=?").bind(auth.device.id).run();
 await audit(env,auth.user.id,'device_signed_out',auth.device.name,req);
 return json({status:'signed_out'});
}

function simplePage(title,body,status=200) {
 const page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+escapeHTML(title)+' — Yarr Media</title><style>'+accountCSS+
  '.activate-code{font:800 30px ui-monospace,monospace;letter-spacing:.12em;text-align:center}.activate-actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}.activate-actions form{flex:1}.activate-actions button{width:100%}</style></head><body><div class="wrap"><nav class="nav"><a href="/" class="brand">YARR MEDIA</a></nav><main class="account-main"><div class="account-signin">'+body+
  '</div></main><footer class="note">Yarr Media · <a href="/terms">Terms</a> · <a href="/privacy">Privacy</a></footer></div></body></html>';
 return html(siteChrome(page),status);
}

async function activatePage(req,env) {
 const u=new URL(req.url);
 const code=normalizeCode(u.searchParams.get('code'));
 const shown=code.length===8?formatUserCode(code):'';
 const user=await currentUser(req,env);
 if(!user){
  const back='/activate'+(shown?'?code='+shown:'');
  return simplePage('Sign in a device','<p class="account-kicker">Sign in a device</p><h1>Sign in first</h1><p class="account-subtitle">Sign in to your Yarr Media account, then confirm the code shown on your TV.</p><div class="account-panel account-login">'+
   (authReady(env)?'<a class="account-submit" href="/auth/google/start?return='+encodeURIComponent(back)+'">Continue with Google</a>':'<p class="account-note">Sign-in is not configured yet.</p>')+'</div>');
 }
 const status=u.searchParams.get('done');
 if(status)return simplePage('Device sign-in',status==='approved'?'<h1>You\'re signed in</h1><p class="account-subtitle">Your TV will finish signing in within a few seconds.</p>':status==='denied'?'<h1>Sign-in cancelled</h1><p class="account-subtitle">The TV was not signed in.</p>':'<h1>Code not accepted</h1><p class="account-subtitle">That code is wrong, expired or already used. Start again on your TV.</p><a class="account-secondary" href="/activate">Enter a code</a>');
 if(code.length===8&&[...code].every(c=>CODE_ALPHABET.includes(c))){
  const pending=await env.ACCOUNTS.prepare("SELECT device_name FROM device_login_requests WHERE user_code_hash=? AND status='pending' AND expires_at>CURRENT_TIMESTAMP").bind(await digest('user\0'+code)).first();
  if(pending){
   const hidden='<input type="hidden" name="code" value="'+escapeHTML(shown)+'">';
   return simplePage('Confirm device','<p class="account-kicker">Sign in a device</p><h1>Sign in “'+escapeHTML(pending.device_name||'Google TV')+'”?</h1><p class="account-subtitle">Signed in as '+escapeHTML(user.email||user.display_name||'')+'. Only approve a code you can see on your own screen.</p><div class="account-panel"><p class="activate-code">'+escapeHTML(shown)+'</p><div class="activate-actions">'+
    '<form method="post" action="/activate">'+hidden+'<input type="hidden" name="decision" value="approve"><button class="account-submit" type="submit">Approve</button></form>'+
    '<form method="post" action="/activate">'+hidden+'<input type="hidden" name="decision" value="deny"><button class="account-secondary" type="submit">Cancel</button></form></div></div>');
  }
 }
 return simplePage('Sign in a device','<p class="account-kicker">Sign in a device</p><h1>Enter the code from your TV</h1>'+(shown?'<div class="account-feedback" role="status">That code is wrong, expired or already used.</div>':'')+
  '<div class="account-panel"><form class="account-form" method="get" action="/activate"><label for="code">Code</label><input id="code" name="code" required maxlength="12" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX"><button class="account-submit" type="submit">Continue</button></form></div>');
}

async function activateDecision(req,env) {
 const user=await currentUser(req,env);
 if(!user)return redirect('/activate');
 if(!sameSiteForm(req))return json({error:'forbidden'},403);
 if(await rateLimited(env,req,'activate',1,10))return redirect('/activate?done=invalid');
 let form;try{form=await readForm(req,300);}catch(e){return json({error:e.message},e.status||400);}
 const code=normalizeCode(form.get('code')),decision=form.get('decision');
 if(code.length!==8||![...code].every(c=>CODE_ALPHABET.includes(c))||!['approve','deny'].includes(decision))return redirect('/activate?done=invalid');
 const result=await env.ACCOUNTS.prepare("UPDATE device_login_requests SET status=?,user_id=?,approved_at=CURRENT_TIMESTAMP WHERE user_code_hash=? AND status='pending' AND expires_at>CURRENT_TIMESTAMP")
  .bind(decision==='approve'?'approved':'denied',user.id,await digest('user\0'+code)).run();
 if(result.meta.changes!==1)return redirect('/activate?done=invalid');
 await audit(env,user.id,decision==='approve'?'device_approved':'device_denied','',req);
 return redirect('/activate?done='+(decision==='approve'?'approved':'denied'));
}

// ---- Remote-access passes ------------------------------------------------------
// A pass is a short-lived Ed25519-signed token: "this account may use this
// server remotely until exp". The home server checks it offline with the public
// key from /api/passes/keys, so media never has to pass through Cloudflare.
let passKeyCache=null;
async function passKey(env) {
 if(!env.PASS_SIGNING_KEY)return null;
 if(passKeyCache?.raw===env.PASS_SIGNING_KEY)return passKeyCache;
 const jwk=JSON.parse(env.PASS_SIGNING_KEY);
 if(jwk.kty!=='OKP'||jwk.crv!=='Ed25519'||!jwk.d||!jwk.x||!jwk.kid)throw Error('PASS_SIGNING_KEY must be an Ed25519 private JWK with a kid');
 const key=await crypto.subtle.importKey('jwk',{kty:'OKP',crv:'Ed25519',d:jwk.d,x:jwk.x},{name:'Ed25519'},false,['sign']);
 passKeyCache={raw:env.PASS_SIGNING_KEY,key,kid:jwk.kid,public:{kty:'OKP',crv:'Ed25519',x:jwk.x,kid:jwk.kid,use:'sig',alg:'EdDSA'}};
 return passKeyCache;
}
async function passPublicKeys(env) {
 const keys=[];
 const current=await passKey(env);
 if(current)keys.push(current.public);
 if(env.PASS_PREVIOUS_PUBLIC_JWK){
  try{const old=JSON.parse(env.PASS_PREVIOUS_PUBLIC_JWK);if(old.kty==='OKP'&&old.crv==='Ed25519'&&old.x&&old.kid)keys.push({kty:'OKP',crv:'Ed25519',x:old.x,kid:old.kid,use:'sig',alg:'EdDSA'});}catch(_){}
 }
 return keys;
}
async function issuePass(env,user,server,device=null,lifetime=PASS_SECONDS) {
 const key=await passKey(env);
 if(!key)return {error:'passes_not_configured',status:503};
 const pro=await proStatus(env,user.id);
 if(!pro.active)return {error:'pro_required',status:402};
 const now=Math.floor(Date.now()/1000);
 const proUntil=pro.until?Math.floor(Date.parse(pro.until)/1000)+PRO_GRACE_DAYS*86400:null;
 const exp=Math.min(now+lifetime,proUntil||Infinity);
 const header={alg:'EdDSA',typ:'yarr-pass',kid:key.kid};
 const claims={v:1,iss:PUBLIC_SITE,aud:server.server_identity,sub:user.id,role:'owner',dev:device?.id||null,iat:now,exp,jti:random().slice(0,22)};
 const input=base64urlJSON(header)+'.'+base64urlJSON(claims);
 const sig=new Uint8Array(await crypto.subtle.sign({name:'Ed25519'},key.key,new TextEncoder().encode(input)));
 return {pass:input+'.'+encoded(sig),expires_at:new Date(exp*1000).toISOString(),remote_address:serverOrigin(env,server)};
}
// A server's HTTPS address: the owner's own address if they set one, otherwise
// one derived from the public IP it checks in from (a-b-c-d.<suffix>, which the
// server's Caddy has a certificate for). Server addresses are never under
// yarr.media, so customer servers never receive yarr.media sign-in cookies.
function publicIPv4(value) {
 const v=String(value||'').trim();
 const p=v.split('.');
 if(p.length!==4||!p.every(x=>/^(0|[1-9][0-9]{0,2})$/.test(x)&&Number(x)<=255))return null;
 const [a,b]=p.map(Number);
 if(a===0||a===10||a===127||a>=224||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127))return null;
 return v;
}
function serverOrigin(env,s) {
 if(s?.public_url)return s.public_url;
 if(s?.public_ip&&publicIPv4(s.public_ip))return 'https://'+s.public_ip.replaceAll('.','-')+'.'+(env.SERVER_HOST_SUFFIX||'sslip.io');
 return null;
}
async function ownedServer(env,userId,ref) {
 const id=String(ref||'');
 if(!/^[A-Za-z0-9-]{8,64}$/.test(id))return null;
 // Owner-only for now. Shared access will add a server_members table and check it here.
 return env.ACCOUNTS.prepare("SELECT id,server_identity,public_url,public_ip,display_name FROM servers WHERE owner_user_id=? AND status='paired' AND server_identity IS NOT NULL AND (id=? OR server_identity=?)").bind(userId,id,id).first();
}
async function passRequest(req,env) {
 let who=await deviceFromRequest(req,env);
 if(!who){
  const user=await currentUser(req,env);
  if(!user)return json({error:'unauthorized'},401);
  if(!validOrigin(req))return json({error:'forbidden'},403);
  who={user,device:null};
 }
 let body;try{body=await readJSON(req,500);}catch(e){return json({error:e.message},e.status||400);}
 const server=await ownedServer(env,who.user.id,body.server_id);
 if(!server)return json({error:'server_not_found'},404);
 const result=await issuePass(env,who.user,server,who.device);
 if(result.error)return json({error:result.error},result.status);
 return json(result);
}
// Browser entry point: sign in (if needed), check Pro, then hand the browser to
// the home server's own HTTPS address with a fresh pass.
async function remoteOpen(req,env) {
 const u=new URL(req.url);
 const ref=u.searchParams.get('server')||u.searchParams.get('server_identity')||'';
 let back=u.searchParams.get('return')||'/';
 if(!/^\/[A-Za-z0-9/._~%?=&-]{0,300}$/.test(back)||back.startsWith('//'))back='/';
 const user=await currentUser(req,env);
 if(!user){
  const ret=safeReturnPath('/remote/open?server='+encodeURIComponent(ref)+(back!=='/'?'&return='+encodeURIComponent(back):''));
  return redirect(ACCOUNTS_SITE+'/auth/google/start'+(ret?'?return='+encodeURIComponent(ret):''));
 }
 const server=await ownedServer(env,user.id,ref);
 if(!server)return redirect(ACCOUNTS_SITE+'/?remote=not_found');
 const origin=serverOrigin(env,server);
 if(!origin)return redirect(ACCOUNTS_SITE+'/?remote=no_address');
 const result=await issuePass(env,user,server,null,BROWSER_PASS_SECONDS);
 if(result.error)return redirect(ACCOUNTS_SITE+'/?remote='+(result.error==='pro_required'?'pro_required':'unavailable'));
 const target=new URL('/remote/start',origin);
 target.searchParams.set('pass',result.pass);
 target.searchParams.set('return',back);
 return new Response(null,{status:303,headers:{location:target.toString(),'cache-control':'no-store','referrer-policy':'no-referrer'}});
}

// ---- Account management --------------------------------------------------------
async function accountDevicesAction(req,env) {
 const user=await currentUser(req,env);
 if(!user)return redirect('/account');
 if(!sameSiteForm(req))return json({error:'forbidden'},403);
 let form;try{form=await readForm(req,300);}catch(e){return json({error:e.message},e.status||400);}
 const id=String(form.get('id')||'');
 if(form.get('action')!=='revoke'||!/^[a-f0-9-]{36}$/.test(id))return redirect('/account?device=invalid');
 const r=await env.ACCOUNTS.prepare("UPDATE devices SET revoked_at=CURRENT_TIMESTAMP,token_hash=NULL WHERE id=? AND owner_user_id=? AND revoked_at IS NULL").bind(id,user.id).run();
 if(r.meta.changes)await audit(env,user.id,'device_revoked',id,req);
 return redirect('/account?device='+(r.meta.changes?'revoked':'invalid'));
}
async function accountRemoteAddress(req,env) {
 const user=await currentUser(req,env);
 if(!user)return redirect('/account');
 if(!sameSiteForm(req))return json({error:'forbidden'},403);
 let form;try{form=await readForm(req,600);}catch(e){return json({error:e.message},e.status||400);}
 const id=String(form.get('id')||'');
 if(!/^[a-f0-9-]{36}$/.test(id))return redirect('/account?server=invalid');
 let address;try{address=remoteAddress(form.get('address'));}catch(_){return redirect('/account?server=bad_address');}
 const r=await env.ACCOUNTS.prepare("UPDATE servers SET public_url=? WHERE id=? AND owner_user_id=?").bind(address||null,id,user.id).run();
 return redirect('/account?server='+(r.meta.changes?'address_saved':'invalid'));
}
// Can the internet reach this server's HTTPS address? Checked from Cloudflare,
// so it answers "would remote viewers get through?" without guessing.
async function accountReachability(req,env,u) {
 const user=await currentUser(req,env);
 if(!user)return redirect('/account');
 const server=await ownedServer(env,user.id,u.searchParams.get('id'));
 if(!server)return redirect('/account?server=invalid');
 const origin=serverOrigin(env,server);
 if(!origin)return redirect('/account?server=reach_noaddress');
 try{
  const r=await fetch(origin+'/health',{signal:AbortSignal.timeout(6000),headers:{accept:'application/json'}});
  const body=await r.json().catch(()=>({}));
  return redirect('/account?server='+(r.ok&&body.status==='ok'?'reach_ok':'reach_fail'));
 }catch(_){return redirect('/account?server=reach_fail');}
}
// The signed apt repository lives on the apt-repo branch (written by the
// release workflow); this serves it at https://yarr.media/apt.
async function aptFile(req,path) {
 if(!/^(?:yarr-media\.(?:gpg|asc)|dists\/stable\/(?:InRelease|Release(?:\.gpg)?|main\/binary-(?:amd64|arm64)\/Packages(?:\.gz)?)|pool\/main\/y\/yarr-media\/yarr-media_[0-9A-Za-z.+~-]+_all\.deb)$/.test(path))return new Response('Not found',{status:404});
 const upstream=await fetch('https://raw.githubusercontent.com/blarkin13/one-eyed-willie/apt-repo/'+path,{cf:{cacheTtl:300,cacheEverything:true}});
 if(!upstream.ok)return new Response('Not found',{status:upstream.status===404?404:502});
 const type=path.endsWith('.deb')?'application/vnd.debian.binary-package':path.endsWith('.gz')?'application/gzip':path.endsWith('.gpg')?'application/pgp-keys':'text/plain; charset=utf-8';
 return new Response(req.method==='HEAD'?null:upstream.body,{headers:{'content-type':type,'cache-control':'public, max-age=300','x-content-type-options':'nosniff'}});
}
async function installScript(req,env,path,type) {
 const upstream=await fetch('https://raw.githubusercontent.com/blarkin13/one-eyed-willie/main/'+path,{cf:{cacheTtl:300,cacheEverything:true}});
 if(!upstream.ok)return new Response('echo "Yarr Media installer is temporarily unavailable" >&2; exit 1\n',{status:503,headers:{'content-type':'text/plain; charset=utf-8'}});
 return new Response(req.method==='HEAD'?null:upstream.body,{headers:{'content-type':type+'; charset=utf-8','cache-control':'public, max-age=300','x-content-type-options':'nosniff'}});
}
async function accountDelete(req,env) {
 const user=await currentUser(req,env);
 if(!user)return redirect('/account');
 if(!sameSiteForm(req))return json({error:'forbidden'},403);
 let form;try{form=await readForm(req,300);}catch(e){return json({error:e.message},e.status||400);}
 if(form.get('confirm')!=='DELETE')return redirect('/account?delete=confirm');
 await audit(env,null,'account_deleted',await digest('user\0'+user.id),req);
 const cleanupStatements=[env.ACCOUNTS.prepare("DELETE FROM pairing_requests WHERE owner_user_id=?").bind(user.id)];
 if(env.YARR_STRIPE_TEST_ENABLED==='1'||env.YARR_ONE_TIME_PRO_ENABLED==='1'){
  // Delete account identity and its usable Pro license while retaining a
  // non-identifying purchase record needed for reconciliation and tax records.
  cleanupStatements.push(
   env.ACCOUNTS.prepare("INSERT OR IGNORE INTO stripe_purchase_archive(checkout_session_id,price_id,status,amount_total,currency,payment_intent_id,purchased_at,updated_at) SELECT id,price_id,status,amount_total,currency,payment_intent_id,created_at,updated_at FROM stripe_checkout_sessions WHERE user_id=?").bind(user.id),
   env.ACCOUNTS.prepare("DELETE FROM one_time_pro_entitlements WHERE user_id=?").bind(user.id),
   env.ACCOUNTS.prepare("DELETE FROM stripe_checkout_sessions WHERE user_id=?").bind(user.id)
  );
 }
 cleanupStatements.push(env.ACCOUNTS.prepare("DELETE FROM users WHERE id=?").bind(user.id));
 await env.ACCOUNTS.batch(cleanupStatements);
 const headers=new Headers({location:PUBLIC_SITE+'/?account=deleted','cache-control':'no-store'});
 const host=new URL(req.url).hostname;
 headers.append('set-cookie',host==='yarr.media'||host.endsWith('.yarr.media')?sharedSessionCookie('',0):cookie('__Host-yarr_session','',0));
 return new Response(null,{status:303,headers});
}
async function accountExtras(env,user) {
 const [pro,devices]=await Promise.all([
  proStatus(env,user.id),
  env.ACCOUNTS.prepare("SELECT id,device_name,device_type,created_at,last_seen_at FROM devices WHERE owner_user_id=? AND revoked_at IS NULL AND token_hash IS NOT NULL ORDER BY created_at DESC").bind(user.id).all().then(r=>r.results||[])
 ]);
 return {pro,devices,one_time_checkout:proCheckoutAvailable(env),live_checkout:env.YARR_STRIPE_MODE==='live'};
}
function planPanelHTML(extra) {
 const p=extra.pro;
 let body;
 if(p.active){
  const note=p.one_time?'One-time Pro license active; no recurring payments.':'Pro active. '+escapeHTML(p.forever?'No end date':'Until '+new Date(p.until).toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric',timeZone:'UTC'}))+'.';
  body='<h2>Yarr Media Pro</h2><p class="account-note">'+note+' Remote-access availability depends on the installed server and app.</p>';
 }else if(extra.one_time_checkout){
  body='<h2>Free</h2><p class="account-note">Yarr Media Pro — $29 one-time purchase, plus applicable tax. '+(extra.live_checkout?'Access your own media remotely.':'Sandbox checkout for test accounts only; remote access is still in development.')+'</p>'+
   '<p class="account-note">Full refund requests accepted within 14 days. <a href="https://yarr.media/refunds">Read the Refund Policy</a> before purchasing.</p>'+    '<form method="post" action="/api/stripe/checkout"><input type="hidden" name="product" value="pro"><button class="account-submit" type="submit">'+(extra.live_checkout?'Buy Pro — $29':'Test Pro checkout')+'</button></form>';
 }else{
  body='<h2>Free</h2><p class="account-note">Pro remote access is not on sale yet.</p>';
 }
 return '<section class="account-panel account-help" id="plan"><p class="account-kicker">Your plan</p>'+body+'</section>';
}
function devicesPanelHTML(extra) {
 const list=extra.devices.length?'<div class="account-server-list">'+extra.devices.map(d=>
  '<article class="account-server"><div class="account-server-header"><div><h3>'+escapeHTML(d.device_name)+'</h3><p class="account-note">Signed in '+escapeHTML(String(d.created_at).slice(0,10))+(d.last_seen_at?' · last used '+escapeHTML(String(d.last_seen_at).slice(0,10)):'')+'</p></div>'+
  '<form method="post" action="/account/devices"><input type="hidden" name="action" value="revoke"><input type="hidden" name="id" value="'+escapeHTML(d.id)+'"><button class="account-text-button" type="submit">Sign out</button></form></div></article>').join('')+'</div>'
  :'<p class="account-note">No TVs or apps are signed in. On your TV, choose Sign in and enter the code at <strong>yarr.media/activate</strong>.</p>';
 return '<section class="account-panel" id="devices"><div class="panel-top"><div><p class="account-kicker">Devices</p><h2>Signed-in devices</h2></div><span class="account-count">'+extra.devices.length+'</span></div>'+list+'</section>';
}
function remoteAddressFormHTML(s) {
 const detected=s.public_ip?'https://'+s.public_ip.replaceAll('.','-')+'.sslip.io':'';
 return '<p class="account-small">'+(s.public_url?'Using your custom address.':detected?'Reached at '+escapeHTML(detected)+' (found automatically).':'Address not found yet; it appears after the server checks in.')+' <a href="'+APP_SITE+'/">Open app.yarr.media</a></p>'+
  '<p class="account-small"><a href="/account/servers/check?id='+escapeHTML(s.id)+'">Check remote access</a></p>'+
  '<form method="post" action="/account/servers/address" class="account-form"><input type="hidden" name="id" value="'+escapeHTML(s.id)+'"><label for="server-address-'+escapeHTML(s.id)+'">Custom HTTPS address (optional)</label><div class="account-form-row"><input id="server-address-'+escapeHTML(s.id)+'" maxlength="260" name="address" placeholder="Leave empty to use the automatic address" value="'+escapeHTML(s.public_url||'')+'"><button class="account-secondary" type="submit">Save address</button></div></form>';
}
const DANGER_HTML='<section class="account-panel" id="delete-account"><p class="account-kicker">Danger zone</p><h2>Delete account</h2><p class="account-note">Permanently deletes your account, revokes any one-time Pro license without a refund or transfer, signs out devices, and unlinks servers. Media on your own server is not touched. Required purchase and tax records are retained without your Yarr user ID.</p><details class="account-manage"><summary>Delete my account</summary><div class="account-manage-body"><form method="post" action="/account/delete" class="account-form"><label for="confirm-delete">Type DELETE to confirm</label><input id="confirm-delete" name="confirm" required autocomplete="off" pattern="DELETE"><button class="account-secondary" type="submit">Permanently delete</button></form></div></details></section>';
const ACCOUNT_MESSAGES={
 checkout:{success:'Stripe received your purchase. Your Pro status will update when the payment is confirmed.',cancel:'Checkout was cancelled; no test payment was made.'},
 device:{revoked:'That device has been signed out.',invalid:'That device could not be found.'},
 delete:{confirm:'Type DELETE to confirm account deletion.'},
 remote:{pro_required:'Remote access needs Pro.',no_address:'Add a remote HTTPS address for that server first.',not_found:'That server is not linked to your account.',unavailable:'Remote access is not available yet.'},
 server:{address_saved:'Remote address saved.',bad_address:'Use a public https:// address on port 443, without a path.',
  reach_ok:'Remote access works: yarr.media reached your server from the internet.',
  reach_fail:'yarr.media could not reach your server from the internet. Forward TCP port 443 on your router to this server, then check again.',
  reach_noaddress:'Your server has not reported its address yet. Make sure it is on and paired.'}
};
function accountMessage(u) {
 for(const [key,table] of Object.entries(ACCOUNT_MESSAGES)){const v=u.searchParams.get(key);if(v&&table[v])return table[v];}
 return '';
}

// ---- Housekeeping ------------------------------------------------------------
async function cleanup(env) {
 const minute=Math.floor(Date.now()/60000),bucket=Math.floor(Date.now()/600000);
 await env.ACCOUNTS.batch([
  env.ACCOUNTS.prepare("DELETE FROM sessions WHERE expires_at<CURRENT_TIMESTAMP"),
  env.ACCOUNTS.prepare("DELETE FROM oauth_flows WHERE expires_at<CURRENT_TIMESTAMP"),
  env.ACCOUNTS.prepare("DELETE FROM pairing_requests WHERE expires_at<datetime('now','-1 day')"),
  env.ACCOUNTS.prepare("DELETE FROM device_login_requests WHERE expires_at<datetime('now','-1 day')"),
  env.ACCOUNTS.prepare("DELETE FROM pairing_rate_limits WHERE (instr(window,':')>0 AND CAST(substr(window,instr(window,':')+1) AS INTEGER)<?) OR (instr(window,':')=0 AND CAST(window AS INTEGER)<?)").bind(minute-180,bucket-18),
  env.ACCOUNTS.prepare("DELETE FROM devices WHERE (revoked_at IS NOT NULL AND revoked_at<datetime('now','-90 days')) OR (token_expires_at IS NOT NULL AND token_expires_at<datetime('now','-30 days'))"),
  env.ACCOUNTS.prepare("DELETE FROM audit_log WHERE created_at<datetime('now','-365 days')"),
  env.ACCOUNTS.prepare("DELETE FROM billing_events WHERE received_at<datetime('now','-400 days')")
 ]);
}

// ---- app.yarr.media -----------------------------------------------------------
// Everyone opens app.yarr.media. The Worker only serves a starter page and a
// service worker; after that, every request the app makes is sent by the
// browser straight to the signed-in owner's own server (its HTTPS address is
// derived from the public IP the server checks in from), carrying a Yarr pass.
// Library pages and video therefore travel home -> viewer, never through
// Cloudflare, and the address bar stays app.yarr.media.
const APP_SW_SOURCE = String.raw`/* Yarr Media app service worker (served by yarr.media). */
'use strict';
const OWN = ['/__yarr/'];
const COPY = ['accept','accept-language','content-type','range','if-range','if-none-match','if-modified-since','x-requested-with'];
let conn = null, pending = null;
self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
async function connection(force) {
  if (!force && conn && conn.exp - Date.now() > 10 * 60 * 1000) return conn;
  if (!pending) pending = (async () => {
    try {
      const r = await fetch('/__yarr/connection', {credentials: 'same-origin', cache: 'no-store'});
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error(body.message || 'connection ' + r.status), {status: r.status, body});
      conn = {origin: body.server_origin, pass: body.pass, exp: Date.parse(body.expires_at)};
      return conn;
    } finally { pending = null; }
  })();
  return pending;
}
function page(title, message, status) {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Yarr Media</title>' +
    '<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0a0a;color:#f5f1e8;font:16px system-ui,sans-serif;text-align:center">' +
    '<div style="max-width:520px;padding:24px"><h1 style="font-size:26px">' + esc(title) + '</h1><p style="color:#c2bcb2;line-height:1.6">' + esc(message) + '</p>' +
    '<p><a style="color:#eb8888" href="/">Try again</a> &middot; <a style="color:#eb8888" href="https://accounts.yarr.media/">My Account</a></p></div></body>',
    {status: status || 503, headers: {'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store'}});
}
async function send(req, c, body) {
  const url = new URL(req.url);
  const headers = new Headers();
  for (const name of COPY) { const v = req.headers.get(name); if (v) headers.set(name, v); }
  headers.set('authorization', 'Yarr-Pass ' + c.pass);
  return fetch(c.origin + url.pathname + url.search, {method: req.method, headers, body, mode: 'cors', credentials: 'omit', redirect: 'follow', cache: 'no-store'});
}
async function forward(req) {
  const url = new URL(req.url);
  const navigate = req.mode === 'navigate';
  let c;
  try { c = await connection(false); }
  catch (e) {
    const target = e.body && e.body.redirect;
    if (navigate && target) return Response.redirect(target, 303);
    if (navigate) return page('Your server is not available', e.message, e.status || 503);
    return new Response(JSON.stringify({error: 'yarr_connection', message: e.message}), {status: e.status || 503, headers: {'content-type': 'application/json'}});
  }
  const body = ['GET', 'HEAD'].includes(req.method) ? undefined : await req.arrayBuffer();
  let res;
  try {
    res = await send(req, c, body);
    if (res.status === 401) { c = await connection(true); res = await send(req, c, body); }
  } catch (e) {
    if (navigate) return page('Your server could not be reached', 'Yarr Media could not connect to your home server. Check that it is on and reachable from the internet.', 502);
    return new Response(JSON.stringify({error: 'server_unreachable'}), {status: 502, headers: {'content-type': 'application/json'}});
  }
  if (res.redirected && navigate) {
    const moved = new URL(res.url);
    return Response.redirect(moved.pathname + moved.search, 303);
  }
  const nullBody = [101, 204, 205, 304].includes(res.status) || req.method === 'HEAD';
  return new Response(nullBody ? null : res.body, {status: res.status, statusText: res.statusText, headers: res.headers});
}
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || OWN.some(p => url.pathname.startsWith(p))) return;
  event.respondWith(forward(event.request));
});
`;
const APP_START_PAGE = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Yarr Media</title>'+
 '<link rel="icon" type="image/svg+xml" href="https://yarr.media/favicon.svg?v=moon-sail-v1"></head>'+
 '<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0a0a;color:#f5f1e8;font:16px system-ui,sans-serif;text-align:center">'+
 '<p id="status">Connecting to your server…</p><script>'+
 "(async()=>{const say=t=>{document.getElementById('status').textContent=t};"+
 "if(!('serviceWorker' in navigator)){say('This browser cannot open Yarr Media. Try Chrome, Edge, Firefox or Safari (not a private window).');return}"+
 "try{const r=await fetch('/__yarr/connection',{cache:'no-store'});const j=await r.json().catch(()=>({}));"+
 "if(!r.ok){if(j.redirect){location.replace(j.redirect);return}say(j.message||'Your server is not available right now.');return}"+
 "await navigator.serviceWorker.register('/__yarr/sw.js',{scope:'/'});await navigator.serviceWorker.ready;"+
 "const tries=Number(sessionStorage.getItem('yarr-sw-tries')||0);if(tries>2){say('Could not start the app in this browser.');return}sessionStorage.setItem('yarr-sw-tries',String(tries+1));"+
 "if(navigator.serviceWorker.controller)location.reload();else navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload(),{once:true});"+
 "}catch(e){say('Could not connect: '+(e&&e.message||e))}})();"+
 '</script></body></html>';
const APP_START_HEADERS = {'content-type':'text/html; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'same-origin',
 'content-security-policy':"default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; worker-src 'self'; img-src https://yarr.media; base-uri 'none'; frame-ancestors 'none'"};

async function appServerFor(env,user) {
 // Owner-only for now: the most recently seen paired server on the account.
 return env.ACCOUNTS.prepare("SELECT id,server_identity,public_url,public_ip,display_name FROM servers WHERE owner_user_id=? AND status='paired' AND server_identity IS NOT NULL ORDER BY (last_seen_at IS NULL),last_seen_at DESC,created_at DESC LIMIT 1").bind(user.id).first();
}
async function appConnection(req,env,u) {
 const user=await currentUser(req,env);
 const back=u.searchParams.get('path')||'/';
 if(!user)return json({error:'signin',redirect:ACCOUNTS_SITE+'/auth/google/start?return='+encodeURIComponent('/open-app'+(back!=='/'?'?path='+encodeURIComponent(back):''))},401);
 const server=await appServerFor(env,user);
 if(!server)return json({error:'no_server',message:'No server is linked to this account yet.',redirect:ACCOUNTS_SITE+'/'},404);
 const origin=serverOrigin(env,server);
 if(!origin)return json({error:'no_address',message:'Your server has not reported its address yet. Make sure it is on and paired, then try again in a minute.'},409);
 const result=await issuePass(env,user,server);
 if(result.error==='pro_required')return json({error:'pro_required',message:'Watching away from home needs Pro.',redirect:ACCOUNTS_SITE+'/?remote=pro_required'},402);
 if(result.error)return json({error:result.error,message:'Remote access is not available right now.'},result.status);
 return json({server_origin:origin,server_name:server.display_name,pass:result.pass,expires_at:result.expires_at});
}
async function appHostRoutes(req,env,u) {
 const p=u.pathname,m=req.method;
 if(p==='/__yarr/sw.js'&&m==='GET')return new Response(APP_SW_SOURCE,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-cache','service-worker-allowed':'/','x-content-type-options':'nosniff'}});
 if(p==='/__yarr/connection'&&m==='GET')return appConnection(req,env,u);
 if(p.startsWith('/__yarr/'))return json({error:'not_found'},404);
 if(p==='/account'||p.startsWith('/account/')||p.startsWith('/auth/'))return redirect(ACCOUNTS_SITE+p+u.search);
 // Without the service worker yet (first visit, or a cleared browser): start it.
 if(m==='GET'||m==='HEAD'){
  if(!await currentUser(req,env))return redirect(ACCOUNTS_SITE+'/auth/google/start?return='+encodeURIComponent('/open-app'+(p!=='/'?'?path='+encodeURIComponent(p+u.search):'')));
  return new Response(m==='HEAD'?null:APP_START_PAGE,{headers:APP_START_HEADERS});
 }
 return json({error:'app_not_started'},409);
}

// Routes added by this section. Returns null when the request is not ours.
async function accountsV2Routes(req,env,u) {
 const m=req.method,p=u.pathname;
 if(p==='/activate'&&u.hostname!=='accounts.yarr.media'&&!HOST_ONLY_SITES.has(u.origin))return redirect(ACCOUNTS_SITE+'/activate'+u.search);
 if(m==='GET'&&p==='/open-app'&&!HOST_ONLY_SITES.has(u.origin)){
  const path=u.searchParams.get('path')||'/';
  return redirect(APP_SITE+(/^\/[A-Za-z0-9/._~%?=&-]{0,300}$/.test(path)&&!path.startsWith('//')?path:'/'));
 }
 if(m==='GET'&&p==='/activate')return activatePage(req,env);
 if(m==='POST'&&p==='/activate')return activateDecision(req,env);
 if(m==='POST'&&p==='/api/device/code')return deviceCodeStart(req,env);
 if(m==='POST'&&p==='/api/device/token')return deviceCodeToken(req,env);
 if(m==='GET'&&p==='/api/device/me')return deviceMe(req,env);
 if(m==='POST'&&p==='/api/device/signout')return deviceSignOut(req,env);
 if(m==='GET'&&p==='/api/passes/keys'){
  try{return new Response(JSON.stringify({keys:await passPublicKeys(env)}),{headers:{...JSON_HEADERS,'cache-control':'public, max-age=3600'}});}
  catch(_){return json({error:'passes_misconfigured'},503);}
 }
 if(m==='POST'&&p==='/api/passes')return passRequest(req,env);
 if(m==='GET'&&p==='/remote/open')return remoteOpen(req,env);
 if(m==='POST'&&p==='/account/devices')return accountDevicesAction(req,env);
 if(m==='POST'&&p==='/account/servers/address')return accountRemoteAddress(req,env);
 if(m==='GET'&&p==='/account/servers/check')return accountReachability(req,env,u);
 if((m==='GET'||m==='HEAD')&&p==='/install.sh'&&!u.hostname.startsWith('app.'))return installScript(req,env,'deploy/install.sh','text/x-shellscript');
 if((m==='GET'||m==='HEAD')&&p==='/tv'&&!u.hostname.startsWith('app.'))return redirect(APK_URL);
 if((m==='GET'||m==='HEAD')&&p==='/android'&&!u.hostname.startsWith('app.'))return redirect(PHONE_APK_URL);
 if((m==='GET'||m==='HEAD')&&p.startsWith('/apt/')&&!u.hostname.startsWith('app.'))return aptFile(req,p.slice(5));
 if(m==='POST'&&p==='/account/delete')return accountDelete(req,env);
 return null;
}

export default { async fetch(req,env) {
 const u=new URL(req.url);
 try {
  // Owner workspace: restricted to the canonical public host and browser session; no device credentials.
  if(u.pathname==='/owner'||u.pathname.startsWith('/owner/')||u.pathname==='/mail'||u.pathname.startsWith('/mail/')||u.pathname.startsWith('/api/support-mail/')){
   if(u.hostname!=='yarr.media')return ownerNotFound();
   const user=env.ACCOUNTS?await currentUser(req,env):null;
   if(!user&&req.method==='GET'&&(u.pathname==='/owner'||u.pathname==='/owner/'||u.pathname==='/mail'||u.pathname==='/mail/'))return redirect('/auth/google/start?return='+encodeURIComponent(u.pathname.startsWith('/mail')?'/mail/':'/owner/'));
   if(!ownerAllowed(user,env))return ownerNotFound();
   if(u.pathname.startsWith('/api/support-mail/'))return handleSupportMail(req,env,{session:async()=>user});
   return ownerPage(req,env,user);
  }

  if((req.method==='GET'||req.method==='HEAD')&&u.pathname==='/favicon.svg')return new Response(req.method==='HEAD'?null:YARR_ICON_SVG,{headers:{'content-type':'image/svg+xml; charset=utf-8','cache-control':'public, max-age=3600','x-content-type-options':'nosniff'}});
  if((req.method==='GET'||req.method==='HEAD')&&u.pathname==='/favicon.ico')return redirect('/favicon.svg?v=moon-sail-v1');
  if(u.hostname==='www.yarr.media')return new Response(null,{status:301,headers:{location:'https://yarr.media'+u.pathname+u.search,'cache-control':'public, max-age=3600'}});
  // Yarr Pro test-mode routes; independent of media playback, disabled by default.
  if(u.hostname==='accounts.yarr.media'&&u.pathname==='/api/stripe/webhook')
    return proStripeWebhook(req,env);
  if(u.hostname==='accounts.yarr.media'&&u.pathname==='/api/stripe/checkout')
    return createProCheckout(req,env,await currentUser(req,env));
  if(u.hostname==='accounts.yarr.media'&&u.pathname==='/api/stripe/entitlement'){
    if(req.method!=='GET')return json({error:'method_not_allowed'},405);
    const member=await currentUser(req,env);
    if(!member)return json({error:'sign_in_required'},401);
    const status=await proStatus(env,member.id);
    return json({pro:status.active,checkout_enabled:proCheckoutAvailable(env)});
  }
  const accountsV2=await accountsV2Routes(req,env,u);
  if(accountsV2)return accountsV2;
  // Dedicated app and account hosts share an authenticated first-party session.
  // app.yarr.media: starter page + service worker; the app itself comes from
  // the owner's own server (see appHostRoutes).
  if(u.hostname==='app.yarr.media')return appHostRoutes(req,env,u);
  if(u.hostname==='accounts.yarr.media'){
    if(req.method==='GET'&&u.pathname==='/account')return redirect('/'+u.search);
    // The account dashboard is the homepage of the accounts subdomain.
    if(u.pathname==='/auth/google/start')return redirect(PUBLIC_SITE+'/auth/google/start'+u.search);
    if(u.pathname==='/auth/google/callback')return redirect('/account?login=failed');
    if(u.pathname==='/app')return redirect(APP_SITE+'/');
  }
  if(u.hostname==='yarr.media'&&(u.pathname==='/app'||u.pathname==='/account'))return redirect((u.pathname==='/app'?APP_SITE+'/':ACCOUNTS_SITE+'/account')+u.search);
  // Both authorized hosts now serve their own first-party account sessions.
  // Public brand assets are fetched from the existing GitHub release source,
  // rather than through the account-gated private server proxy.
  const publicAssetPaths={
   '/assets/yarr-media-wordmark.png':'yarr-media-wordmark.png',
   '/assets/yarr-media-og.jpg':'yarr-media-og.jpg',
   '/assets/yarr-media-og-v2.jpg':'yarr-media-og-v2.jpg',
   '/assets/yarr-anchor.png':'yarr-anchor.png'
  };
  if((req.method==='GET'||req.method==='HEAD')&&publicAssetPaths[u.pathname]){
   const name=publicAssetPaths[u.pathname];
   const upstream=await fetch('https://raw.githubusercontent.com/blarkin13/one-eyed-willie/main/server/'+name);
   if(!upstream.ok)return new Response('Asset unavailable',{status:502,headers:{'cache-control':'no-store'}});
   return new Response(req.method==='HEAD'?null:upstream.body,{status:200,headers:{
    'content-type':name.endsWith('.jpg')?'image/jpeg':'image/png',
    'cache-control':'public, max-age=3600','x-content-type-options':'nosniff'
   }});
  }
  if(req.method==='GET'&&(u.pathname==='/health'||u.pathname==='/__edge/health')) {
   let database='unavailable';try{await env.ACCOUNTS.prepare('SELECT 1 AS ok').first();database='ready'}catch(_){}
   return json({service:'yarr',status:'staging',database,authentication:authReady(env)?'configured':'not_configured',media_proxy:false},database==='ready'?200:503);
  }
  if(req.method==='GET'&&u.pathname==='/robots.txt'&&u.hostname!=='yarr.media'&&u.hostname!=='www.yarr.media')return new Response('User-agent: *\nDisallow: /\n',{headers:{'content-type':'text/plain; charset=utf-8','cache-control':'public, max-age=3600'}});
  if(req.method==='GET'&&u.pathname==='/auth/google/start')return googleStart(req,env);
  if(req.method==='GET'&&u.pathname==='/auth/google/callback')return googleCallback(req,env);
  if(req.method==='POST'&&u.pathname==='/auth/logout') {
   if(!validOrigin(req))return json({error:'forbidden'},403);
   const token=getCookie(req,SHARED_SESSION_NAME)||getCookie(req,'__Host-yarr_session');
   if(token)await env.ACCOUNTS.prepare("DELETE FROM sessions WHERE token_hash=?").bind(await digest(token)).run();
   const cleared=new Headers({'location':new URL(req.url).hostname==='accounts.yarr.media'?'/account':ACCOUNTS_SITE+'/account','cache-control':'no-store'});
   cleared.append('set-cookie',new URL(req.url).hostname.endsWith('yarr.media')?sharedSessionCookie('',0):cookie('__Host-yarr_session','',0));
   return new Response(null,{status:303,headers:cleared});
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
  if((req.method==='GET'||req.method==='HEAD') && (u.pathname==='/assets/yarr-media-wordmark.png'||u.pathname==='/assets/yarr-media-og.jpg')) {
   const isLogo=u.pathname.endsWith('wordmark.png');
   const target='https://raw.githubusercontent.com/blarkin13/one-eyed-willie/main/server/'+(isLogo?'yarr-media-wordmark.png':'yarr-media-og.jpg');
   const upstream=await fetch(target,{cf:{cacheTtl:3600,cacheEverything:true}});
   if(!upstream.ok)return new Response('Image unavailable',{status:502,headers:{'cache-control':'no-store'}});
   return new Response(req.method==='HEAD'?null:upstream.body,{headers:{'content-type':isLogo?'image/png':'image/jpeg','cache-control':'public, max-age=3600','x-content-type-options':'nosniff'}});
  }
  if(req.method==='GET'&&u.pathname==='/app') {
   const user=await currentUser(req,env);
   if(!user)return redirect(new URL(req.url).hostname==='yarr.larki-brian.workers.dev'?'/account':ACCOUNTS_SITE+'/account');
   return proxyInstalledApp(req,env,'/');
  }
  if(req.method==='GET'&&(u.pathname==='/account'||(u.hostname==='accounts.yarr.media'&&(u.pathname==='/'||u.pathname==='/index.html')))) {
   const user=await currentUser(req,env);
   const message=u.searchParams.get('login')?'Sign-in was not completed. Please try again.':'';
   const statuses={renamed:'Server name saved.',deleted:'Unused registration removed.',protected:'Paired servers require a secure unpair flow before removal.',invalid:'Check the server name and try again.'};
   const pairStatuses={success:'Server linked to your account. Remote access is not enabled yet.',invalid:'The pairing code is invalid, expired or already used.',claimed:'That server is already linked. Unpairing is not enabled yet.',slow:'Too many attempts. Try again shortly.',limit:'You can link up to five servers during testing.'};
   const message2=message||pairStatuses[u.searchParams.get('pair')]||statuses[u.searchParams.get('server')]||'';
   const servers=user?await listServers(env,user.id):[];
   const extra=user?await accountExtras(env,user):null;
   const shown=accountMessage(u)||message2||(u.searchParams.get('account')==='deleted'?'Your account has been deleted.':'');
   return html(accountHTML(user,authReady(env),shown,servers,extra),200,{'content-security-policy':HTML_HEADERS['content-security-policy'].replace("form-action 'self'","form-action 'self' https://checkout.stripe.com")});
  }
  if(req.method==='GET'||req.method==='HEAD') {
   if(u.pathname==='/robots.txt')return new Response(req.method==='HEAD'?null:'User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /account\nDisallow: /owner/\nDisallow: /mail/\nDisallow: /api/\nDisallow: /auth/\nSitemap: '+PUBLIC_SITE+'/sitemap.xml\n',{headers:{'content-type':'text/plain; charset=utf-8','cache-control':'public, max-age=3600'}});
   if(u.pathname==='/sitemap.xml')return new Response(req.method==='HEAD'?null:'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+PUBLIC_URLS.map(p=>'<url><loc>'+PUBLIC_SITE+p+'</loc></url>').join('')+'</urlset>',{headers:{'content-type':'application/xml; charset=utf-8','cache-control':'public, max-age=3600'}});
   if(u.pathname==='/how2s'||u.pathname.startsWith('/how2s/')){
    const guide=how2Html(u.pathname);
    if(!guide)return redirect('/how2s');
    return new Response(req.method==='HEAD'?null:siteChrome(guide),{headers:{...HTML_HEADERS,'cache-control':'public, max-age=300'}});
   }
   const info=infoPage(u.pathname);
   if(info)return new Response(req.method==='HEAD'?null:info,{headers:{...HTML_HEADERS,'cache-control':'public, max-age=300'}});
  }
  if(u.pathname.startsWith('/auth/'))return json({error:'not_found'},404);
  if(u.pathname==='/api/private' || u.pathname.startsWith('/api/private/'))return json({error:'not_found'},404);
  // This Worker owns account, login and pairing routes. All other application
  // paths are served by the paired local One-Eyed Willie server.
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
   return new Response(req.method==='HEAD'?null:siteChrome(rendered.replace('</main>',DOWNLOADS_PLACEHOLDERS+'</main>')).replace('<body>','<body class="yarr-home">').replace('</head>',"<style>/* Anchor artwork sits behind homepage content, never intercepts interaction. */body.yarr-home{position:relative}body.yarr-home::before{content:\"\";position:absolute;bottom:0;right:clamp(120px,21vw,320px);width:min(32vw,430px);height:560px;background:url(\"/assets/yarr-anchor.png\") right bottom/contain no-repeat;z-index:0;pointer-events:none;opacity:.85}body.yarr-home>.wrap{position:relative;z-index:1}@media(max-width:850px){body.yarr-home::before{right:20px;width:min(52vw,400px);opacity:.65}}@media(max-width:560px){body.yarr-home::before{right:8px;width:55vw;opacity:.45}}</style>"+'</head>'),{headers:{...HTML_HEADERS,'cache-control':'private, no-store'}});
  }
  return json({error:'not_found'},404);
 }catch(_) {return json({error:'temporarily_unavailable'},503);}
},
async email(message,env) { await receiveSupportMail(message,env); },
async scheduled(event,env,ctx) { ctx.waitUntil(cleanup(env)); }
};
