// One-time Pro entitlement read used by the account UI, TV credentials and remote-pass issuance.
// Keep off until the database migration and billing acceptance checks are complete.
export function oneTimeProEnabled(env) {
 return env?.YARR_STRIPE_TEST_ENABLED==='1'||env?.YARR_ONE_TIME_PRO_ENABLED==='1';
}
export async function oneTimeProActive(env,userId) {
 if(!oneTimeProEnabled(env)||!env.ACCOUNTS||typeof userId!=='string'||!userId)return false;
 const result=await env.ACCOUNTS.prepare(
  "SELECT 1 FROM one_time_pro_entitlements WHERE user_id=? AND status='active' LIMIT 1"
 ).bind(userId).first();
 return !!result;
}
