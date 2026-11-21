// node --test cloudflare/yarr/test/
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,generateKeyPairSync,createSign} from 'node:crypto';
import {loadWorker,makeEnv,signedInUser,pairedServer,request,newPassKey,digest,mockFetch,jsonResponse,b64url} from './harness.mjs';

const ACC='https://accounts.yarr.media';
const PUB='https://yarr.media';
const formHeaders=user=>({cookie:user.cookie,origin:ACC,'sec-fetch-site':'same-origin'});

async function verifyPass(pass,publicJwk){
 const [h,c,s]=pass.split('.');
 const key=await webcrypto.subtle.importKey('jwk',{kty:'OKP',crv:'Ed25519',x:publicJwk.x},{name:'Ed25519'},false,['verify']);
 const ok=await webcrypto.subtle.verify({name:'Ed25519'},key,Buffer.from(s,'base64url'),new TextEncoder().encode(h+'.'+c));
 return {ok,header:JSON.parse(Buffer.from(h,'base64url')),claims:JSON.parse(Buffer.from(c,'base64url'))};
}

test('existing public pages and health still work', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const home=await request(worker,env,'GET',PUB+'/');
 assert.equal(home.status,200);
 assert.match(await home.text(),/og:image/);
 const health=await request(worker,env,'GET',PUB+'/health');
 assert.equal((await health.json()).database,'ready');
 assert.equal((await request(worker,env,'GET',PUB+'/privacy')).status,200);
});

test('Google TV sign-in: code, approval, token, profile, sign-out', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const start=await request(worker,env,'POST',PUB+'/api/device/code',{json:{device_name:'Living room TV',device_type:'google_tv'}});
 assert.equal(start.status,201);
 const code=await start.json();
 assert.match(code.user_code,/^[A-Z2-9]{4}-[A-Z2-9]{4}$/);
 assert.equal(code.verification_uri,PUB+'/activate');

 let poll=await request(worker,env,'POST',PUB+'/api/device/token',{json:{device_code:code.device_code}});
 assert.equal((await poll.json()).error,'authorization_pending');
 poll=await request(worker,env,'POST',PUB+'/api/device/token',{json:{device_code:code.device_code}});
 assert.equal((await poll.json()).error,'slow_down','polling faster than the interval is slowed down');

 // yarr.media/activate sends people to the accounts host.
 const short=await request(worker,env,'GET',PUB+'/activate?code='+code.user_code);
 assert.equal(short.headers.get('location'),ACC+'/activate?code='+code.user_code);
 const confirm=await request(worker,env,'GET',ACC+'/activate?code='+code.user_code,{headers:{cookie:user.cookie}});
 assert.match(await confirm.text(),/Living room TV/);

 const bad=await request(worker,env,'POST',ACC+'/activate',{headers:{cookie:user.cookie,origin:'https://evil.example'},form:{code:code.user_code,decision:'approve'}});
 assert.equal(bad.status,403,'cross-site approval is refused');
 const approve=await request(worker,env,'POST',ACC+'/activate',{headers:formHeaders(user),form:{code:code.user_code.toLowerCase(),decision:'approve'}});
 assert.equal(approve.headers.get('location'),'/activate?done=approved');

 env.ACCOUNTS.raw.prepare("UPDATE device_login_requests SET last_polled_at=NULL").run();
 const granted=await request(worker,env,'POST',PUB+'/api/device/token',{json:{device_code:code.device_code}});
 const token=await granted.json();
 assert.equal(granted.status,200);
 assert.match(token.access_token,/^ydv_/);
 const again=await request(worker,env,'POST',PUB+'/api/device/token',{json:{device_code:code.device_code}});
 assert.equal((await again.json()).error,'invalid_grant','a code yields exactly one credential');

 const auth={authorization:'Bearer '+token.access_token};
 const me=await (await request(worker,env,'GET',PUB+'/api/device/me',{headers:auth})).json();
 assert.equal(me.user.email,user.email);
 assert.equal(me.device.name,'Living room TV');
 assert.equal(me.pro.active,false);

 const page=await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text();
 assert.match(page,/Signed-in devices/);
 assert.match(page,/Living room TV/);

 const out=await request(worker,env,'POST',PUB+'/api/device/signout',{headers:auth});
 assert.equal(out.status,200);
 assert.equal((await request(worker,env,'GET',PUB+'/api/device/me',{headers:auth})).status,401);
});

