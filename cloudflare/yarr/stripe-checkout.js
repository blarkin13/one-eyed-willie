// Yarr Media — feature-gated, one-time Stripe Checkout and automatic tax.
// Production checkout is controlled by YARR_LIVE_CHECKOUT_ENABLED; policy terms are disclosed at payment.
const allowedHost = new Set(['accounts.yarr.media']);
const checkoutOrigin = 'https://accounts.yarr.media';
const stripeHeaders = {'content-type':'application/x-www-form-urlencoded'};
const reply = (body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}});
const stripeMode = env => env.YARR_STRIPE_MODE==='live'?'live':env.YARR_STRIPE_TEST_ENABLED==='1'?'test':null;
const expectedLive = env => stripeMode(env)==='live';
// Both standard and restricted Stripe live secret keys can authenticate Checkout.
const validLiveSecretKey = value => /^(?:sk|rk)_live_/.test(value||'');
const stripeReady = env => {
 const mode=stripeMode(env);
 if(!mode || !env.ACCOUNTS || !/^price_/.test(env.STRIPE_PRO_PRICE_ID||''))return false;
 return mode==='live'
  ? env.YARR_ONE_TIME_PRO_ENABLED==='1' && validLiveSecretKey(env.STRIPE_SECRET_KEY) && /^whsec_/.test(env.STRIPE_WEBHOOK_SECRET||'')
  : /^sk_test_/.test(env.STRIPE_SECRET_KEY||'');
};
const webhookReady = env => {
 if(!env.ACCOUNTS || !/^whsec_/.test(env.STRIPE_WEBHOOK_SECRET||''))return false;
 return expectedLive(env)
  ? env.YARR_ONE_TIME_PRO_ENABLED==='1' && validLiveSecretKey(env.STRIPE_SECRET_KEY)
  : stripeMode(env)==='test';
};
export const proCheckoutAvailable = env => stripeReady(env) && (
 expectedLive(env) ? env.YARR_LIVE_CHECKOUT_ENABLED==='1' : env.YARR_STRIPE_TEST_ENABLED==='1'
);
const configured = proCheckoutAvailable;
const validForm = req => {
  const url=new URL(req.url);
  return allowedHost.has(url.hostname) && req.headers.get('origin')===url.origin &&
    req.headers.get('sec-fetch-site')!=='cross-site' &&
    (req.headers.get('content-type')||'').startsWith('application/x-www-form-urlencoded');
};
async function stripePost(env,path,params){
  const response=await fetch('https://api.stripe.com/v1/'+path,{
    method:'POST',
    headers:{authorization:'Bearer '+env.STRIPE_SECRET_KEY,...stripeHeaders},
    body:params
  });
  const result=await response.json();
  if(!response.ok)throw new Error('Stripe '+response.status+': '+String(result.error?.type||'checkout_failed'));
  return result;
}
export async function createProCheckout(req,env,user){
  if(req.method!=='POST')return reply({error:'method_not_allowed'},405);
  if(!user)return reply({error:'sign_in_required'},401);
  if(!configured(env))return reply({error:'checkout_not_enabled'},503);
  if(!validForm(req))return reply({error:'invalid_request_origin'},403);
  const fields=new URLSearchParams(await req.text());
  if(fields.toString().length>500||fields.get('product')!=='pro')return reply({error:'invalid_product'},400);
  const already=await env.ACCOUNTS.prepare("SELECT 1 FROM one_time_pro_entitlements WHERE user_id=? AND status='active' LIMIT 1").bind(user.id).first();
  if(already)return reply({error:'already_pro'},409);
  const params=new URLSearchParams({
    mode:'payment',
    'line_items[0][price]':env.STRIPE_PRO_PRICE_ID,
    'line_items[0][quantity]':'1',
    'automatic_tax[enabled]':'true',
    billing_address_collection:'required',
    'tax_id_collection[enabled]':'true',
    customer_creation:'always',
    client_reference_id:user.id,
    'metadata[yarr_user_id]':user.id,
    'custom_text[submit][message]':'Yarr Media Pro is a $29 one-time purchase, plus applicable tax. Request a full refund for any reason within 14 days of purchase at refunds@yarr.media. Refund Policy: https://yarr.media/refunds. A refund revokes Pro access, but local Free use continues.',
    success_url:checkoutOrigin+'/?checkout=success&session_id={CHECKOUT_SESSION_ID}',
    cancel_url:checkoutOrigin+'/?checkout=cancel'
  });
  if(user.email)params.set('customer_email',user.email);
  let session;
  try{session=await stripePost(env,'checkout/sessions',params);}
  catch(_){return reply({error:'checkout_unavailable'},502);}
  if(!(expectedLive(env)?/^cs_live_/:/^cs_test_/).test(session.id||'')||!/^https:\/\//.test(session.url||''))return reply({error:'invalid_session'},502);
  await env.ACCOUNTS.prepare(
    'INSERT INTO stripe_checkout_sessions(id,user_id,price_id,status) VALUES(?,?,?,?)'
  ).bind(session.id,user.id,env.STRIPE_PRO_PRICE_ID,'pending').run();
  return new Response(null,{status:303,headers:{location:session.url,'cache-control':'no-store'}});
}
async function stripeGet(env,path){
  const response=await fetch('https://api.stripe.com/v1/'+path,{headers:{authorization:'Bearer '+env.STRIPE_SECRET_KEY}});
  if(!response.ok)throw new Error('Stripe verification unavailable');
  return response.json();
}
async function verifyPaidSession(env,sessionId,existing) {
  // Never fulfill from a webhook payload alone; retrieve authoritative state and line items.
  const session=await stripeGet(env,'checkout/sessions/'+encodeURIComponent(sessionId));
  if(session.livemode!==expectedLive(env) || session.mode!=='payment' || session.payment_status!=='paid' ||
     session.status!=='complete' || session.client_reference_id!==existing.user_id ||
     session.currency!=='usd' || !Number.isSafeInteger(session.amount_total) ||
     session.amount_total<2900 || !/^pi_/.test(session.payment_intent||''))return null;
  const items=await stripeGet(env,'checkout/sessions/'+encodeURIComponent(sessionId)+'/line_items?limit=10');
  if(items.has_more || items.data?.length!==1 ||
     items.data[0]?.price?.id!==existing.price_id ||
     items.data[0]?.quantity!==1 ||
     existing.price_id!==env.STRIPE_PRO_PRICE_ID ||
     items.data[0]?.price?.unit_amount!==2900 ||
     items.data[0]?.price?.tax_behavior!=='exclusive')return null;
  // A late delivery of checkout.session.completed must not reactivate a refunded/disputed purchase.
  const intent=await stripeGet(env,'payment_intents/'+encodeURIComponent(session.payment_intent));
  if(intent.livemode!==expectedLive(env) || intent.status!=='succeeded' ||
     intent.id!==session.payment_intent || !/^ch_/.test(intent.latest_charge||''))return null;
  const charge=await stripeGet(env,'charges/'+encodeURIComponent(intent.latest_charge));
  if(charge.livemode!==expectedLive(env) || charge.payment_intent!==session.payment_intent || charge.refunded ||
     Number(charge.amount_refunded||0)>0 || charge.disputed)return null;
  return session;
}
async function locateCheckoutForCharge(env,paymentIntent) {
  let paid=await env.ACCOUNTS.prepare('SELECT id,user_id,status FROM stripe_checkout_sessions WHERE payment_intent_id=?').bind(paymentIntent).first();
  if(paid)return paid;
  // Refund and dispute webhooks can arrive before checkout completion. Map PI to Stripe
  // Checkout session and the *pre-existing* pending row, never trust the event user metadata.
  const result=await stripeGet(env,'checkout/sessions?payment_intent='+encodeURIComponent(paymentIntent)+'&limit=2');
  if(result.has_more || result.data?.length!==1 || result.data[0]?.livemode!==expectedLive(env))return null;
  const session=result.data[0];
  if(!(expectedLive(env)?/^cs_live_/:/^cs_test_/).test(session.id||'') || session.mode!=='payment')return null;
  paid=await env.ACCOUNTS.prepare('SELECT id,user_id,status FROM stripe_checkout_sessions WHERE id=?').bind(session.id).first();
  if(!paid || paid.user_id!==session.client_reference_id)return null;
  return paid;
}
const fromHex = hex => {
  if(!/^[a-f0-9]{64}$/i.test(hex))return null;
  return new Uint8Array(hex.match(/.{2}/g).map(pair=>parseInt(pair,16)));
};
const equal = (a,b) => {
  if(!a||!b||a.length!==b.length)return false;
  let n=0;for(let i=0;i<a.length;i++)n|=a[i]^b[i];return n===0;
};
export async function verifyStripeSignature(payload,header,secret,now=Date.now()){
  if(!header||!secret||!secret.startsWith('whsec_'))return false;
  const parts=header.split(',').map(x=>x.trim().split('='));
  const ts=parts.find(x=>x[0]==='t')?.[1];
  const sigs=parts.filter(x=>x[0]==='v1').map(x=>fromHex(x[1]));
  if(!/^\d{10}$/.test(ts||'')||Math.abs(Math.floor(now/1000)-Number(ts))>300)return false;
  const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const expected=new Uint8Array(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(ts+'.'+payload)));
  return sigs.some(sig=>equal(sig,expected));
}
export async function proStripeWebhook(req,env){
  if(req.method!=='POST')return reply({error:'method_not_allowed'},405);
  if(!webhookReady(env))return reply({error:'unavailable'},503);
  const payload=await req.text();
  if(payload.length>200000)return reply({error:'payload_too_large'},413);
  if(!await verifyStripeSignature(payload,req.headers.get('stripe-signature'),env.STRIPE_WEBHOOK_SECRET))return reply({error:'invalid_signature'},400);
  let event;try{event=JSON.parse(payload);}catch(_){return reply({error:'invalid_json'},400);}
  if(event.livemode!==expectedLive(env)||!/^evt_/.test(event.id||''))return reply({error:'invalid_event'},400);
  // Revoke access when Stripe reports refunds or disputed charges.
  // Refunded/contested licenses require owner review before reinstatement.
  if(['charge.refunded','charge.dispute.created'].includes(event.type)){
    const notice=event.data?.object;
    const dispute=event.type==='charge.dispute.created';
    // Stripe charge.refunded contains a Charge; charge.dispute.created contains a Dispute.
    const chargeId=dispute?notice?.charge:notice?.id;
    if(!/^ch_/.test(chargeId||'') ||
       (dispute && !/^(du|dp)_/.test(notice?.id||'')))return reply({received:true,ignored:true});
    let charge,paid;
    try{
      charge=await stripeGet(env,'charges/'+encodeURIComponent(chargeId));
      if(charge.livemode!==expectedLive(env) || charge.id!==chargeId ||
         !/^pi_/.test(charge.payment_intent||''))return reply({error:'invalid_charge'},400);
      if(dispute?!charge.disputed:!(charge.refunded || Number(charge.amount_refunded||0)>0))
        return reply({error:'refund_or_dispute_not_verified'},400);
      paid=await locateCheckoutForCharge(env,charge.payment_intent);
    }catch(_){return reply({error:'stripe_verification_unavailable'},503);}
    const paymentIntent=charge.payment_intent;
    const status=event.type==='charge.dispute.created'?'disputed':'refunded';
    if(!paid){
      // An account may have been deleted after paying: retain non-identifying
      // tax and payment records without recreating a user or entitlement.
      const archived=await env.ACCOUNTS.prepare('SELECT checkout_session_id FROM stripe_purchase_archive WHERE payment_intent_id=?').bind(paymentIntent).first();
      if(!archived)return reply({received:true,ignored:true});
      await env.ACCOUNTS.batch([
        env.ACCOUNTS.prepare('INSERT OR IGNORE INTO stripe_webhook_events(event_id,event_type,session_id) VALUES(?,?,?)').bind(event.id,event.type,archived.checkout_session_id),
        env.ACCOUNTS.prepare("UPDATE stripe_purchase_archive SET status=CASE WHEN status='disputed' THEN 'disputed' ELSE ? END,updated_at=CURRENT_TIMESTAMP WHERE checkout_session_id=?").bind(status,archived.checkout_session_id)
      ]);
      return reply({received:true,archived:true});
    }
    await env.ACCOUNTS.batch([
      env.ACCOUNTS.prepare('INSERT OR IGNORE INTO stripe_webhook_events(event_id,event_type,session_id) VALUES(?,?,?)').bind(event.id,event.type,paid.id),
      env.ACCOUNTS.prepare("UPDATE stripe_checkout_sessions SET status=CASE WHEN status='disputed' THEN 'disputed' ELSE ? END,payment_intent_id=COALESCE(payment_intent_id,?),updated_at=CURRENT_TIMESTAMP WHERE id=?").bind(status,paymentIntent,paid.id),
      env.ACCOUNTS.prepare("UPDATE one_time_pro_entitlements SET status='revoked' WHERE checkout_session_id=?").bind(paid.id)
    ]);
    return reply({received:true});
  }
  if(!['checkout.session.completed','checkout.session.async_payment_succeeded'].includes(event.type))return reply({received:true,ignored:true});
  const notice=event.data?.object;
  if(!notice||notice.mode!=='payment'||notice.payment_status!=='paid'||!(expectedLive(env)?/^cs_live_/:/^cs_test_/).test(notice.id||''))return reply({received:true,ignored:true});
  const existing=await env.ACCOUNTS.prepare('SELECT id,user_id,price_id,status FROM stripe_checkout_sessions WHERE id=?').bind(notice.id).first();
  if(!existing||notice.client_reference_id!==existing.user_id)return reply({error:'unknown_or_mismatched_checkout'},400);
  if(existing.status==='refunded'||existing.status==='disputed')return reply({received:true,ignored:true});
  let session;
  try{session=await verifyPaidSession(env,notice.id,existing);}
  catch(_){return reply({error:'stripe_verification_unavailable'},503);}
  if(!session)return reply({error:'payment_verification_failed'},400);
  await env.ACCOUNTS.batch([
    env.ACCOUNTS.prepare('INSERT OR IGNORE INTO stripe_webhook_events(event_id,event_type,session_id) VALUES(?,?,?)').bind(event.id,event.type,session.id),
    env.ACCOUNTS.prepare("UPDATE stripe_checkout_sessions SET status='paid',amount_total=?,currency=?,payment_intent_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('pending','paid')").bind(session.amount_total,session.currency,session.payment_intent,session.id),
    env.ACCOUNTS.prepare("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) SELECT ?,?,'active' WHERE EXISTS(SELECT 1 FROM stripe_checkout_sessions WHERE id=? AND status='paid') ON CONFLICT(checkout_session_id) DO NOTHING").bind(existing.user_id,session.id,session.id)
  ]);
  return reply({received:true});
}
