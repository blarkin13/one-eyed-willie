// Integration acceptance for Yarr one-time Pro, using the real account Worker and in-memory D1.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,signedInUser,pairedServer,request,newPassKey,digest,mockFetch,jsonResponse} from './harness.mjs';

const ACC='https://accounts.yarr.media';
const PUB='https://yarr.media';
const PRO_PRICE='price_test_yarr_pro_29';

test('test-only account dashboard shows one-time Checkout, never the subscription plan',async()=>{
 const worker=await loadWorker();
 const env=makeEnv({YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:PRO_PRICE});
 const user=await signedInUser(env);
 const page=await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text();
 assert.match(page,/\$29 one-time purchase/);
 assert.match(page,/action="\/api\/stripe\/checkout"/);
 assert.doesNotMatch(page,/action="\/account\/billing\/checkout"/);
 const noCookie=await request(worker,env,'GET',ACC+'/api/stripe/entitlement');
 assert.equal(noCookie.status,401);
 const status=await (await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:user.cookie}})).json();
 assert.deepEqual(status,{pro:false,checkout_enabled:true});
});

test('logged-in one-time Checkout has origin checks, automatic tax and matching database user',async()=>{
 const worker=await loadWorker();
 const env=makeEnv({YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:PRO_PRICE});
 const user=await signedInUser(env);
 const anonymous=await request(worker,env,'POST',ACC+'/api/stripe/checkout',{headers:{origin:ACC},form:{product:'pro'}});
 assert.equal(anonymous.status,401);
 const malicious=await request(worker,env,'POST',ACC+'/api/stripe/checkout',{headers:{cookie:user.cookie,origin:'https://attacker.example'},form:{product:'pro'}});
 assert.equal(malicious.status,403);
 const fetching=mockFetch((url,method,body)=>{
  assert.equal(url,'https://api.stripe.com/v1/checkout/sessions');
  assert.equal(method,'POST');
  const p=new URLSearchParams(body);
  assert.equal(p.get('mode'),'payment');
  assert.equal(p.get('automatic_tax[enabled]'),'true');
  assert.equal(p.get('line_items[0][price]'),PRO_PRICE);
  assert.equal(p.get('client_reference_id'),user.id);
  assert.equal(p.get('billing_address_collection'),'required');
  return jsonResponse({id:'cs_test_one_time_integration',url:'https://checkout.stripe.com/c/pay/test'});
 });
 try {
  const res=await request(worker,env,'POST',ACC+'/api/stripe/checkout',{headers:{cookie:user.cookie,origin:ACC},form:{product:'pro'}});
  assert.equal(res.status,303);
  assert.equal(res.headers.get('location'),'https://checkout.stripe.com/c/pay/test');
  const row=env.ACCOUNTS.raw.prepare("SELECT user_id,price_id,status FROM stripe_checkout_sessions WHERE id='cs_test_one_time_integration'").get();
  assert.deepEqual({...row},{user_id:user.id,price_id:PRO_PRICE,status:'pending'});
  assert.equal(fetching.calls.length,1);
 }finally{fetching.restore();}
});

test('one-time Pro is visible to account, TV and remote access; revocation removes access',async()=>{
 const worker=await loadWorker();
 const key=await newPassKey('stripe-one-time');
 const env=makeEnv({YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:PRO_PRICE,PASS_SIGNING_KEY:JSON.stringify(key)});
 const user=await signedInUser(env),other=await signedInUser(env,{id:'other-one-time',email:'other@example.invalid'});
 const server=pairedServer(env,user.id,{publicUrl:'https://home.example.net'});
 const token='ydv_'+'T'.repeat(48);
 env.ACCOUNTS.raw.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES('device-qa',?,'QA TV','google_tv',?,datetime('now','+1 day'))").run(user.id,await digest(token));
 const pass=who=>request(worker,env,'POST',ACC+'/api/passes',{headers:{cookie:who.cookie,origin:ACC},json:{server_id:server.id}});
 assert.equal((await pass(user)).status,402);
 env.ACCOUNTS.raw.prepare("INSERT INTO stripe_checkout_sessions(id,user_id,price_id,status) VALUES('cs_test_entitled',?,?,'paid')").run(user.id,PRO_PRICE);
 env.ACCOUNTS.raw.prepare("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) VALUES(?,'cs_test_entitled','active')").run(user.id);
 const owned=await (await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:user.cookie}})).json();
 const otherStatus=await (await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:other.cookie}})).json();
 assert.equal(owned.pro,true);
 assert.equal(otherStatus.pro,false);
 const page=await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text();
 assert.match(page,/One-time Pro license active; no recurring payments/);
 assert.doesNotMatch(page,/Test Pro checkout/);
 const device=await (await request(worker,env,'GET',PUB+'/api/device/me',{headers:{authorization:'Bearer '+token}})).json();
 assert.equal(device.pro.active,true);
 assert.equal((await pass(user)).status,200);
 assert.equal((await pass(other)).status,404);
 env.ACCOUNTS.raw.prepare("UPDATE one_time_pro_entitlements SET status='revoked' WHERE user_id=?").run(user.id);
 const revoked=await (await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:user.cookie}})).json();
 const revokedDevice=await (await request(worker,env,'GET',PUB+'/api/device/me',{headers:{authorization:'Bearer '+token}})).json();
 assert.equal(revoked.pro,false);
 assert.equal(revokedDevice.pro.active,false);
 assert.equal((await pass(user)).status,402);
});

test('one-time Checkout stays disabled without test flag and does not read unmigrated table',async()=>{
 const worker=await loadWorker();
 const env=makeEnv({STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:PRO_PRICE});
 const user=await signedInUser(env);
 const page=await (await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}})).text();
 assert.doesNotMatch(page,/Test Pro checkout/);
 const status=await (await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:user.cookie}})).json();
 assert.deepEqual(status,{pro:false,checkout_enabled:false});
 const post=await request(worker,env,'POST',ACC+'/api/stripe/checkout',{headers:{cookie:user.cookie,origin:ACC},form:{product:'pro'}});
 assert.equal(post.status,503);
});

test('existing active Pro account retains access when one-time checkout remains disabled',async()=>{
 const worker=await loadWorker();
 const env=makeEnv();
 const user=await signedInUser(env);
 env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider,plan) VALUES('manual-pro-test',?,'active','manual','pro')").run(user.id);
 const res=await request(worker,env,'GET',ACC+'/api/stripe/entitlement',{headers:{cookie:user.cookie}});
 assert.equal(res.status,200);
 assert.deepEqual(await res.json(),{pro:true,checkout_enabled:false});
});
