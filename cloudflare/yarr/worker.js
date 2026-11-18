// Yarr staging: public product landing page plus isolated, disabled account APIs.
// Product name and public domain remain provisional. No home-server media proxy.
const JSON_HEADERS = {'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'};
const HTML_HEADERS = {'content-type':'text/html; charset=utf-8','cache-control':'public, max-age=300','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"};
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
  if((origin&&origin!==SITE)||(site&&site!=='same-origin')||(!origin&&site!=='same-origin'))return json({error:'forbidden'},403);
 }
 const size=Number(req.headers.get('content-length')||0);
 if(!Number.isFinite(size)||size>32*1024*1024)return json({error:'request_too_large'},413);
 const source=new URL(req.url);
 // The origin host is a compile-time constant. Browser controls only path/query.
 const path=originPath||source.pathname;
 if(!path.startsWith('/')||path.startsWith('//')||path.includes('\\'))return json({error:'invalid_path'},400);
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
  await verifiedOrigin(env,owned.server,identitySignal);
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
  responseHeaders.set('cache-control','private, no-store');
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
  // Keep video, HLS, images and HTTP Range responses streamed, not buffered.
  return new Response(method==='HEAD'||[204,205,304].includes(upstream.status)?null:upstream.body,{status:upstream.status,headers:responseHeaders});
 }catch(_){return json({error:'private_server_unavailable'},503);}
}

const MEDIA_CACHE_HEADERS={'cache-control':'private, no-store','x-content-type-options':'nosniff'};
async function privateCatalog(req,env){
 const owned=await ownedPrivateServer(req,env);
 if(owned.error)return owned.error;
 const url=new URL(req.url);
 const kind=url.searchParams.get('kind');
 if(kind!=='movies'&&kind!=='tv')return json({error:'invalid_kind'},400);
 const offsetRaw=url.searchParams.get('offset')||'0';
 if(!/^\d{1,7}$/.test(offsetRaw))return json({error:'invalid_offset'},400);
 const offset=Number(offsetRaw);
 if(offset>1000000)return json({error:'invalid_offset'},400);
 const sort=url.searchParams.get('sort')||'title';
 if(!['title','recent','added','year','length','rating'].includes(sort))return json({error:'invalid_sort'},400);
 const search=url.searchParams.get('search')||'';
 if(search.length>100||/[\x00-\x1f]/.test(search))return json({error:'invalid_search'},400);
 const signal=AbortSignal.timeout(12000);
 try{
  await verifiedOrigin(env,owned.server,signal);
  const params=new URLSearchParams({kind,offset:String(offset),limit:'72',sort,search});
  const r=await env.YARR_PRIVATE_API.fetch('http://one-eyed-willie:8787/api/catalog?'+params.toString(),{method:'GET',signal,headers:{accept:'application/json','accept-encoding':'identity'}});
  if(!r.ok || !(r.headers.get('content-type')||'').includes('json'))return json({error:'library_unavailable'},502);
  const length=Number(r.headers.get('content-length')||0);
  if(length>1200000)return json({error:'library_response_too_large'},502);
  const raw=await r.text();
  if(raw.length>1200000)return json({error:'library_response_too_large'},502);
  const data=JSON.parse(raw);
  if(!Array.isArray(data.items))return json({error:'library_response_invalid'},502);
  const items=data.items.slice(0,72).map(x=>{
   const path=typeof x.poster_url==='string'?x.poster_url:'';
   const match=/^\/api\/artwork\/(thumb\/)?([a-f0-9]{64})$/.exec(path);
   return {kind,library_id:Number(x.library_id)||null,key:String(x.key||'').slice(0,200),title:String(x.title||'Untitled').slice(0,220),
    year:Number.isInteger(x.year)?x.year:null,genres:Array.isArray(x.genres)?x.genres.filter(x=>typeof x==='string').slice(0,5):[],
    rating:typeof x.rating==='number'?x.rating:null, runtime:typeof x.runtime==='number'?x.runtime:null,
    seasons:Array.isArray(x.seasons)?x.seasons.length:0,watched:!!x.watched,partially_watched:!!x.partially_watched,
    poster_url:match?'/api/private/artwork/'+(match[1]?'thumb/':'')+match[2]:null};
  });
  return json({kind,items,total:Math.max(0,Number(data.total)||items.length),offset,limit:72,server_name:owned.server.display_name,media_access:false});
 }catch(_){return json({error:'private_library_unavailable'},503);}
}
async function privateArtwork(req,env){
 const owned=await ownedPrivateServer(req,env);
 if(owned.error)return owned.error;
 const path=new URL(req.url).pathname;
 const match=/^\/api\/private\/artwork\/(thumb\/)?([a-f0-9]{64})$/.exec(path);
 if(!match)return json({error:'not_found'},404);
 const signal=AbortSignal.timeout(12000);
 try{
  await verifiedOrigin(env,owned.server,signal);
  const origin='http://one-eyed-willie:8787/api/artwork/'+(match[1]?'thumb/':'')+match[2];
  const r=await env.YARR_PRIVATE_API.fetch(origin,{method:'GET',signal,headers:{accept:'image/avif,image/webp,image/jpeg,image/png','accept-encoding':'identity'}});
  if(!r.ok)return new Response(null,{status:r.status===404?404:502,headers:MEDIA_CACHE_HEADERS});
  const mime=(r.headers.get('content-type')||'').split(';')[0].trim().toLowerCase();
  if(!['image/jpeg','image/png','image/webp'].includes(mime))return json({error:'invalid_artwork_type'},502);
  const len=Number(r.headers.get('content-length')||0);
  if(len>5*1024*1024)return json({error:'artwork_too_large'},502);
  const bytes=await r.arrayBuffer();
  if(bytes.byteLength>5*1024*1024)return json({error:'artwork_too_large'},502);
  return new Response(bytes,{status:200,headers:{...MEDIA_CACHE_HEADERS,'content-type':mime,'content-length':String(bytes.byteLength)}});
 }catch(_){return json({error:'artwork_unavailable'},503);}
}


