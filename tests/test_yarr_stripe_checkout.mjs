// Run with: node --test tests/test_yarr_stripe_checkout.mjs (Node 18+).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto,createHmac} from 'node:crypto';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
const source=readFileSync(new URL('../cloudflare/yarr/stripe-checkout.js',import.meta.url),'utf8');
const {verifyStripeSignature,createProCheckout,proStripeWebhook}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

test('valid Stripe HMAC signature is accepted',async()=>{
  const payload=JSON.stringify({id:'evt_1',livemode:false});
  const ts=Math.floor(Date.now()/1000);
  const secret='whsec_test_key_for_unit_testing';
  const signature=createHmac('sha256',secret).update(ts+'.'+payload).digest('hex');
  assert.equal(await verifyStripeSignature(payload,'t='+ts+',v1='+signature,secret),true);
  assert.equal(await verifyStripeSignature(payload+' ', 't='+ts+',v1='+signature,secret),false);
  assert.equal(await verifyStripeSignature(payload,'t='+(ts-301)+',v1='+signature,secret),false);
  assert.equal(await verifyStripeSignature(payload,'t='+ts+',v1=bad',secret),false);
});
test('checkout disabled without sandbox flag or test key',async()=>{
  const req=new Request('https://accounts.yarr.media/api/stripe/checkout',{method:'POST',headers:{origin:'https://accounts.yarr.media','content-type':'application/x-www-form-urlencoded'},body:'product=pro'});
  const res=await createProCheckout(req,{}, {id:'u1'});
  assert.equal(res.status,503);
  assert.equal((await res.json()).error,'checkout_not_enabled');
});
test('webhook rejects unauthorized posts by default',async()=>{
  const req=new Request('https://accounts.yarr.media/api/stripe/webhook',{method:'POST',body:'{}'});
  const res=await proStripeWebhook(req,{});
  assert.equal(res.status,503);
});

