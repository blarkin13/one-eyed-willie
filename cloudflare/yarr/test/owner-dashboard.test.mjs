import test from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,signedInUser,request} from './harness.mjs';
const root='https://yarr.media';
test('owner page and all mailbox resources require configured web owner',async()=>{
 const worker=await loadWorker(),env=makeEnv({YARR_OWNER_ACCOUNT_ID:'owner',SUPPORT_MAIL_INBOX_ENABLED:'true',MAIL_MESSAGES:{}});
 const owner=await signedInUser(env,{id:'owner'}),other=await signedInUser(env,{id:'other',email:'other@example.com'});
 const get=(url,who)=>request(worker,env,'GET',url,{headers:who?{cookie:who.cookie}:{}});
 for(const p of ['/owner/','/mail/','/mail/mail.js','/api/support-mail/threads']){
  assert.equal((await get(root+p,other)).status,404);
  assert.equal((await get('https://app.yarr.media'+p,owner)).status,404);
 }
 assert.equal((await get(root+'/owner/')).status,303);
 assert.equal((await get(root+'/api/support-mail/threads')).status,404);
 const dashboard=await get(root+'/owner/',owner);
 assert.equal(dashboard.status,200);assert.match(await dashboard.text(),/Registered accounts/);
 assert.equal(dashboard.headers.get('cache-control'),'no-store');
 assert.equal((await get(root+'/mail/',owner)).status,200);
 assert.deepEqual(await (await get(root+'/api/support-mail/threads',owner)).json(),{threads:[],send_enabled:false});
 env.SUPPORT_MAIL_INBOX_ENABLED='false';
 assert.equal((await get(root+'/api/support-mail/threads',owner)).status,404);
 delete env.YARR_OWNER_ACCOUNT_ID;
 assert.equal((await get(root+'/owner/',owner)).status,404);
});
test('mail mutations reject non-owner and foreign origins',async()=>{
 const worker=await loadWorker(),env=makeEnv({YARR_OWNER_ACCOUNT_ID:'owner',SUPPORT_MAIL_INBOX_ENABLED:'true',MAIL_MESSAGES:{}});
 const owner=await signedInUser(env,{id:'owner'});
 const p=root+'/api/support-mail/threads/11111111-2222-3333-4444-555555555555/status';
 const response=await request(worker,env,'PATCH',p,{headers:{cookie:owner.cookie,origin:'https://evil.example'},json:{status:'closed'}});
 assert.equal(response.status,403);
});

test('owner workspace links appear only for the configured site owner',async()=>{
 const worker=await loadWorker(),env=makeEnv({YARR_OWNER_ACCOUNT_ID:'owner'});
 const owner=await signedInUser(env,{id:'owner'}),other=await signedInUser(env,{id:'other',email:'other@example.com'});
 const url='https://accounts.yarr.media/';
 const get=async who=>(await request(worker,env,'GET',url,{headers:{cookie:who.cookie}})).text();
 assert.match(await get(owner),/https:\/\/yarr\.media\/owner\//);
 assert.doesNotMatch(await get(other),/https:\/\/yarr\.media\/owner\//);
 const privacy=await (await request(worker,env,'GET','https://yarr.media/privacy')).text();
 for(const alias of ['support','billing','privacy','legal'])assert.ok(privacy.includes('mailto:'+alias+'@yarr.media'));
 assert.match(privacy,/Customer correspondence/);
});