function serversHTML(servers) {
 const paired=servers.some(s=>s.status==='paired'&&s.server_identity);
 const pairing='<section class="block"><p class="eyebrow">Secure pairing</p><h2>Pair your server</h2><p class="note">On your installed server, open Settings → General → Connect to Yarr, then enter its code.</p><form class="serverform" method="post" action="/account/pair"><label>Pairing code<input required maxlength="22" name="code" autocomplete="off" placeholder="XXXX-XXXX-XXXX-XXXX"></label><button class="btn" type="submit">Pair server</button></form></section>';
 const cards=servers.length?servers.map(s=>{
  const linked=s.status==='paired'&&!!s.server_identity;
  const tag=linked?'<span class="tag" style="color:#b6e9cb;background:#203c31">Paired'+(s.online?' · Online':' · Offline')+'</span>':'<span class="tag">Not paired</span>';
  const description=linked?(s.online?'Server is online and reporting securely. Remote playback is not enabled yet.':s.connection_secret_hash?'Account paired; server is offline or has not reported recently.':'Account paired. Reconnect from server settings to activate secure status reporting.'):'This manual registration is not linked to an installed server.';
  const rename='<form method="post" action="/account/servers" class="serverform" style="margin-top:14px;gap:8px"><input type="hidden" name="action" value="rename"><input type="hidden" name="id" value="'+escapeHTML(s.id)+'"><label>Server name<input required maxlength="80" name="name" value="'+escapeHTML(s.display_name)+'"></label><div><button type="submit" class="smallbtn">Save name</button></div></form>';
  const removal=linked?'':'<form method="post" action="/account/servers" style="margin-top:12px"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="'+escapeHTML(s.id)+'"><button type="submit" class="smallbtn">Remove unused registration</button></form>';
  return '<article class="server"><div class="serverhead"><h3>'+escapeHTML(s.display_name)+'</h3>'+tag+'</div><p class="note">'+description+'</p>'+rename+removal+'</article>';
 }).join(''):'<div class="server"><p class="note">No servers linked to your account yet.</p></div>';
 return pairing+'<section class="block"><p class="eyebrow">Your servers</p><h2>Connected servers</h2><p class="note">The server link is tied to your Google account. Media access requires a separate secure connection.</p>'+cards+'<p class="note"><a href="/app">Open full One-Eyed Willie app</a> · <a href="/viewer">Open separate Yarr viewer</a></p></section>';
}

