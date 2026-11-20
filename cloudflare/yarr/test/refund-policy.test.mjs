import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,signedInUser,request,mockFetch,jsonResponse} from './harness.mjs';

const PUB='https://yarr.media',ACC='https://accounts.yarr.media';

test('public refund policy is crawlable, linked, and consistent with the 14-day one-time offer',async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const res=await request(worker,env,'GET',PUB+'/refunds');
 assert.equal(res.status,200);
 const page=await res.text();
 assert.match(page,/<title>Refund Policy \| Yarr Media<\/title>/);
 assert.match(page,/14 calendar days/);
 assert.match(page,/refunds@yarr\.media/);
 assert.match(page,/href="mailto:refunds@yarr\.media\?subject=/);
 assert.match(page,/original payment method/);
 assert.match(page,/associated Pro entitlement/);
 assert.match(page,/<link rel="canonical" href="https:\/\/yarr\.media\/refunds">/);
 assert.match(page,/application\/ld\+json/);
 assert.doesNotMatch(page,/noindex,nofollow/);
 const map=await (await request(worker,env,'GET',PUB+'/sitemap.xml')).text();
 assert.match(map,/<loc>https:\/\/yarr\.media\/refunds<\/loc>/);
 for(const route of ['/','/terms','/features','/how2s']){
  const html=await (await request(worker,env,'GET',PUB+route)).text();
  assert.match(html,/href="https:\/\/yarr\.media\/refunds"/,route+' should link refunds');
 }
 const terms=await (await request(worker,env,'GET',PUB+'/terms')).text();
 assert.match(terms,/Our 14-day Refund Policy/);
 assert.doesNotMatch(terms,/recurring subscription billed through Stripe/);
});

test('a signed-in buyer sees the refund policy before checkout',async()=>{
 const worker=await loadWorker();
 const env=makeEnv({YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:'price_test_refund'});
 const user=await signedInUser(env);
 const res=await request(worker,env,'GET',ACC+'/',{headers:{cookie:user.cookie}});
 const html=await res.text();
 assert.match(html,/Full refund requests accepted within 14 days/);
 assert.match(html,/href="https:\/\/yarr\.media\/refunds"/);
 assert.match(html,/action="\/api\/stripe\/checkout"/);
});

test('Stripe-hosted Checkout includes a visible refund window and contact details',async()=>{
 const worker=await loadWorker();
 const env=makeEnv({YARR_STRIPE_TEST_ENABLED:'1',STRIPE_SECRET_KEY:'sk_test_local',STRIPE_PRO_PRICE_ID:'price_test_refund'});
 const user=await signedInUser(env);
 const calls=mockFetch((url,method,body)=>{
  assert.equal(url,'https://api.stripe.com/v1/checkout/sessions');
  assert.equal(method,'POST');
  const p=new URLSearchParams(body);
  assert.equal(p.get('mode'),'payment');
  assert.equal(p.get('automatic_tax[enabled]'),'true');
  const policy=p.get('custom_text[submit][message]');
  assert.match(policy,/14 days/);
  assert.match(policy,/refunds@yarr\.media/);
  assert.match(policy,/https:\/\/yarr\.media\/refunds/);
  assert.match(policy,/refund revokes Pro access/);
  return jsonResponse({id:'cs_test_refund_policy',url:'https://checkout.stripe.com/c/pay/refund-test'});
 });
 try{
  const res=await request(worker,env,'POST',ACC+'/api/stripe/checkout',{headers:{cookie:user.cookie,origin:ACC},form:{product:'pro'}});
  assert.equal(res.status,303);
  assert.equal(calls.calls.length,1);
 }finally{calls.restore();}
});