function signEvent(event,secret='whsec_unit_test') {
  const body=JSON.stringify(event);
  const ts=Math.floor(Date.now()/1000);
  const sig=createHmac('sha256',secret).update(ts+'.'+body).digest('hex');
  return new Request('https://accounts.yarr.media/api/stripe/webhook',{method:'POST',
    headers:{'stripe-signature':'t='+ts+',v1='+sig,'content-type':'application/json'},body});
}
function stubD1(find) {
  const statements=[];
  return {statements, prepare(sql) {return {sql,bind(...values){return {
    sql,values,first:async()=>find(sql,values),
    run:async()=>({success:true})
  }}}},async batch(batch){statements.push(...batch);return batch.map(()=>({success:true}))}};
}
const paidNotice=(id='cs_test_late')=>({
  id:'evt_paid_1',livemode:false,type:'checkout.session.completed',
  data:{object:{id,mode:'payment',payment_status:'paid',client_reference_id:'u1'}}
});
test('late paid checkout webhook never reactivates a refunded purchase',async()=>{
  const db=stubD1(()=>({id:'cs_test_late',user_id:'u1',status:'refunded',price_id:'price_correct'}));
  const res=await proStripeWebhook(signEvent(paidNotice()),{
    YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',
    STRIPE_PRO_PRICE_ID:'price_correct',ACCOUNTS:db
  });
  assert.equal(res.status,200);
  assert.equal((await res.json()).ignored,true);
  assert.equal(db.statements.length,0);
});
test('a refund arriving before checkout completion maps the pending checkout and revokes',async()=>{
  const originalFetch=globalThis.fetch;
  const lookedUp=[];
  globalThis.fetch=async url=>{
    lookedUp.push(String(url));
    if(String(url).includes('/charges/ch_refund'))return Response.json({id:'ch_refund',livemode:false,payment_intent:'pi_refund',refunded:true,amount_refunded:3139,disputed:false});
    if(String(url).includes('/checkout/sessions?payment_intent='))return Response.json({has_more:false,data:[{id:'cs_test_refund_first',livemode:false,mode:'payment',client_reference_id:'u1'}]});
    throw Error('Unexpected Stripe query '+url);
  };
  try {
    const db=stubD1(sql=>sql.includes('WHERE payment_intent_id=')?null:{id:'cs_test_refund_first',user_id:'u1',status:'pending'});
    const ev={id:'evt_refund_1',livemode:false,type:'charge.refunded',data:{object:{id:'ch_refund',payment_intent:'pi_refund'}}};
    const res=await proStripeWebhook(signEvent(ev),{
      YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:db
    });
    assert.equal(res.status,200);
    assert.equal(db.statements.length,3);
    assert.match(db.statements[1].sql,/payment_intent_id=COALESCE/);
    assert.deepEqual(db.statements[1].values,['refunded','pi_refund','cs_test_refund_first']);
    assert.match(db.statements[2].sql,/status='revoked'/);
    assert.equal(lookedUp.length,2);
  }finally {globalThis.fetch=originalFetch;}
});
test('dispute webhook retrieves its Charge via the dispute charge ID, not dispute ID',async()=>{
  const originalFetch=globalThis.fetch;
  const called=[];
  globalThis.fetch=async url=>{
    called.push(String(url));
    if(String(url).endsWith('/charges/ch_disputed'))return Response.json({id:'ch_disputed',livemode:false,payment_intent:'pi_disputed',disputed:true});
    throw Error('Unexpected Stripe query');
  };
  try{
    const db=stubD1(()=>({id:'cs_test_disputed',user_id:'u1',status:'paid'}));
    const ev={id:'evt_dispute_1',livemode:false,type:'charge.dispute.created',data:{object:{id:'du_1',charge:'ch_disputed'}}};
    const res=await proStripeWebhook(signEvent(ev),{
      YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:db
    });
    assert.equal(res.status,200);
    assert.equal(db.statements.length,3);
    assert.deepEqual(db.statements[1].values,['disputed','pi_disputed','cs_test_disputed']);
    assert.deepEqual(called,['https://api.stripe.com/v1/charges/ch_disputed']);
  }finally{globalThis.fetch=originalFetch;}
});
test('Stripe charge with a previous refund blocks delayed fulfillment',async()=>{
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async url=>{
    const p=String(url);
    if(p.endsWith('/checkout/sessions/cs_test_paid'))return Response.json({id:'cs_test_paid',livemode:false,status:'complete',mode:'payment',payment_status:'paid',client_reference_id:'u1',currency:'usd',amount_total:3139,payment_intent:'pi_paid'});
    if(p.includes('/checkout/sessions/cs_test_paid/line_items'))return Response.json({has_more:false,data:[{price:{id:'price_correct',unit_amount:2900,tax_behavior:'exclusive'},quantity:1}]});
    if(p.endsWith('/payment_intents/pi_paid'))return Response.json({id:'pi_paid',livemode:false,status:'succeeded',latest_charge:'ch_paid'});
    if(p.endsWith('/charges/ch_paid'))return Response.json({id:'ch_paid',payment_intent:'pi_paid',refunded:true,amount_refunded:3139,disputed:false});
    throw Error('Unexpected Stripe query: '+p);
  };
  try{
    const db=stubD1(()=>({id:'cs_test_paid',user_id:'u1',status:'pending',price_id:'price_correct'}));
    const res=await proStripeWebhook(signEvent(paidNotice('cs_test_paid')),{
      YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',
      STRIPE_PRO_PRICE_ID:'price_correct',STRIPE_SECRET_KEY:'sk_test_unit',ACCOUNTS:db
    });
    assert.equal(res.status,400);
    assert.equal((await res.json()).error,'payment_verification_failed');
    assert.equal(db.statements.length,0);
  }finally{globalThis.fetch=originalFetch;}
});

const entitlementSource=readFileSync(new URL('../cloudflare/yarr/entitlements.js',import.meta.url),'utf8');
const {oneTimeProEnabled,oneTimeProActive}=await import('data:text/javascript;base64,'+Buffer.from(entitlementSource).toString('base64'));
test('one-time Pro remains disabled until the feature flag is enabled',async()=>{
  let queried=false;
  const db={prepare(){queried=true;throw Error('should not query migration before flag is enabled')}};
  assert.equal(oneTimeProEnabled({ACCOUNTS:db}),false);
  assert.equal(await oneTimeProActive({ACCOUNTS:db},'u1'),false);
  assert.equal(queried,false);
});
test('active one-time Pro is visible to the same user but not others',async()=>{
  let observed;
  const db={prepare(sql){assert.match(sql,/status='active'/);return {bind(id){observed=id;return {first:async()=>id==='member_pro'?{'1':1}:null}}}}};
  const env={YARR_STRIPE_TEST_ENABLED:'1',ACCOUNTS:db};
  assert.equal(oneTimeProEnabled(env),true);
  assert.equal(await oneTimeProActive(env,'member_pro'),true);
  assert.equal(observed,'member_pro');
  assert.equal(await oneTimeProActive(env,'member_free'),false);
  assert.equal(await oneTimeProActive(env,''),false);
});
test('revoked one-time Pro cannot be granted by mere purchase history',async()=>{
  const env={YARR_ONE_TIME_PRO_ENABLED:'1',ACCOUNTS:{
    prepare(sql){return {bind(){return {first:async()=>null}}}}
  }};
  assert.equal(await oneTimeProActive(env,'member_refunded'),false);
});