test('a signed-in TV finds its server and gets a 1-hour pass for remote playback', async()=>{
 const key=await newPassKey('k-tv');
 const worker=await loadWorker(),env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(key)});
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 const db=env.ACCOUNTS.raw;
 db.prepare("UPDATE servers SET public_ip='76.183.183.204'").run();
 const token='ydv_'+'t'.repeat(43);
 db.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES('tv1',?,'Living room TV','google_tv',?,datetime('now','+1 day'))").run(user.id,await digest(token));
 const auth={authorization:'Bearer '+token};
 const me=await (await request(worker,env,'GET',PUB+'/api/device/me',{headers:auth})).json();
 assert.deepEqual(me.servers.map(s=>[s.id,s.server_identity,s.remote_address]),[[server.id,server.identity,'https://76-183-183-204.sslip.io']]);
 const free=await request(worker,env,'POST',PUB+'/api/passes',{headers:auth,json:{server_id:server.id}});
 assert.equal(free.status,402,'remote playback needs Pro');
 assert.equal((await free.json()).error,'pro_required');
 db.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1',?,'active','manual')").run(user.id);
 const res=await request(worker,env,'POST',PUB+'/api/passes',{headers:auth,json:{server_id:server.id}});
 assert.equal(res.status,200);
 const body=await res.json();
 assert.equal(body.remote_address,'https://76-183-183-204.sslip.io');
 const keys=await (await request(worker,env,'GET',PUB+'/api/passes/keys')).json();
 const pass=await verifyPass(body.pass,keys.keys[0]);
 assert.ok(pass.ok);
 assert.equal(pass.claims.aud,server.identity);
 assert.equal(pass.claims.dev,'tv1');
 assert.equal(pass.claims.exp-pass.claims.iat,3600);
 assert.equal((await request(worker,env,'POST',PUB+'/api/passes',{headers:auth,json:{server_id:'99999999-2222-3333-4444-555555555555'}})).status,404);
});

test('activation needs sign-in and keeps the code through Google sign-in', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const page=await (await request(worker,env,'GET',ACC+'/activate?code=ABCD-EFGH')).text();
 assert.match(page,/\/auth\/google\/start\?return=%2Factivate%3Fcode%3DABCD-EFGH/);
 const start=await request(worker,env,'GET',PUB+'/auth/google/start?return='+encodeURIComponent('/activate?code=ABCD-EFGH'));
 assert.equal(start.status,303);
 assert.equal(env.ACCOUNTS.raw.prepare('SELECT return_to FROM oauth_flows').get().return_to,'/activate?code=ABCD-EFGH');
 await request(worker,env,'GET',PUB+'/auth/google/start?return='+encodeURIComponent('https://evil.example/'));
 const rows=env.ACCOUNTS.raw.prepare('SELECT return_to FROM oauth_flows ORDER BY rowid').all();
 assert.equal(rows[1].return_to,null,'open redirects are dropped');
 // The accounts host keeps the return path when it bounces to the sign-in host.
 const bounce=await request(worker,env,'GET',ACC+'/auth/google/start?return=%2Factivate');
 assert.equal(bounce.headers.get('location'),PUB+'/auth/google/start?return=%2Factivate');
});