const appCSS="\n:root{color-scheme:dark;background:#090b11;color:#f7f6fa;font-family:system-ui,-apple-system,sans-serif}\n*{box-sizing:border-box}body{margin:0;background:#090b11;min-height:100vh}a{color:inherit;text-decoration:none}\n.appnav{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px clamp(18px,4vw,64px);border-bottom:1px solid #ffffff16}\n.appbrand{font-size:23px;font-weight:900;letter-spacing:.08em}.navlinks{display:flex;gap:18px;color:#bebdcc;font-size:14px}\n.appmain{padding:34px clamp(18px,4vw,64px) 80px}\n.intro{display:flex;justify-content:space-between;align-items:end;gap:20px;flex-wrap:wrap}\n.eyebrow{text-transform:uppercase;color:#ab89f8;letter-spacing:.13em;font-size:12px;font-weight:700}\nh1{font-size:clamp(32px,5vw,56px);margin:10px 0 8px;letter-spacing:-.04em}p{color:#a9a8ba}\n.connection{font-size:13px;color:#c9bddf}\n.toolbar{margin:30px 0 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}\n.tab{border:0;border-bottom:2px solid transparent;background:transparent;color:#b5afc1;padding:12px 20px;font:600 16px system-ui;cursor:pointer}\n.tab.selected{border-color:#aa80f6;color:#fff}\ninput,select{background:#171824;color:#fff;border:1px solid #383547;border-radius:9px;padding:12px;font-size:14px}\ninput{min-width:180px;flex:1;max-width:330px}select{max-width:185px}\n#library-count{margin-left:auto;font-size:13px;color:#9a97a7}\n.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:26px 17px;align-items:start}\n.media-tile{background:none;border:0;padding:0;color:inherit;text-align:left;cursor:pointer;min-width:0;border-radius:9px}\n.media-tile:focus-visible{outline:3px solid #ad88f3;outline-offset:5px}\n.poster{aspect-ratio:2/3;background:#191c2b;display:block;border-radius:9px;overflow:hidden;border:1px solid #ffffff18;transition:transform .2s,box-shadow .2s}\n.media-tile:hover .poster,.media-tile:focus-visible .poster{transform:scale(1.035);box-shadow:0 10px 32px #0009}\n.poster img{width:100%;height:100%;object-fit:cover}.media-placeholder{display:grid;place-items:center;height:100%;font-size:64px;color:#7e638e}\n.media-title{display:block;margin-top:10px;font-weight:650;font-size:14px;line-height:1.35;overflow-wrap:anywhere}\n.media-meta{display:block;color:#a4a0b1;font-size:12px;margin-top:4px}\n#media-state{padding:20px 0;color:#a5a0b8;font-size:13px}\n#load-more{padding:11px 20px;border:1px solid #6c528c;border-radius:8px;background:#221d2c;color:white;cursor:pointer}\n#media-detail[hidden],#load-more[hidden]{display:none}\n#media-detail{position:fixed;inset:0;background:#070711db;z-index:10;display:grid;place-items:center;padding:20px}\n.detail-panel{background:#181724;border:1px solid #ffffff27;border-radius:17px;max-width:710px;width:100%;padding:26px;display:grid;grid-template-columns:180px 1fr;gap:24px}\n#detail-poster{aspect-ratio:2/3;background:#242038;border-radius:8px;overflow:hidden}\n#detail-poster img{width:100%;height:100%;object-fit:cover}\n#detail-close{background:#302b3e;border:0;color:white;border-radius:8px;padding:10px 18px;cursor:pointer}\n@media(max-width:600px){.toolbar{gap:9px}.tab{padding:9px 12px}.media-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:18px 10px}.detail-panel{grid-template-columns:95px 1fr;padding:14px}.navlinks{font-size:12px}}\n";
const appClientJS="'use strict';\n(function(){\n const $=id=>document.getElementById(id);\n const grid=$('media-grid'),state=$('media-state'),tabs=[...document.querySelectorAll('[data-kind]')];\n const search=$('library-search'),sort=$('library-sort'),more=$('load-more'),detail=$('media-detail'),close=$('detail-close');\n let kind='movies', offset=0,total=0,busy=false,done=false,queryId=0,debounce;\n const esc=value=>String(value??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n function status(text){state.textContent=text;}\n function poster(item){return item.poster_url&&/^\\/api\\/private\\/artwork\\/(thumb\\/)?[a-f0-9]{64}$/.test(item.poster_url)?item.poster_url:'';}\n function card(item){\n  const node=document.createElement('button');node.type='button';node.className='media-tile';\n  const art=poster(item);\n  const image=art?'<img loading=\"lazy\" decoding=\"async\" alt=\"\" src=\"'+esc(art)+'\">':'<div class=\"media-placeholder\" aria-hidden=\"true\">◈</div>';\n  const extras=[item.year,item.rating!=null?'★ '+item.rating:'',item.kind==='tv'&&item.seasons?item.seasons+' seasons':''].filter(Boolean).join(' · ');\n  node.innerHTML='<span class=\"poster\">'+image+'</span><span class=\"media-title\">'+esc(item.title)+'</span><span class=\"media-meta\">'+esc(extras)+'</span>';\n  node.addEventListener('click',()=>showDetail(item));\n  return node;\n }\n function showDetail(item){\n  $('detail-title').textContent=item.title;\n  $('detail-meta').textContent=[item.year,item.rating!=null?'Rating '+item.rating:'',item.runtime?item.runtime+' minutes':'',item.kind==='tv'?item.seasons+' seasons':''].filter(Boolean).join(' · ');\n  $('detail-genres').textContent=item.genres.join(' · ')||'No genre information available';\n  $('detail-watched').textContent=item.watched?'Watched':item.partially_watched?'Partially watched':'Not watched';\n  const art=poster(item);\n  $('detail-poster').replaceChildren();\n  if(art){const img=new Image();img.src=art;img.alt=item.title+' poster';$('detail-poster').append(img);}\n  detail.hidden=false;\n  close.focus();\n }\n close.addEventListener('click',()=>{detail.hidden=true;});\n detail.addEventListener('click',e=>{if(e.target===detail)detail.hidden=true;});\n document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!detail.hidden){detail.hidden=true;}});\n async function load(){\n  if(busy||done)return;\n  busy=true;const current=queryId;more.hidden=true;\n  status(offset?'Loading more titles…':'Loading your '+(kind==='movies'?'movies':'TV shows')+'…');\n  const q=new URLSearchParams({kind,offset:String(offset),sort:sort.value,search:search.value.trim()});\n  try{\n   const response=await fetch('/api/private/catalog?'+q,{credentials:'same-origin',cache:'no-store'});\n   const payload=await response.json();\n   if(current!==queryId)return;\n   if(!response.ok)throw Error(payload.error==='not_authenticated'?'Session expired — sign in again.':payload.error==='server_not_found'?'No authorized server is connected.':'Your private library could not be reached.');\n   if(!Array.isArray(payload.items))throw Error('Invalid catalog response');\n   const frag=document.createDocumentFragment();\n   payload.items.forEach(item=>frag.append(card(item)));\n   grid.append(frag);offset+=payload.items.length;total=payload.total||0;\n   done=payload.items.length===0||offset>=total;\n   $('library-count').textContent=total.toLocaleString()+' '+(kind==='movies'?'movies':'TV shows');\n   status(total?offset+' of '+total+' titles':'No matching titles in this library.');\n   more.hidden=done;\n   if(!done&&grid.scrollHeight<window.innerHeight+500){busy=false;load();return;}\n  }catch(e){if(current===queryId){status(e.message||'Unable to load library');more.hidden=false;more.textContent='Try again';}}\n  finally{if(current===queryId)busy=false;}\n }\n function reset(next){\n  if(next)kind=next;\n  queryId++;offset=0;total=0;done=false;busy=false;grid.replaceChildren();detail.hidden=true;more.textContent='Load more';\n  tabs.forEach(t=>{const active=t.dataset.kind===kind;t.setAttribute('aria-selected',String(active));t.classList.toggle('selected',active);});\n  $('library-count').textContent='';\n  load();\n }\n tabs.forEach(tab=>tab.addEventListener('click',()=>reset(tab.dataset.kind)));\n more.addEventListener('click',load);\n sort.addEventListener('change',()=>reset());\n search.addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>reset(),280);});\n if('IntersectionObserver' in window){\n  const observer=new IntersectionObserver(entries=>{if(entries[0].isIntersecting&&!busy&&!done)load();},{rootMargin:'700px'});\n  observer.observe($('library-sentinel'));\n }\n reset('movies');\n})();";
function viewerHTML(user,servers) {
 const linked=servers.filter(s=>s.status==='paired'&&s.server_identity);
 const label=linked.length?escapeHTML(linked[0].display_name):'No paired server';
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Yarr · Your Library</title><style>'+appCSS+'</style></head><body>'+
 '<header class="appnav"><a class="appbrand" href="/app">YARR.</a><nav class="navlinks"><a href="/account">Account</a><a href="/api/private/health">Connection test</a></nav></header>'+
 '<main class="appmain"><section class="intro"><div><div class="eyebrow">Your personal library</div><h1>Movies &amp; Television</h1><p>Browse the media on your own server.</p></div><div class="connection">Server: '+label+' · Private connection</div></section>'+
 '<div class="toolbar"><button class="tab selected" type="button" data-kind="movies" aria-selected="true">Movies</button><button class="tab" type="button" data-kind="tv" aria-selected="false">TV Shows</button><input id="library-search" aria-label="Search your library" placeholder="Search titles…" autocomplete="off"><select id="library-sort" aria-label="Sort library"><option value="title">Title</option><option value="recent">Recently added</option><option value="year">Year</option><option value="rating">Rating</option></select><span id="library-count"></span></div>'+
 '<div id="media-grid" class="media-grid"></div><p id="media-state" role="status">Connecting to your server…</p><button id="load-more" hidden>Load more</button><div id="library-sentinel" aria-hidden="true"></div>'+
 '<p style="margin-top:50px;font-size:13px">Read-only preview. Remote playback is not enabled yet.</p></main>'+
 '<div id="media-detail" hidden role="dialog" aria-modal="true" aria-label="Media details"><div class="detail-panel"><div id="detail-poster"></div><div><div class="eyebrow">From your library</div><h2 id="detail-title"></h2><p id="detail-meta"></p><p id="detail-genres"></p><p id="detail-watched"></p><p>Playback will be available after per-device authorization is finished.</p><button id="detail-close">Close</button></div></div></div>'+
 '<script src="/viewer-client.js" defer></script></body></html>';
}