test('refund after account deletion updates archived ledger without restoring the user',async()=>{
 const originalFetch=globalThis.fetch;
 globalThis.fetch=async url=>{
  const p=String(url);
  if(p.endsWith('/charges/ch_after_deletion'))return Response.json({id:'ch_after_deletion',livemode:false,payment_intent:'pi_after_deletion',refunded:true,amount_refunded:3139,disputed:false});
  if(p.includes('/checkout/sessions?payment_intent='))return Response.json({has_more:false,data:[{id:'cs_test_deleted',livemode:false,mode:'payment',client_reference_id:'deleted_user'}]});
  throw Error('Unexpected Stripe query');
 };
 try{
  const db=stubD1(sql=>sql.includes('stripe_purchase_archive')?{checkout_session_id:'cs_test_deleted'}:null);
  const event={id:'evt_refund_after_delete',livemode:false,type:'charge.refunded',data:{object:{id:'ch_after_deletion'}}};
  const response=await proStripeWebhook(signEvent(event),{
   YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:db
  });
  assert.equal(response.status,200);
  assert.equal((await response.json()).archived,true);
  assert.equal(db.statements.length,2);
  assert.match(db.statements[1].sql,/UPDATE stripe_purchase_archive/);
  assert.deepEqual(db.statements[1].values,['refunded','cs_test_deleted']);
 }finally{globalThis.fetch=originalFetch;}
});

test('real Stripe du_ dispute can arrive before checkout completion and revokes Pro',async()=>{
  const originalFetch=globalThis.fetch;
  const queries=[];
  globalThis.fetch=async url=>{
    const p=String(url);
    queries.push(p);
    if(p.endsWith('/charges/ch_test_disputed'))return Response.json({id:'ch_test_disputed',livemode:false,payment_intent:'pi_test_disputed',disputed:true,refunded:false,amount_refunded:0});
    if(p.includes('/checkout/sessions?payment_intent='))return Response.json({has_more:false,data:[{id:'cs_test_dispute_pending',mode:'payment',livemode:false,client_reference_id:'qa_dispute'}]});
    throw Error('Unexpected URL '+p);
  };
  try{
    const db=stubD1(sql=>sql.includes('WHERE payment_intent_id=')?null:{id:'cs_test_dispute_pending',user_id:'qa_dispute',status:'pending'});
    const event={id:'evt_test_real_dispute',livemode:false,type:'charge.dispute.created',data:{object:{id:'du_test_disputed',object:'dispute',charge:'ch_test_disputed',payment_intent:'pi_test_disputed',status:'needs_response'}}};
    const res=await proStripeWebhook(signEvent(event),{YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:db});
    assert.equal(res.status,200);
    assert.equal((await res.json()).received,true);
    assert.equal(db.statements.length,3);
    assert.deepEqual(db.statements[1].values,['disputed','pi_test_disputed','cs_test_dispute_pending']);
    assert.match(db.statements[2].sql,/status='revoked'/);
    assert.equal(queries.length,2);
  }finally{globalThis.fetch=originalFetch;}
});