test('Google callback records the identity and returns to the saved path', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const start=await request(worker,env,'GET',PUB+'/auth/google/start?return='+encodeURIComponent('/activate?code=ABCD-EFGH'));
 const state=new URL(start.headers.get('location')).searchParams.get('state');
 const nonce=new URL(start.headers.get('location')).searchParams.get('nonce');
 const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
 const jwk={...publicKey.export({format:'jwk'}),kid:'k1',alg:'RS256',use:'sig'};
 const now=Math.floor(Date.now()/1000);
 const header=b64url(Buffer.from(JSON.stringify({alg:'RS256',kid:'k1',typ:'JWT'})));
 const claims=b64url(Buffer.from(JSON.stringify({iss:'https://accounts.google.com',aud:'client-id',sub:'g-999',email:'new@example.com',email_verified:true,name:'New',nonce,iat:now,exp:now+600})));
 const sig=createSign('RSA-SHA256').update(header+'.'+claims).sign(privateKey).toString('base64url');
 const mock=mockFetch(url=>{
  if(url==='https://oauth2.googleapis.com/token')return jsonResponse({id_token:header+'.'+claims+'.'+sig});
  if(url==='https://www.googleapis.com/oauth2/v3/certs')return jsonResponse({keys:[jwk]});
 });
 try{
  const cb=await request(worker,env,'GET',PUB+'/auth/google/callback?state='+state+'&code=abc',{headers:{cookie:'__Host-yarr_oauth='+state}});
  assert.equal(cb.status,303);
  assert.equal(cb.headers.get('location'),ACC+'/activate?code=ABCD-EFGH');
  assert.match(cb.headers.get('set-cookie'),/__Secure-yarr_session=/);
 }finally{mock.restore();}
 const identity=env.ACCOUNTS.raw.prepare("SELECT provider,subject,email FROM user_identities").get();
 assert.deepEqual({...identity},{provider:'google',subject:'g-999',email:'new@example.com'});
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT event FROM audit_log").get().event,'signed_in');
});

test('Google callback returns owner workspace login to the canonical host', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const start=await request(worker,env,'GET',PUB+'/auth/google/start?return='+encodeURIComponent('/owner/'));
 const state=new URL(start.headers.get('location')).searchParams.get('state');
 const nonce=new URL(start.headers.get('location')).searchParams.get('nonce');
 const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
 const jwk={...publicKey.export({format:'jwk'}),kid:'k1',alg:'RS256',use:'sig'};
 const now=Math.floor(Date.now()/1000);
 const header=b64url(Buffer.from(JSON.stringify({alg:'RS256',kid:'k1',typ:'JWT'})));
 const claims=b64url(Buffer.from(JSON.stringify({iss:'https://accounts.google.com',aud:'client-id',sub:'g-999',email:'new@example.com',email_verified:true,name:'New',nonce,iat:now,exp:now+600})));
 const sig=createSign('RSA-SHA256').update(header+'.'+claims).sign(privateKey).toString('base64url');
 const mock=mockFetch(url=>{
  if(url==='https://oauth2.googleapis.com/token')return jsonResponse({id_token:header+'.'+claims+'.'+sig});
  if(url==='https://www.googleapis.com/oauth2/v3/certs')return jsonResponse({keys:[jwk]});
 });
 try{
  const cb=await request(worker,env,'GET',PUB+'/auth/google/callback?state='+state+'&code=abc',{headers:{cookie:'__Host-yarr_oauth='+state}});
  assert.equal(cb.status,303);
  assert.equal(cb.headers.get('location'),PUB+'/owner/');
  assert.match(cb.headers.get('set-cookie'),/__Secure-yarr_session=/);
 }finally{mock.restore();}
 const identity=env.ACCOUNTS.raw.prepare("SELECT provider,subject,email FROM user_identities").get();
 assert.deepEqual({...identity},{provider:'google',subject:'g-999',email:'new@example.com'});
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT event FROM audit_log").get().event,'signed_in');
});

