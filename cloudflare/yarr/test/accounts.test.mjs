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

const STRIPE_ENV={STRIPE_SECRET_KEY:'sk_test_x',STRIPE_WEBHOOK_SECRET:'whsec_test',STRIPE_PRO_PRICE_ID:'price_pro'};
async function signedEvent(event,secret='whsec_test',t=Math.floor(Date.now()/1000)){
 const payload=JSON.stringify(event);
 const key=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const mac=Buffer.from(await webcrypto.subtle.sign('HMAC',key,new TextEncoder().encode(t+'.'+payload))).toString('hex');
 return {body:payload,headers:{'stripe-signature':'t='+t+',v1='+mac,'content-type':'application/json'}};
}

test('Stripe: checkout, signed webhooks, Pro on and off, replay protection', async()=>{
 const worker=await loadWorker(),env=makeEnv({...STRIPE_ENV,STRIPE_AUTOMATIC_TAX:'1'});
 const user=await signedInUser(env);
 let sub={id:'sub_1',status:'active',customer:'cus_1',metadata:{user_id:user.id},cancel_at_period_end:false,items:{data:[{current_period_end:Math.floor(Date.now()/1000)+30*86400}]}};
 const mock=mockFetch((url,method)=>{
  if(url==='https://api.stripe.com/v1/checkout/sessions'&&method==='POST')return jsonResponse({id:'cs_1',url:'https://checkout.stripe.com/c/pay/cs_1'});
  if(url==='https://api.stripe.com/v1/subscriptions/sub_1'&&method==='GET')return jsonResponse(sub);
  if(url==='https://api.stripe.com/v1/subscriptions/sub_1'&&method==='DELETE'){sub={...sub,status:'canceled'};return jsonResponse(sub);}
 });
 try{
  const page=await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}});
  assert.match(await page.text(),/Upgrade to Pro/);
  assert.match(page.headers.get('content-security-policy'),/form-action 'self' https:\/\/checkout\.stripe\.com/);

  const co=await request(worker,env,'POST',ACC+'/account/billing/checkout',{headers:formHeaders(user),form:{}});
  assert.equal(co.headers.get('location'),'https://checkout.stripe.com/c/pay/cs_1');
  const sent=new URLSearchParams(mock.calls.at(-1).body);
  assert.equal(sent.get('client_reference_id'),user.id);
  assert.equal(sent.get('subscription_data[metadata][user_id]'),user.id);
  assert.equal(sent.get('line_items[0][price]'),'price_pro');
  assert.equal(sent.get('automatic_tax[enabled]'),'true');
  assert.equal(sent.get('customer_email'),user.email);

  const bad=await signedEvent({id:'evt_x',type:'customer.subscription.updated',data:{object:{id:'sub_1'}}},'wrong');
  assert.equal((await request(worker,env,'POST',PUB+'/api/stripe/webhook',bad)).status,400);
  const stale=await signedEvent({id:'evt_x',type:'customer.subscription.updated',data:{object:{id:'sub_1'}}},'whsec_test',Math.floor(Date.now()/1000)-3600);
  assert.equal((await request(worker,env,'POST',PUB+'/api/stripe/webhook',stale)).status,400,'old signatures are refused');

  const done=await signedEvent({id:'evt_1',type:'checkout.session.completed',data:{object:{mode:'subscription',subscription:'sub_1',client_reference_id:user.id}}});
  assert.equal((await request(worker,env,'POST',PUB+'/api/stripe/webhook',done)).status,200);
  const replay=await request(worker,env,'POST',PUB+'/api/stripe/webhook',done);
  assert.equal((await replay.json()).duplicate,true);
  let row=env.ACCOUNTS.raw.prepare("SELECT status,provider_customer_id,current_period_end FROM subscriptions").get();
  assert.equal(row.status,'active');
  assert.equal(row.provider_customer_id,'cus_1');
  assert.ok(row.current_period_end);
  assert.match(await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text(),/Yarr Media Pro/);

  sub={...sub,status:'canceled'};
  const ended=await signedEvent({id:'evt_2',type:'customer.subscription.deleted',data:{object:{id:'sub_1'}}});
  await request(worker,env,'POST',PUB+'/api/stripe/webhook',ended);
  row=env.ACCOUNTS.raw.prepare("SELECT COUNT(*) n, MAX(status) s FROM subscriptions").get();
  assert.equal(row.n,1,'one row per Stripe subscription');
  assert.equal(row.s,'canceled');
  assert.match(await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text(),/Upgrade to Pro/);
 }finally{mock.restore();}
});

test('Stripe: a failed webhook is forgotten so Stripe can retry it', async()=>{
 const worker=await loadWorker(),env=makeEnv(STRIPE_ENV);
 await signedInUser(env);
 const mock=mockFetch(()=>jsonResponse({error:{type:'api_error'}},500));
 try{
  const ev=await signedEvent({id:'evt_9',type:'customer.subscription.updated',data:{object:{id:'sub_9'}}});
  assert.equal((await request(worker,env,'POST',PUB+'/api/stripe/webhook',ev)).status,500);
  assert.equal(env.ACCOUNTS.raw.prepare("SELECT COUNT(*) n FROM billing_events").get().n,0);
 }finally{mock.restore();}
});

test('billing stays off without Stripe keys', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const user=await signedInUser(env);
 assert.match(await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text(),/not on sale yet/);
 const co=await request(worker,env,'POST',ACC+'/account/billing/checkout',{headers:formHeaders(user),form:{}});
 assert.equal(co.headers.get('location'),'/account?billing=unavailable');
 assert.equal((await request(worker,env,'POST',PUB+'/api/stripe/webhook',{body:'{}'})).status,503);
});

test('account deletion cancels billing first, then removes everything', async()=>{
 const worker=await loadWorker(),env=makeEnv(STRIPE_ENV);
 const user=await signedInUser(env);
 pairedServer(env,user.id);
 const db=env.ACCOUNTS.raw;
 db.prepare("INSERT INTO subscriptions(id,user_id,status,provider,provider_subscription_id,provider_customer_id) VALUES('p1',?,'active','stripe','sub_1','cus_1')").run(user.id);
 db.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES('d1',?,'TV','google_tv','h',datetime('now','+1 day'))").run(user.id);
 const unconfirmed=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'delete'}});
 assert.equal(unconfirmed.headers.get('location'),'/account?delete=confirm');

 let mock=mockFetch(()=>jsonResponse({error:{type:'api_error'}},500));
 try{
  const failed=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'DELETE'}});
  assert.equal(failed.headers.get('location'),'/account?delete=billing');
  assert.equal(db.prepare("SELECT COUNT(*) n FROM users").get().n,1,'not deleted while still billing');
 }finally{mock.restore();}

 mock=mockFetch((url,method)=>method==='DELETE'&&url.endsWith('/subscriptions/sub_1')?jsonResponse({id:'sub_1',status:'canceled'}):null);
 try{
  const ok=await request(worker,env,'POST',ACC+'/account/delete',{headers:formHeaders(user),form:{confirm:'DELETE'}});
  assert.equal(ok.headers.get('location'),PUB+'/?account=deleted');
  assert.match(ok.headers.get('set-cookie'),/Max-Age=0/);
 }finally{mock.restore();}
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