function accountHTML(user,enabled,message='',servers=[]) {
 const title=user?'My Account':'Sign in to Yarr';
 const action=user?'<form method="post" action="/auth/logout"><button class="btn" type="submit">Sign out</button></form>':(enabled?'<a class="btn primary" href="/auth/google/start">Continue with Google</a>':'<p class="note">Google Sign-In is being configured. Account creation is not available yet.</p>');
 const details=user?'<div class="card"><h3>'+escapeHTML(user.display_name||'Your account')+'</h3><p>'+escapeHTML(user.email)+'</p><p class="note">Manage registered servers below. Only you can see your server entries.</p></div>'+serversHTML(servers):'<p class="lead">Sign in to manage your personal Yarr server and devices. Each account keeps its own servers separate.</p>';
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+title+' — Yarr</title><style>'+accountCSS+'</style></head><body><div class="wrap"><nav class="nav"><a href="/" class="brand">YARR.</a><a href="/" class="link">Home</a></nav><main class="hero"><p class="eyebrow">Personal media account</p><h1>'+title+'</h1>'+details+(message?'<p class="note">'+escapeHTML(message)+'</p>':'')+'<div class="actions">'+action+'</div></main><footer class="note">Yarr development preview · No media streaming through the account Worker</footer></div></body></html>';
}
const accountCSS = ':root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0b1019;color:#f6f3ed}*{box-sizing:border-box}.wrap{max-width:800px;margin:auto;padding:0 28px}.nav{display:flex;justify-content:space-between;align-items:center;padding:28px 0;border-bottom:1px solid #ffffff25}.brand{font-size:24px;font-weight:900;text-decoration:none;color:#fff}.link{color:#cfc1f9}.hero{padding:72px 0 90px}.hero h1{font-size:clamp(40px,7vw,66px);letter-spacing:-.05em}.lead{font-size:19px;line-height:1.6;color:#c3c6d2}.eyebrow{color:#b69cfa;letter-spacing:.16em;font-weight:700;font-size:12px;text-transform:uppercase}.note{color:#aaaebc;font-size:14px;line-height:1.65}.card{padding:24px;border:1px solid #ffffff28;border-radius:14px}.card p{color:#c4c6cf}.actions{margin-top:25px}.btn{display:inline-block;border:1px solid #8d6be5;border-radius:10px;background:#8d6be5;padding:14px 22px;color:#101019;text-decoration:none;font-weight:700;cursor:pointer}.block{margin:40px 0 60px}.block h2{font-size:30px}.server{border:1px solid #ffffff25;border-radius:13px;padding:20px;margin:16px 0}.server h3{margin:0}.serverhead{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.tag{color:#ddcba2;background:#413522;padding:5px 9px;border-radius:7px;font-size:12px}.serverform{display:grid;gap:16px;margin-top:22px}.serverform label{font-size:14px;color:#ddd;display:grid;gap:7px}.serverform input{border:1px solid #525468;border-radius:8px;padding:14px;background:#151d2e;color:white;font:inherit;width:100%}.smallbtn{border:1px solid #7b7182;background:transparent;color:#d9d0e3;padding:9px 13px;border-radius:8px;cursor:pointer}';
export default { async fetch(req,env) {
 const u=new URL(req.url);
 try {
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
  if(req.method==='GET'&&u.pathname==='/viewer-client.js')return new Response(appClientJS,{headers:{'content-type':'application/javascript; charset=utf-8','cache-control':'private, no-store','x-content-type-options':'nosniff'}});
  if(req.method==='GET'&&u.pathname==='/api/private/catalog')return privateCatalog(req,env);
  if(req.method==='GET'&&u.pathname.startsWith('/api/private/artwork/'))return privateArtwork(req,env);
  if(req.method==='GET'&&u.pathname==='/viewer'){
   const user=await currentUser(req,env);
   if(!user)return redirect('/account');
   return new Response(viewerHTML(user,await listServers(env,user.id)),{headers:{...HTML_HEADERS,'content-security-policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",'cache-control':'private, no-store'}});
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
  if(u.pathname.startsWith('/auth/'))return json({error:'not_found'},404);
  if(u.pathname==='/api/private' || u.pathname.startsWith('/api/private/'))return json({error:'not_found'},404);
  // This Worker owns account, login and pairing routes. All other application
  // paths are served by the paired local One-Eyed Willie server.
  if(u.pathname!=='/'&&u.pathname!=='/index.html')return proxyInstalledApp(req,env);
  if(req.method!=='GET'&&req.method!=='HEAD')return json({error:'method_not_allowed'},405);
  if(u.pathname==='/'||u.pathname==='/index.html') {
   const user=await currentUser(req,env);
   if(user)return proxyInstalledApp(req,env,'/');
   const cta=user?'<a class="btn primary" href="/app">Open App</a><a class="btn" href="/account">My Account</a>':authReady(env)?'<a class="btn primary" href="/auth/google/start">Sign in with Google</a>':'<a class="btn primary" href="/account">Account setup</a>';
   const rendered=page.replace('<a class="btn primary" href="#setup">See how it works</a>',cta+'<a class="btn" href="#setup">See how it works</a>')
     .replace('Server download & sign-in are coming.','Server downloads are coming.')
     .replace('Public downloads, Google Sign-In, and account-based pairing are not available yet.','Public downloads and account-based server pairing are not available yet.');
   return new Response(req.method==='HEAD'?null:rendered,{headers:{...HTML_HEADERS,'cache-control':'private, no-store'}});
  }
  return json({error:'not_found'},404);
 }catch(_) {return json({error:'temporarily_unavailable'},503);}
}};