test('remote-access passes: owner only, Pro only, signed, verifiable', async()=>{
 const worker=await loadWorker();
 const key=await newPassKey('k-2026');
 const env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(key)});
 const user=await signedInUser(env);
 const other=await signedInUser(env,{id:'user-2',email:'other@example.com'});
 const server=pairedServer(env,user.id,{publicUrl:'https://home.example.net'});
 const asks=(who,serverId)=>request(worker,env,'POST',ACC+'/api/passes',{headers:{cookie:who.cookie,origin:ACC},json:{server_id:serverId}});

 assert.equal((await asks(user,server.id)).status,402,'Free accounts get no pass');
 env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1',?,'active','manual')").run(user.id);
 assert.equal((await asks(other,server.id)).status,404,'only the owner gets a pass');
 const noOrigin=await request(worker,env,'POST',ACC+'/api/passes',{headers:{cookie:user.cookie},json:{server_id:server.id}});
 assert.equal(noOrigin.status,403,'cookie-authenticated requests need the site origin');

 const res=await asks(user,server.identity);
 assert.equal(res.status,200);
 const body=await res.json();
 assert.equal(body.remote_address,'https://home.example.net');
 const keys=await (await request(worker,env,'GET',PUB+'/api/passes/keys')).json();
 assert.equal(keys.keys.length,1);
 assert.equal(keys.keys[0].kid,'k-2026');
 assert.equal(keys.keys[0].d,undefined,'the private part is never published');
 const {ok,header,claims}=await verifyPass(body.pass,keys.keys[0]);
 assert.ok(ok);
 assert.deepEqual(header,{alg:'EdDSA',typ:'yarr-pass',kid:'k-2026'});
 assert.equal(claims.aud,server.identity);
 assert.equal(claims.sub,user.id);
 assert.equal(claims.role,'owner');
 assert.ok(claims.exp-claims.iat<=3600);

 // Browser flow hands off to the server's own address.
 const open=await request(worker,env,'GET',ACC+'/remote/open?server='+server.id+'&return=%2Fmovies',{headers:{cookie:user.cookie}});
 const target=new URL(open.headers.get('location'));
 assert.equal(target.origin+target.pathname,'https://home.example.net/remote/start');
 assert.equal(target.searchParams.get('return'),'/movies');
 const browserPass=await verifyPass(target.searchParams.get('pass'),keys.keys[0]);
 assert.ok(browserPass.ok);
 assert.equal(browserPass.claims.exp-browserPass.claims.iat,12*3600,'browser passes outlast a movie');
});

test('passes are off until a signing key is configured', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1',?,'active','manual')").run(user.id);
 const res=await request(worker,env,'POST',ACC+'/api/passes',{headers:{cookie:user.cookie,origin:ACC},json:{server_id:server.id}});
 assert.equal(res.status,503);
 assert.deepEqual((await (await request(worker,env,'GET',PUB+'/api/passes/keys')).json()).keys,[]);
});

