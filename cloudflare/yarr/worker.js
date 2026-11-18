// Yarr staging: public product landing page plus isolated, disabled account APIs.
// Product name and public domain remain provisional. No home-server media proxy.
const JSON_HEADERS = {'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'};
const HTML_HEADERS = {'content-type':'text/html; charset=utf-8','cache-control':'public, max-age=300','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"};
const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yarr — Your media. Your server.</title><meta name="description" content="A self-hosted movie and TV media server. Organize your local library, explore rich metadata, and watch on your own devices.">
<meta name="robots" content="noindex,follow">
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b1019;color:#f6f3ed}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 78% 5%,#282342 0,transparent 48%),#0b1019;min-height:100vh}a{color:inherit}
.wrap{max-width:1100px;margin:auto;padding:0 28px}.nav{display:flex;align-items:center;justify-content:space-between;padding:26px 0;border-bottom:1px solid #ffffff18}.brand{font-size:24px;font-weight:900;letter-spacing:.04em}.links{display:flex;gap:25px;align-items:center}.links a{text-decoration:none;color:#c8c9d3;font-size:14px}.links a:hover{color:white}
.hero{padding:105px 0 74px;max-width:790px}.eyebrow{font-weight:700;letter-spacing:.18em;color:#b69cfa;font-size:12px;text-transform:uppercase}.hero h1{font-size:clamp(46px,7vw,84px);line-height:1.02;letter-spacing:-.055em;margin:24px 0}.hero h1 span{color:#b69cfa}.lead{font-size:20px;color:#c3c6d2;line-height:1.65;max-width:650px}.actions{display:flex;gap:14px;flex-wrap:wrap;margin-top:36px}.btn{display:inline-block;border:1px solid #7b6ea1;border-radius:11px;text-decoration:none;padding:14px 21px;font-weight:650}.btn.primary{background:#8d6be5;color:#110d1b;border-color:#8d6be5}.btn:hover{filter:brightness(1.12)}
.section{padding:55px 0;border-top:1px solid #ffffff19}.section h2{font-size:32px;letter-spacing:-.035em}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:32px}.card{padding:25px;border:1px solid #ffffff22;border-radius:15px;background:#ffffff08}.card h3{font-size:18px;margin:0 0 10px}.card p{color:#bcc0cb;line-height:1.6;margin:0}.step{color:#b69cfa;font-weight:900;font-size:12px;letter-spacing:.16em;margin-bottom:14px}
.note{font-size:14px;color:#9da4b5;line-height:1.7}.footer{padding:26px 0 45px;color:#8e96a8;font-size:13px;border-top:1px solid #ffffff19}
@media(max-width:700px){.hero{padding:70px 0 50px}.links{gap:12px}.links a{font-size:12px}.cards{grid-template-columns:1fr}.hero h1{font-size:50px}.lead{font-size:17px}}
</style></head><body><div class="wrap">
<nav class="nav"><div class="brand">YARR<span style="color:#a78ae8">.</span></div><div class="links"><a href="#features">Features</a><a href="#setup">How it works</a><a href="#download">Server install</a></div></nav>
<main><section class="hero"><div class="eyebrow">Self-hosted movies & television</div><h1>Your media.<br><span>Your server.</span></h1><p class="lead">Give your personal movie and TV collection a home. Browse beautiful libraries, discover rich metadata, and stream from the server you control.</p><div class="actions"><a class="btn primary" href="#setup">See how it works</a><a class="btn" href="#download">Server installation</a></div></section>
<section id="features" class="section"><div class="eyebrow">One library, all your screens</div><h2>Made for the collection you already own.</h2><div class="cards"><div class="card"><h3>Movies & TV</h3><p>Scan local files, build a beautiful library, and browse episodes, posters, cast, and descriptions.</p></div><div class="card"><h3>Watch your way</h3><p>Play locally from your own hardware. Account-based access on the web and TV is in development.</p></div><div class="card"><h3>Optional integrations</h3><p>Enhance your setup with metadata services and optional Radarr, Sonarr and SABnzbd connections.</p></div></div></section>
<section id="setup" class="section"><div class="eyebrow">How it will work</div><h2>Set up once. Watch on your devices.</h2><div class="cards"><div class="card"><div class="step">01 / INSTALL</div><h3>Run your server</h3><p>Install the self-hosted server on a compatible home computer or NAS.</p></div><div class="card"><div class="step">02 / CONNECT</div><h3>Add your libraries</h3><p>Choose media folders and let Yarr organize and enrich your collection.</p></div><div class="card"><div class="step">03 / WATCH</div><h3>Sign in and play</h3><p>Secure account pairing and remote playback are being developed.</p></div></div></section>
<section id="download" class="section"><div class="eyebrow">Early development</div><h2>Server download & sign-in are coming.</h2><p class="lead">The server is being prepared for independent installations. Public downloads, Google Sign-In, and account-based pairing are not available yet.</p><p class="note">This preview does not access or expose anyone's media server. Yarr is a provisional product name and domain has not been selected.</p></section></main>
<footer class="footer">Yarr · Development preview · Self-hosted media</footer>
</div></body></html>`;
export default { async fetch(request,env) {
 const u=new URL(request.url);
 if(request.method==='GET'&&(u.pathname==='/health'||u.pathname==='/__edge/health')) {
  let database='unavailable';
  try{await env.ACCOUNTS.prepare('SELECT 1 AS ok').first();database='ready'}catch(_){}
  return Response.json({service:'yarr',status:'staging',database,authentication:'not_configured',media_proxy:false},{status:database==='ready'?200:503,headers:JSON_HEADERS});
 }
 if(u.pathname==='/robots.txt')return new Response('User-agent: *\nDisallow: /\n',{headers:{'content-type':'text/plain; charset=utf-8'}});
 if(u.pathname.startsWith('/api/')||u.pathname.startsWith('/auth/'))return Response.json({error:'not_configured',message:'Account sign-in is not enabled.'},{status:503,headers:JSON_HEADERS});
 if(request.method!=='GET'&&request.method!=='HEAD')return new Response('Method not allowed',{status:405,headers:JSON_HEADERS});
 if(u.pathname==='/'||u.pathname==='/index.html')return new Response(request.method==='HEAD'?null:page,{headers:HTML_HEADERS});
 return new Response('Not found',{status:404,headers:JSON_HEADERS});
}};
