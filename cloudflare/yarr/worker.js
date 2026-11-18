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


const YARR_TEST_PAGE="<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Yarr direct connection test</title><style>body{font:16px system-ui,sans-serif;background:#0c101b;color:#f4f2ef;max-width:680px;padding:40px 22px;margin:auto}h1{font-size:35px}p{line-height:1.55;color:#bfc4cc}a{color:#ba9dff}button{border:0;background:#9e84eb;color:#141020;padding:14px 18px;font:700 16px system-ui;border-radius:8px;cursor:pointer}button:disabled{opacity:.5}pre{white-space:pre-wrap;word-break:break-word;line-height:1.55;background:#252b38;padding:20px;border-radius:8px}small{color:#bfc4cc}</style></head><body><a href=\"/app\">Yarr</a><h1>Direct connection test</h1><p>Check whether your current Wi-Fi can exchange encrypted test data directly with your home Yarr server. No videos or personal files are accessed. Cloudflare carries only the connection setup.</p><button id=\"go\">Test connection</button><pre id=\"out\" role=\"status\" aria-live=\"polite\">Ready.</pre><small>The working Yarr video player is not changed by this test.</small><script>\n(()=>{'use strict';const btn=document.getElementById('go'),out=document.getElementById('out');const log=s=>{out.textContent+='\\n'+s};\nconst candidates=sdp=>{const list=(sdp||'').split(/\\r?\\n/).filter(x=>x.startsWith('a=candidate:'));return {total:list.length,host:list.filter(x=>/ typ host(?: |$)/.test(x)).length,srflx:list.filter(x=>/ typ srflx(?: |$)/.test(x)).length,relay:list.filter(x=>/ typ relay(?: |$)/.test(x)).length}};\nconst explain=pc=>{if(!pc)return 'No peer connection was initialized';const local=candidates(pc.localDescription?.sdp),remote=candidates(pc.remoteDescription?.sdp);return 'ICE='+pc.iceConnectionState+'; peer='+pc.connectionState+'; signaling='+pc.signalingState+'; gathering='+pc.iceGatheringState+'; candidates local='+JSON.stringify(local)+' remote='+JSON.stringify(remote)};\nfunction waitIce(pc){return new Promise((ok,no)=>{if(pc.iceGatheringState==='complete')return ok();const timer=setTimeout(()=>no(Error('STUN candidate discovery timed out')),25000);pc.addEventListener('icegatheringstatechange',function fn(){if(pc.iceGatheringState==='complete'){clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',fn);ok()}})})}\nasync function route(pc){const stats=await pc.getStats();const t=[...stats.values()].find(s=>s.type==='transport'&&s.selectedCandidatePairId);const pair=(t&&stats.get(t.selectedCandidatePairId))||[...stats.values()].find(s=>s.type==='candidate-pair'&&s.nominated&&s.state==='succeeded');if(!pair)return 'Candidate path was not reported';const l=stats.get(pair.localCandidateId),r=stats.get(pair.remoteCandidateId),a=l?.candidateType||'unknown',b=r?.candidateType||'unknown';return 'ICE path: '+a+' / '+b+(a==='relay'||b==='relay'?' (relayed)':' (no TURN relay)')}\nbtn.onclick=async()=>{btn.disabled=true;out.textContent='Starting encrypted connection…';let pc;try{\npc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});const dc=pc.createDataChannel('yarr-network-probe-v1');dc.binaryType='arraybuffer';pc.addEventListener('iceconnectionstatechange',()=>log('ICE state: '+pc.iceConnectionState));pc.addEventListener('connectionstatechange',()=>log('Peer state: '+pc.connectionState));dc.addEventListener('close',()=>log('Data channel closed'));let size=0,received=0,good=true;const begin=performance.now();\nconst done=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Peer data transfer timed out')),45000);dc.onopen=()=>{log('Peer connected; testing 256 KiB');dc.send('test')};dc.onerror=()=>reject(Error('Data-channel error'));dc.onmessage=({data})=>{if(typeof data==='string'){const obj=JSON.parse(data);if(obj.type==='start')size=obj.length;else if(obj.type==='done'){clearTimeout(timer);resolve()}}else{const bytes=new Uint8Array(data);for(let i=0;i<bytes.length;i++)if(bytes[i]!==((received+i)%251))good=false;received+=bytes.length}}});\nawait pc.setLocalDescription(await pc.createOffer());await waitIce(pc);log('Negotiating with the paired home server…');\nconst res=await fetch('/api/network-test/offer',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'content-type':'application/json'},body:JSON.stringify({type:'offer',sdp:pc.localDescription.sdp})});\nif(!res.ok)throw Error('Home diagnostic unavailable (HTTP '+res.status+')');\nconst answer=await res.json();log('Diagnostic backend: '+(answer.diagnostic_origin||'unknown; server may be on an older version'));log('Home server answer: '+JSON.stringify(candidates(answer.sdp)));await pc.setRemoteDescription({type:answer.type,sdp:answer.sdp});log('Answer accepted; waiting for ICE and the data channel…');await done;\nif(!good||received!==262144||size!==262144)throw Error('Test data integrity mismatch ('+received+' bytes)');\nlog('PASS: '+received+' correct bytes in '+Math.round(performance.now()-begin)+' ms');log(await route(pc));log('Synthetic-data connectivity verified; real media playback not yet proven.');\n}catch(e){log('FAILED: '+(e?.message||String(e)));log('Diagnostics: '+explain(pc));log('If ICE stays checking or failed, the internet connections may block direct UDP. This does not mean your Yarr sign-in or Cloudflare connection is broken.')}finally{pc?.close();btn.disabled=false}};\n})();\n</script></body></html>";
const YARR_MEDIA_TEST_PAGE="<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Yarr • Direct movie playback test</title>\n<style>\nbody{font:16px system-ui,sans-serif;background:#0c101b;color:#f4f2ef;max-width:920px;padding:30px 18px;margin:auto}\nh1{font-size:30px}p,small{color:#bfc4cc;line-height:1.5}a{color:#ba9dff}\ninput{background:#1d2533;color:white;border:1px solid #64708b;padding:12px;border-radius:8px;max-width:150px;font-size:16px}\nbutton{border:0;background:#9573dc;color:#141020;padding:12px 18px;font:700 16px system-ui;border-radius:8px;cursor:pointer;margin:0 10px 10px 0}\nbutton:disabled{opacity:.4;cursor:not-allowed}video{width:100%;max-height:60vh;background:#000;border-radius:10px;margin:10px 0}\npre{white-space:pre-wrap;word-break:break-word;line-height:1.5;background:#202a3b;padding:16px;border-radius:10px}\nlabel{display:block;margin:12px 0}strong{color:#f4f2ef}\n</style>\n<script>window.YARR_DIRECT_TEST_MODE=true;</script>\n<script src=\"/assets/yarr-direct-client.js\" defer></script>\n</head><body>\n<a href=\"/app\">Back to Yarr</a>\n<h1>Direct movie playback test</h1>\n<p>This test streams video directly from your home server over WebRTC UDP 3478. The normal Yarr movie player is unchanged. Use a <strong>browser-playable MP4</strong> movie from your library to test video and seeking. Other formats will be tested separately.</p>\n<p>Find the media ID in the normal Yarr watch URL, for example <code>/watch/42</code> means ID <code>42</code>.</p>\n<label for=\"id\">Movie ID <input id=\"id\" type=\"number\" min=\"1\" step=\"1\" placeholder=\"42\" inputmode=\"numeric\"></label>\n<button id=\"play\" disabled>Play direct</button>\n<button id=\"seek\" disabled>Seek +60 seconds</button>\n<button id=\"stop\" disabled>Stop</button>\n<video id=\"video\" controls preload=\"none\" playsinline></video>\n<pre id=\"status\" role=\"status\" aria-live=\"polite\">Connecting direct peer…</pre>\n<small>Only use this test when your home server is running the experimental direct-media pilot. No normal video playback is changed.</small>\n<script>\n(()=>{'use strict';\nconst video=document.getElementById('video'),out=document.getElementById('status'),id=document.getElementById('id'),\n play=document.getElementById('play'),seek=document.getElementById('seek'),stop=document.getElementById('stop');\nconst log=txt=>{out.textContent+='\\n'+txt};\nfunction status(msg){log('Peer: '+msg);play.disabled=msg!=='connected';}\nwindow.addEventListener('yarr:peer:status',event=>status(event.detail));\nwindow.addEventListener('yarr:peer:bytes',event=>{document.title='Direct test: '+Math.round(event.detail/1024)+' KiB received';});\nif(window.YarrDirectPeerStatus)status(window.YarrDirectPeerStatus);\nplay.onclick=()=>{\n const number=Number(id.value);\n if(!Number.isSafeInteger(number)||number<1){log('Enter the numeric media ID from your /watch/<id> URL');return}\n window.YarrDirectTestBytes=0;\n video.src='/api/watch/'+number+'/stream?viewing=direct-pilot';\n video.load();\n video.play().then(()=>log('Video playing directly through peer')).catch(e=>log('Play: '+e.message));\n stop.disabled=false;seek.disabled=true;log('Opening movie '+number+' over direct WebRTC; watching for video bytes…');\n};\nseek.onclick=()=>{\n if(!Number.isFinite(video.duration)){log('Duration unavailable; cannot seek yet');return}\n const from=video.currentTime,to=Math.min(Math.max(0,video.duration-1),from+60);\n if(to<=from){log('Already near the end');return}\n video.currentTime=to;log('Seeking '+Math.round(from)+'s → '+Math.round(to)+'s over WebRTC');\n};\nstop.onclick=()=>{video.pause();video.removeAttribute('src');video.load();seek.disabled=true;stop.disabled=true;log('Stopped');};\nvideo.addEventListener('loadedmetadata',()=>{log('Metadata received; duration '+Math.round(video.duration)+'s');seek.disabled=!Number.isFinite(video.duration)});\nvideo.addEventListener('seeking',()=>log('Video seeking…'));\nvideo.addEventListener('seeked',()=>log('Seek completed at '+Math.round(video.currentTime)+'s'));\nvideo.addEventListener('playing',()=>log('Video playing; '+(window.YarrDirectTestBytes||0)+' direct peer bytes received so far'));\nvideo.addEventListener('error',()=>log('Video failed: '+(video.error?.message||'unsupported codec or media request failed')+'; peer bytes '+(window.YarrDirectTestBytes||0)));\nsetInterval(()=>{if(!video.paused&&video.readyState>0)out.dataset.bytes=String(window.YarrDirectTestBytes||0)},1000);\n})();\n</script></body></html>";
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
 return pairing+'<section class="block"><p class="eyebrow">Your servers</p><h2>Connected servers</h2><p class="note">The server link is tied to your Google account. Media access requires a separate secure connection.</p>'+cards+'<p class="note"><a href="/app">Open full One-Eyed Willie app</a></p></section>';
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
   const cta=user?'<a class="btn primary" href="/app">Open App</a><a class="btn" href="/account">My Account</a>':authReady(env)?'<a class="btn primary" href="/auth/google/start">Sign in with Google</a>':'<a class="btn primary" href="/account">Account setup</a>';
   const rendered=page.replace('<a class="btn primary" href="#setup">See how it works</a>',cta+'<a class="btn" href="#setup">See how it works</a>')
     .replace('Server download & sign-in are coming.','Server downloads are coming.')
     .replace('Public downloads, Google Sign-In, and account-based pairing are not available yet.','Public downloads and account-based server pairing are not available yet.');
   return new Response(req.method==='HEAD'?null:rendered,{headers:{...HTML_HEADERS,'cache-control':'private, no-store'}});
  }
  return json({error:'not_found'},404);
 }catch(_) {return json({error:'temporarily_unavailable'},503);}
}};