const ONE_TIME_TEST_ENV={YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_x',STRIPE_WEBHOOK_SECRET:'whsec_test',STRIPE_PRO_PRICE_ID:'price_pro'};

test('payments: the $29 one-time checkout is the only purchase path', async()=>{
 const worker=await loadWorker();
 const off=makeEnv(),user=await signedInUser(off);
 assert.match(await (await request(worker,off,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text(),/not on sale yet/);
 const env=makeEnv(ONE_TIME_TEST_ENV),buyer=await signedInUser(env);
 const mock=mockFetch(()=>null); // any Stripe call from the removed subscription code would throw
 try{
  const page=await request(worker,env,'GET',ACC+'/',{headers:{cookie:buyer.cookie}});
  const html=await page.text();
  assert.match(html,/\$29 one-time purchase/);
  assert.match(html,/action="\/api\/stripe\/checkout"/);
  assert.doesNotMatch(html,/billing\/portal|billing\/checkout|Manage billing|Billing history/);
  assert.match(page.headers.get('content-security-policy'),/form-action 'self' https:\/\/checkout\.stripe\.com/);
  assert.doesNotMatch(page.headers.get('content-security-policy'),/billing\.stripe\.com/);
  for(const path of ['/account/billing/checkout','/account/billing/portal']){
   const r=await request(worker,env,'POST',ACC+path,{headers:formHeaders(buyer),form:{}});
   assert.ok(!(r.headers.get('location')||'').includes('stripe.com'),path);
  }
  const old=await request(worker,env,'POST',PUB+'/api/stripe/webhook',{body:'{}'});
  assert.notEqual(old.status,200,'the subscription webhook on yarr.media is gone');
 }finally{mock.restore();}
 assert.equal(mock.calls.filter(c=>c.url.includes('api.stripe.com')).length,0);
});

test('manual Pro grants still count and show on the account page', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1',?,'active','manual')").run(user.id);
 const html=await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text();
 assert.match(html,/Yarr Media Pro/);
 assert.match(html,/No end date/);
 env.ACCOUNTS.raw.prepare("UPDATE subscriptions SET current_period_end=datetime('now','-10 days')").run();
 assert.match(await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text(),/not on sale yet/,'expired grants end');
});

test('account deletion removes everything without calling Stripe', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 pairedServer(env,user.id);
 const db=env.ACCOUNTS.raw;
 db.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1',?,'active','manual')").run(user.id);
 db.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES('d1',?,'TV','google_tv','h',datetime('now','+1 day'))").run(user.id);
 const unconfirmed=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'delete'}});
 assert.equal(unconfirmed.headers.get('location'),'/account?delete=confirm');
 const mock=mockFetch(()=>null);
 try{
  const ok=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'DELETE'}});
  assert.equal(ok.headers.get('location'),PUB+'/?account=deleted');
  assert.match(ok.headers.get('set-cookie'),/Max-Age=0/);
 }finally{mock.restore();}
 assert.equal(mock.calls.length,0);
 for(const t of ['users','sessions','servers','devices','subscriptions','user_identities'])
  assert.equal(db.prepare('SELECT COUNT(*) n FROM '+t).get().n,0,t);
 assert.equal(db.prepare("SELECT user_id,event FROM audit_log WHERE event='account_deleted'").get().user_id,null);
});

test('devices can be signed out from the account page', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 env.ACCOUNTS.raw.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES('0f0f0f0f-0000-1111-2222-333333333333',?,'TV','google_tv','h',datetime('now','+1 day'))").run(user.id);
 const r=await request(worker,env,'POST',ACC+'/account/devices',{headers:formHeaders(user),form:{action:'revoke',id:'0f0f0f0f-0000-1111-2222-333333333333'}});
 assert.equal(r.headers.get('location'),'/account?device=revoked');
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT token_hash FROM devices").get().token_hash,null);
});

test('remote address: public HTTPS only, owner only', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 const save=address=>request(worker,env,'POST',ACC+'/account/servers/address',{headers:formHeaders(user),form:{id:server.id,address}});
 assert.equal((await save('http://192.168.1.5')).headers.get('location'),'/account?server=bad_address');
 assert.equal((await save('https://media.example.net/')).headers.get('location'),'/account?server=address_saved');
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT public_url FROM servers").get().public_url,'https://media.example.net');
});

test('daily cleanup removes only expired rows', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const db=env.ACCOUNTS.raw;
 db.prepare("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES('old',?,'old-h',datetime('now','-1 day'))").run(user.id);
 db.prepare("INSERT INTO device_login_requests(device_code_hash,user_code_hash,expires_at) VALUES('a','b',datetime('now','-2 days'))").run();
 db.prepare("INSERT INTO device_login_requests(device_code_hash,user_code_hash,expires_at) VALUES('c','d',datetime('now','+5 minutes'))").run();
 db.prepare("INSERT INTO pairing_rate_limits(ip_hash,window,count) VALUES('x','devcode:1',1),('y','devcode:'||?,1)").run(String(Math.floor(Date.now()/60000)));
 const waits=[];
 await worker.scheduled({},env,{waitUntil:p=>waits.push(p)});
 await Promise.all(waits);
 assert.equal(db.prepare("SELECT COUNT(*) n FROM sessions").get().n,1);
 assert.equal(db.prepare("SELECT device_code_hash FROM device_login_requests").get().device_code_hash,'c');
 assert.equal(db.prepare("SELECT ip_hash FROM pairing_rate_limits").get().ip_hash,'y');
});