test('live checkout requires all production flags, a live API key and a webhook secret',async()=>{
 const req=()=>new Request('https://accounts.yarr.media/api/stripe/checkout',{method:'POST',headers:{origin:'https://accounts.yarr.media','content-type':'application/x-www-form-urlencoded'},body:'product=pro'});
 const db=stubD1(()=>null);
 const config={YARR_STRIPE_MODE:'live',YARR_ONE_TIME_PRO_ENABLED:'1',STRIPE_SECRET_KEY:'sk_live_unit_test',STRIPE_PRO_PRICE_ID:'price_live_unit_test',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:db};
 for(const changes of [{YARR_LIVE_CHECKOUT_ENABLED:'0'},{STRIPE_SECRET_KEY:'sk_test_wrong_key',YARR_LIVE_CHECKOUT_ENABLED:'1'},{STRIPE_WEBHOOK_SECRET:'',YARR_LIVE_CHECKOUT_ENABLED:'1'},{YARR_ONE_TIME_PRO_ENABLED:'0',YARR_LIVE_CHECKOUT_ENABLED:'1'}]){
  const res=await createProCheckout(req(),{...config,...changes},{id:'user-live'});
  assert.equal(res.status,503);
 }
 const fetchBefore=globalThis.fetch;
 globalThis.fetch=async (url,opt)=>{
  assert.equal(url,'https://api.stripe.com/v1/checkout/sessions');
  assert.equal(opt.headers.authorization,'Bearer sk_live_unit_test');
  const args=new URLSearchParams(opt.body);
  assert.equal(args.get('line_items[0][price]'),'price_live_unit_test');
  assert.equal(args.get('automatic_tax[enabled]'),'true');
  assert.equal(args.get('client_reference_id'),'user-live');
  return Response.json({id:'cs_live_unit_test',url:'https://checkout.stripe.com/test'});
 };
 try{
  const res=await createProCheckout(req(),{...config,YARR_LIVE_CHECKOUT_ENABLED:'1'},{id:'user-live',email:'test@example.invalid'});
  assert.equal(res.status,303);
  assert.equal(res.headers.get('location'),'https://checkout.stripe.com/test');
 }finally{globalThis.fetch=fetchBefore;}
});
test('live webhook refuses test events and test webhook refuses live events',async()=>{
 const live={YARR_STRIPE_MODE:'live',YARR_ONE_TIME_PRO_ENABLED:'1',STRIPE_SECRET_KEY:'sk_live_test',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:stubD1(()=>null)};
 const event={id:'evt_test_rejected',livemode:false,type:'customer.created',data:{object:{id:'cus_test'}}};
 const res=await proStripeWebhook(signEvent(event),live);
 assert.equal(res.status,400);
 assert.equal((await res.json()).error,'invalid_event');
 const allowed=await proStripeWebhook(signEvent({...event,livemode:true}),live);
 assert.equal(allowed.status,200);
 assert.equal((await allowed.json()).ignored,true);
 const testEnv={YARR_STRIPE_TEST_ENABLED:'1',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',ACCOUNTS:stubD1(()=>null)};
 const mismatch=await proStripeWebhook(signEvent({...event,livemode:true}),testEnv);
 assert.equal(mismatch.status,400);
});

test('live paid webhook verifies live Stripe session, line item, payment intent, charge and account',async()=>{
 const prior=globalThis.fetch;
 const seen=[];
 globalThis.fetch=async url=>{
  const p=String(url);seen.push(p);
  if(p.endsWith('/checkout/sessions/cs_live_unit'))return Response.json({id:'cs_live_unit',livemode:true,mode:'payment',status:'complete',payment_status:'paid',client_reference_id:'live_member',amount_total:3139,currency:'usd',payment_intent:'pi_live_unit'});
  if(p.includes('/checkout/sessions/cs_live_unit/line_items'))return Response.json({has_more:false,data:[{price:{id:'price_live_unit',unit_amount:2900,tax_behavior:'exclusive'},quantity:1}]});
  if(p.endsWith('/payment_intents/pi_live_unit'))return Response.json({id:'pi_live_unit',livemode:true,status:'succeeded',latest_charge:'ch_live_unit'});
  if(p.endsWith('/charges/ch_live_unit'))return Response.json({id:'ch_live_unit',livemode:true,payment_intent:'pi_live_unit',refunded:false,amount_refunded:0,disputed:false});
  throw Error('unexpected live Stripe API '+p);
 };
 try{
  const db=stubD1(()=>({id:'cs_live_unit',user_id:'live_member',price_id:'price_live_unit',status:'pending'}));
  const env={YARR_STRIPE_MODE:'live',YARR_ONE_TIME_PRO_ENABLED:'1',STRIPE_SECRET_KEY:'sk_live_unit',STRIPE_WEBHOOK_SECRET:'whsec_unit_test',STRIPE_PRO_PRICE_ID:'price_live_unit',ACCOUNTS:db};
  const event={id:'evt_live_unit',livemode:true,type:'checkout.session.completed',data:{object:{id:'cs_live_unit',mode:'payment',payment_status:'paid',client_reference_id:'live_member'}}};
  const response=await proStripeWebhook(signEvent(event),env);
  assert.equal(response.status,200);
  assert.equal((await response.json()).received,true);
  assert.equal(seen.length,4);
  assert.equal(db.statements.length,3);
  assert.deepEqual(db.statements[2].values,['live_member','cs_live_unit','cs_live_unit']);
 }finally{globalThis.fetch=prior;}
});