test('servers record the public IP they check in from', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 const secret='s'.repeat(48);
 env.ACCOUNTS.raw.prepare("UPDATE servers SET connection_secret_hash=? WHERE id=?").run(await digest(secret),server.id);
 const beat=ip=>request(worker,env,'POST',PUB+'/api/connection/heartbeat',{headers:{authorization:'Bearer '+secret,'cf-connecting-ip':ip}});
 assert.equal((await beat('76.183.183.204')).status,200);
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT public_ip FROM servers").get().public_ip,'76.183.183.204');
 await beat('192.168.1.20');
 await beat('2001:db8::1');
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT public_ip FROM servers").get().public_ip,'76.183.183.204','private and IPv6 addresses are not stored');
});

test('app.yarr.media: starter page, service worker and connection', async()=>{
 const worker=await loadWorker();
 const env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(await newPassKey('k-app'))});
 const APP='https://app.yarr.media';
 // Signed out: sent to sign-in, and back to the same page afterwards.
 const out=await request(worker,env,'GET',APP+'/movies?x=1');
 assert.equal(out.headers.get('location'),ACC+'/auth/google/start?return='+encodeURIComponent('/open-app?path='+encodeURIComponent('/movies?x=1')));
 const back=await request(worker,env,'GET',ACC+'/open-app?path='+encodeURIComponent('/movies?x=1'));
 assert.equal(back.headers.get('location'),APP+'/movies?x=1');
 assert.equal((await request(worker,env,'GET',ACC+'/open-app?path=//evil.example')).headers.get('location'),APP+'/');

 const user=await signedInUser(env);
 const page=await request(worker,env,'GET',APP+'/',{headers:{cookie:user.cookie}});
 assert.equal(page.status,200);
 assert.match(await page.text(),/serviceWorker\.register\('\/__yarr\/sw\.js'/);
 assert.match(page.headers.get('content-security-policy'),/worker-src 'self'/);
 const sw=await request(worker,env,'GET',APP+'/__yarr/sw.js');
 assert.equal(sw.headers.get('service-worker-allowed'),'/');
 const swText=await sw.text();
 assert.match(swText,/Yarr-Pass/);
 new Function(swText); // valid JavaScript

 const conn=()=>request(worker,env,'GET',APP+'/__yarr/connection',{headers:{cookie:user.cookie}});
 assert.equal((await conn()).status,404,'no server yet');
 const server=pairedServer(env,user.id);
 assert.equal((await conn()).status,409,'no address yet');
 env.ACCOUNTS.raw.prepare("UPDATE servers SET public_ip='76.183.183.204'").run();
 const noPro=await conn();
 assert.equal(noPro.status,402);
 assert.equal((await noPro.json()).redirect,ACC+'/?remote=pro_required');
 env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m',?,'active','manual')").run(user.id);
 const ok=await (await conn()).json();
 assert.equal(ok.server_origin,'https://76-183-183-204.sslip.io');
 const keys=await (await request(worker,env,'GET',PUB+'/api/passes/keys')).json();
 const {ok:valid,claims}=await verifyPass(ok.pass,keys.keys[0]);
 assert.ok(valid);
 assert.equal(claims.aud,server.identity);
 // A custom address wins over the automatic one.
 env.ACCOUNTS.raw.prepare("UPDATE servers SET public_url='https://media.example.net'").run();
 assert.equal((await (await conn()).json()).server_origin,'https://media.example.net');
 // Signed-out connection requests explain where to sign in.
 const anon=await request(worker,env,'GET',APP+'/__yarr/connection');
 assert.equal(anon.status,401);
 assert.match((await anon.json()).redirect,/\/auth\/google\/start\?return=%2Fopen-app/);
});

test('downloads: installer, TV shortcut, apt repository and page', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const home=await (await request(worker,env,'GET',PUB+'/')).text();
 assert.match(home,/curl -fsSL https:\/\/yarr\.media\/install\.sh \| sudo bash/);
 assert.match(home,/yarr\.media\/tv/);
 assert.doesNotMatch(home,/coming soon/i);
 const tv=await request(worker,env,'GET',PUB+'/tv');
 assert.equal(tv.headers.get('location'),'https://github.com/blarkin13/one-eyed-willie/releases/latest/download/yarr-media-google-tv.apk');
 const phone=await request(worker,env,'GET',PUB+'/android');
 assert.equal(phone.headers.get('location'),'https://github.com/blarkin13/one-eyed-willie/releases/latest/download/yarr-media-android.apk');
 assert.match(home,/yarr\.media\/android/);
 const apt=await request(worker,env,'GET',PUB+'/apt');
 assert.match(await apt.text(),/signed-by=\/usr\/share\/keyrings\/yarr-media\.gpg/);
 const mock=mockFetch(url=>{
  if(url.endsWith('/main/deploy/install.sh'))return new Response('#!/usr/bin/env bash\necho hi\n');
  if(url.endsWith('/apt-repo/dists/stable/InRelease'))return new Response('signed');
  if(url.endsWith('/apt-repo/pool/main/y/yarr-media/yarr-media_1.2.3_all.deb'))return new Response('deb');
 });
 try{
  const sh=await request(worker,env,'GET',PUB+'/install.sh');
  assert.equal(sh.headers.get('content-type'),'text/x-shellscript; charset=utf-8');
  assert.match(await sh.text(),/echo hi/);
  assert.equal(await (await request(worker,env,'GET',PUB+'/apt/dists/stable/InRelease')).text(),'signed');
  const deb=await request(worker,env,'GET',PUB+'/apt/pool/main/y/yarr-media/yarr-media_1.2.3_all.deb');
  assert.equal(deb.headers.get('content-type'),'application/vnd.debian.binary-package');
  assert.equal((await request(worker,env,'GET',PUB+'/apt/secrets.txt')).status,404,'only repository files');
 }finally{mock.restore();}
});

test('servers learn their public IP and owners can check remote reachability', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 const secret='t'.repeat(48);
 env.ACCOUNTS.raw.prepare("UPDATE servers SET connection_secret_hash=? WHERE id=?").run(await digest(secret),server.id);
 const beat=await request(worker,env,'POST',PUB+'/api/connection/heartbeat',{headers:{authorization:'Bearer '+secret,'cf-connecting-ip':'76.183.183.204'}});
 assert.equal((await beat.json()).public_ip,'76.183.183.204');
 let up=true;
 const mock=mockFetch(url=>url==='https://76-183-183-204.sslip.io/health'?(up?jsonResponse({status:'ok'}):jsonResponse({},502)):null);
 try{
  const ok=await request(worker,env,'GET',ACC+'/account/servers/check?id='+server.id,{headers:{cookie:user.cookie}});
  assert.equal(ok.headers.get('location'),'/account?server=reach_ok');
  up=false;
  const bad=await request(worker,env,'GET',ACC+'/account/servers/check?id='+server.id,{headers:{cookie:user.cookie}});
  assert.equal(bad.headers.get('location'),'/account?server=reach_fail');
 }finally{mock.restore();}
 const page=await (await request(worker,env,'GET',ACC+'/?server=reach_fail',{headers:{cookie:user.cookie}})).text();
 assert.match(page,/Forward TCP port 443/);
 assert.match(page,/Check remote access/);
});

test('app.yarr.media service worker keeps the household profile the server hands back', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const sw=await request(worker,env,'GET','https://app.yarr.media/__yarr/sw.js');
 const source=await sw.text();
 const store=new Map(),sent=[],listeners={};
 const cachesStub={open:async()=>({match:async k=>store.has(k)?new Response(store.get(k)):undefined,
  put:async(k,r)=>{store.set(k,await r.text())},delete:async k=>{store.delete(k)}})};
 const fetchStub=async(url,opts={})=>{
  if(url==='/__yarr/connection')return new Response(JSON.stringify({server_origin:'https://home.example',pass:'P',expires_at:new Date(Date.now()+3600e3).toISOString()}),{status:200});
  sent.push([url,opts.headers.get('x-yarr-profile')]);
  return new Response('{}',{status:200,headers:url.endsWith('/api/profiles/choose')?{'x-yarr-profile-set':'TOKEN.1.sig'}:{}});
 };
 const self={addEventListener:(type,fn)=>{listeners[type]=fn},location:{origin:'https://app.yarr.media'},skipWaiting(){},clients:{claim(){}}};
 new Function('self','caches','fetch',source)(self,cachesStub,fetchStub);
 const go=async(path,method='GET')=>{let done;listeners.fetch({request:new Request('https://app.yarr.media'+path,{method}),respondWith:p=>{done=p}});return done};
 await go('/api/viewer');
 await go('/api/profiles/choose','POST');
 await new Promise(r=>setTimeout(r,10));
 await go('/api/home');
 assert.deepEqual(sent.map(x=>x[1]),[null,null,'TOKEN.1.sig']);
 assert.equal(sent[2][0],'https://home.example/api/home');
 assert.equal(store.get('/__yarr/profile'),'TOKEN.1.sig');
});

test('servers keep one encrypted watch-history backup the owner can restore elsewhere', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 const server=pairedServer(env,user.id);
 const secret='s'.repeat(48);
 env.ACCOUNTS.raw.prepare("UPDATE servers SET connection_secret_hash=? WHERE id=?").run(await digest(secret),server.id);
 const auth={authorization:'Bearer '+secret};
 const blob=new Uint8Array([...new TextEncoder().encode('YRB1'),...new Uint8Array(80).fill(7)]);
 const put=(body,type='application/octet-stream',headers=auth)=>request(worker,env,'PUT',PUB+'/api/connection/backup',{headers:{...headers,'content-type':type,'content-length':String(body.length)},body});
 assert.equal((await put(blob,'application/octet-stream',{})).status,401);
 assert.equal((await put(new Uint8Array(80).fill(1))).status,400,'only the encrypted format is stored');
 assert.equal((await put(blob)).status,200);
 assert.equal((await put(blob)).status,200,'replaces, never piles up');
 const list=await (await request(worker,env,'GET',PUB+'/api/connection/backups',{headers:auth})).json();
 assert.deepEqual(list.backups.map(b=>[b.id,b.server_name,b.size,b.this_server]),[[server.id,'Home',84,true]]);
 const got=await request(worker,env,'GET',PUB+'/api/connection/backups/'+server.id,{headers:auth});
 assert.deepEqual(new Uint8Array(await got.arrayBuffer()),blob);
 // Another owner's server can't see it.
 const other=await signedInUser(env,{id:'user-2',email:'other@example.com'});
 const theirs=pairedServer(env,other.id,{id:'99999999-2222-3333-4444-555555555555',identity:'ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee'});
 env.ACCOUNTS.raw.prepare("UPDATE servers SET connection_secret_hash=? WHERE id=?").run(await digest('t'.repeat(48)),theirs.id);
 const peek=await request(worker,env,'GET',PUB+'/api/connection/backups/'+server.id,{headers:{authorization:'Bearer '+'t'.repeat(48)}});
 assert.equal(peek.status,404);
 // Deleting the account deletes its backups.
 const del=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'DELETE'}});
 assert.equal(del.status,303);
 assert.equal(env.ACCOUNTS.raw.prepare("SELECT COUNT(*) AS n FROM server_backups").get().n,0);
});
