// Barnacles: sharing a server with people who have their own Yarr account.
// node --test cloudflare/yarr/test/
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {loadWorker,makeEnv,signedInUser,pairedServer,request,newPassKey,digest} from './harness.mjs';

const ACC='https://accounts.yarr.media';
const PUB='https://yarr.media';
const APP='https://app.yarr.media';
const formHeaders=user=>({cookie:user.cookie,origin:ACC,'sec-fetch-site':'same-origin'});
const LIBS=[{id:1,name:'Movies',kind:'movies'},{id:2,name:'TV Shows',kind:'tv'},{id:3,name:'Private',kind:'movies'}];

async function claimsOf(pass,keys){
 const [h,c,s]=pass.split('.');
 const key=await webcrypto.subtle.importKey('jwk',{kty:'OKP',crv:'Ed25519',x:keys.keys[0].x},{name:'Ed25519'},false,['verify']);
 assert.ok(await webcrypto.subtle.verify({name:'Ed25519'},key,Buffer.from(s,'base64url'),new TextEncoder().encode(h+'.'+c)));
 return JSON.parse(Buffer.from(c,'base64url'));
}

async function setup({ownerPro=true}={}){
 const key=await newPassKey('k-share');
 const worker=await loadWorker(),env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(key)});
 const db=env.ACCOUNTS.raw;
 const owner=await signedInUser(env,{id:'owner-1',email:'owner@example.com'});
 const friend=await signedInUser(env,{id:'friend-1',email:'friend@gmail.com'});
 db.prepare("UPDATE users SET display_name='Friend' WHERE id='friend-1'").run();
 const server=pairedServer(env,owner.id);
 db.prepare("UPDATE servers SET public_ip='76.183.183.204',connection_secret_hash=? WHERE id=?").run(await digest('s'.repeat(48)),server.id);
 if(ownerPro)db.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1','owner-1','active','manual')").run();
 // The server reports its libraries with its heartbeat.
 const hb=await request(worker,env,'POST',ACC+'/api/connection/heartbeat',{headers:{authorization:'Bearer '+'s'.repeat(48),'cf-connecting-ip':'76.183.183.204'},json:{libraries:LIBS}});
 assert.equal(hb.status,200);
 const keys=await (await request(worker,env,'GET',PUB+'/api/passes/keys')).json();
 return {worker,env,db,owner,friend,server,keys};
}
const invite=(t,email,libs=['1','2'])=>request(t.worker,t.env,'POST',ACC+'/account/shares',{headers:formHeaders(t.owner),
 form:[['action','invite'],['server_id',t.server.id],['email',email],...libs.map(l=>['library',l])]});
const shareId=t=>t.db.prepare("SELECT id FROM server_shares").get()?.id;
const act=(t,user,action,id,extra=[])=>request(t.worker,t.env,'POST',ACC+'/account/shares',{headers:formHeaders(user),form:[['action',action],['id',id],...extra]});
async function signTvIn(t,user,type='google_tv'){
 const token='ydv_'+(user.id+type).replace(/[^a-z]/g,'').padEnd(43,'t');
 t.db.prepare("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash,token_expires_at) VALUES(?,?,'TV',?,?,datetime('now','+1 day'))").run('dev-'+user.id+'-'+type,user.id,type,await digest(token));
 return {authorization:'Bearer '+token};
}

test('the heartbeat stores a clean library list (names and kinds only)', async()=>{
 const t=await setup();
 assert.deepEqual(JSON.parse(t.db.prepare("SELECT libraries_json FROM servers").get().libraries_json),LIBS);
 await request(t.worker,t.env,'POST',ACC+'/api/connection/heartbeat',{headers:{authorization:'Bearer '+'s'.repeat(48)},
  json:{libraries:[{id:4,name:'Kids\u0000',kind:'movies<script>'},{id:-1,name:'bad'},{id:5,name:''}]}});
 assert.deepEqual(JSON.parse(t.db.prepare("SELECT libraries_json FROM servers").get().libraries_json),[{id:4,name:'Kids',kind:'moviesscript'}]);
});

test('invite, accept, and a barnacle pass that carries only the chosen libraries', async()=>{
 const t=await setup();
 const r=await invite(t,'Friend@Gmail.com');
 assert.equal(r.headers.get('location'),'/account?share=invited#barnacles');
 const row=t.db.prepare("SELECT invite_email,status,library_ids,barnacle_user_id FROM server_shares").get();
 assert.deepEqual({...row},{invite_email:'friend@gmail.com',status:'pending',library_ids:'[1,2]',barnacle_user_id:null});
 // Not accepted yet: no access.
 const tv=await signTvIn(t,t.friend);
 assert.equal((await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:tv,json:{server_id:t.server.id}})).status,404);
 const page=await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:t.friend.cookie}})).text();
 assert.match(page,/Shared with you/);
 assert.match(page,/invited you to watch their library/);
 assert.equal((await act(t,t.friend,'accept',shareId(t))).headers.get('location'),'/account?share=accepted#shared-with-you');
 const me=await (await request(t.worker,t.env,'GET',PUB+'/api/device/me',{headers:tv})).json();
 assert.deepEqual(me.servers.map(s=>[s.id,s.role,s.owner_name,s.remote_address]),[[t.server.id,'barnacle','Owner','https://76-183-183-204.sslip.io']]);
 assert.equal(me.pro.active,false,'the barnacle has no Pro of their own');
 const res=await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:tv,json:{server_id:t.server.id}});
 assert.equal(res.status,200);
 const claims=await claimsOf((await res.json()).pass,t.keys);
 assert.equal(claims.role,'barnacle');
 assert.equal(claims.sub,t.friend.id);
 assert.equal(claims.aud,t.server.identity);
 assert.deepEqual(claims.lib,[1,2]);
 assert.equal(claims.nm,'Friend');
 // Phones can watch too.
 const phone=await signTvIn(t,t.friend,'android');
 assert.equal((await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:phone,json:{server_id:t.server.id}})).status,200);
});

test('owner changes libraries, removes the barnacle; the owner Pro is what counts', async()=>{
 const t=await setup({ownerPro:false});
 await invite(t,'friend@gmail.com');
 await act(t,t.friend,'accept',shareId(t));
 const tv=await signTvIn(t,t.friend);
 const noPro=await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:tv,json:{server_id:t.server.id}});
 assert.equal(noPro.status,402);
 assert.equal((await noPro.json()).error,'owner_pro_required');
 t.db.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m1','owner-1','active','manual')").run();
 assert.equal((await act(t,t.owner,'update',shareId(t),[['library','3']])).headers.get('location'),'/account?share=updated#barnacles');
 const claims=await claimsOf((await (await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:tv,json:{server_id:t.server.id}})).json()).pass,t.keys);
 assert.deepEqual(claims.lib,[3]);
 // Unknown library ids are dropped; nothing left means no change.
 assert.equal((await act(t,t.owner,'update',shareId(t),[['library','99']])).headers.get('location'),'/account?share=no_libraries#barnacles');
 // The barnacle can't change their own libraries.
 await act(t,t.friend,'update',shareId(t),[['library','1']]);
 assert.equal(t.db.prepare("SELECT library_ids FROM server_shares").get().library_ids,'[3]');
 assert.equal((await act(t,t.owner,'remove',shareId(t))).headers.get('location'),'/account?share=removed#barnacles');
 assert.equal((await request(t.worker,t.env,'POST',PUB+'/api/passes',{headers:tv,json:{server_id:t.server.id}})).status,404);
});

test('invites are validated', async()=>{
 const t=await setup();
 const loc=async r=>new URL((await r).headers.get('location'),ACC).searchParams.get('share');
 assert.equal(await loc(invite(t,'not-an-email')),'bad_email');
 assert.equal(await loc(invite(t,'owner@example.com')),'self');
 assert.equal(await loc(invite(t,'friend@gmail.com',[])),'no_libraries');
 assert.equal(await loc(invite(t,'friend@gmail.com',['42'])),'no_libraries');
 assert.equal(await loc(invite(t,'friend@gmail.com')),'invited');
 assert.equal(await loc(invite(t,'FRIEND@gmail.com')),'exists');
 // Someone else's server, and a server that hasn't reported libraries.
 const other=await request(t.worker,t.env,'POST',ACC+'/account/shares',{headers:formHeaders(t.friend),form:[['action','invite'],['server_id',t.server.id],['email','x@y.com'],['library','1']]});
 assert.equal(new URL(other.headers.get('location'),ACC).searchParams.get('share'),'not_found');
 t.db.prepare("UPDATE servers SET libraries_json=NULL").run();
 assert.equal(await loc(invite(t,'new@example.com')),'update_server');
 // Without a same-site form, nothing happens.
 const forged=await request(t.worker,t.env,'POST',ACC+'/account/shares',{headers:{cookie:t.owner.cookie,origin:'https://evil.example'},form:[['action','invite']]});
 assert.equal(forged.status,403);
});

test('only the invited email can accept; decline and leave', async()=>{
 const t=await setup();
 const stranger=await signedInUser(t.env,{id:'stranger-1',email:'stranger@example.com'});
 await invite(t,'friend@gmail.com');
 const id=shareId(t);
 assert.equal(new URL((await act(t,stranger,'accept',id)).headers.get('location'),ACC).searchParams.get('share'),'not_found');
 assert.equal(t.db.prepare("SELECT status FROM server_shares").get().status,'pending');
 assert.doesNotMatch(await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:stranger.cookie}})).text(),/Shared with you/);
 assert.equal(new URL((await act(t,t.friend,'decline',id)).headers.get('location'),ACC).searchParams.get('share'),'declined');
 assert.equal(t.db.prepare("SELECT COUNT(*) n FROM server_shares").get().n,0);
 await invite(t,'friend@gmail.com');
 await act(t,t.friend,'accept',shareId(t));
 assert.equal(new URL((await act(t,t.friend,'leave',shareId(t))).headers.get('location'),ACC).searchParams.get('share'),'left');
 assert.equal(t.db.prepare("SELECT COUNT(*) n FROM server_shares").get().n,0);
});

test('app.yarr.media opens a shared server for a barnacle', async()=>{
 const t=await setup();
 await invite(t,'friend@gmail.com');
 await act(t,t.friend,'accept',shareId(t));
 const conn=await request(t.worker,t.env,'GET',APP+'/__yarr/connection',{headers:{cookie:t.friend.cookie}});
 assert.equal(conn.status,200);
 const body=await conn.json();
 assert.equal(body.server_origin,'https://76-183-183-204.sslip.io');
 assert.equal((await claimsOf(body.pass,t.keys)).role,'barnacle');
 const use=await request(t.worker,t.env,'GET',APP+'/__yarr/use?server='+t.server.id,{headers:{cookie:t.friend.cookie}});
 assert.equal(use.status,200);
 assert.match(use.headers.get('set-cookie'),/^__Host-yarr_app_server=11111111-2222-3333-4444-555555555555; Path=\/; Secure; HttpOnly/);
 const chosen=await request(t.worker,t.env,'GET',APP+'/__yarr/connection',{headers:{cookie:t.friend.cookie+'; __Host-yarr_app_server='+t.server.id}});
 assert.equal((await claimsOf((await chosen.json()).pass,t.keys)).role,'barnacle');
 // A stranger can't pick someone else's server.
 const stranger=await signedInUser(t.env,{id:'stranger-1',email:'stranger@example.com'});
 assert.equal((await request(t.worker,t.env,'GET',APP+'/__yarr/use?server='+t.server.id,{headers:{cookie:stranger.cookie}})).status,303);
 assert.equal((await request(t.worker,t.env,'GET',APP+'/__yarr/connection',{headers:{cookie:stranger.cookie+'; __Host-yarr_app_server='+t.server.id}})).status,404);
 // The owner still gets an owner pass.
 assert.equal((await claimsOf((await (await request(t.worker,t.env,'GET',APP+'/__yarr/connection',{headers:{cookie:t.owner.cookie}})).json()).pass,t.keys)).role,'owner');
});

test('the owner sees the Barnacles panel; deleting either account removes the share', async()=>{
 const t=await setup();
 await invite(t,'friend@gmail.com');
 let page=await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:t.owner.cookie}})).text();
 assert.match(page,/<h2>Barnacles<\/h2>/);
 assert.match(page,/waiting for them to accept/);
 assert.match(page,/name="library" value="3"/);
 await act(t,t.friend,'accept',shareId(t));
 page=await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:t.owner.cookie}})).text();
 assert.match(page,/<h3>Friend<\/h3>/);
 await request(t.worker,t.env,'POST',ACC+'/account/delete',{headers:formHeaders(t.friend),form:{confirm:'DELETE'}});
 assert.equal(t.db.prepare("SELECT COUNT(*) n FROM server_shares").get().n,0);
 await invite(t,'later@example.com');
 await request(t.worker,t.env,'POST',ACC+'/account/delete',{headers:formHeaders(t.owner),form:{confirm:'DELETE'}});
 assert.equal(t.db.prepare("SELECT COUNT(*) n FROM server_shares").get().n,0);
});

// ---- Server switcher and server pictures ----------------------------------------
function png(width=64,height=64,extra=0){
 const b=new Uint8Array(33+extra);
 b.set([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82]);
 const v=new DataView(b.buffer);v.setUint32(16,width);v.setUint32(20,height);
 return b;
}
function upload(t,user,{id=t.server.id,bytes=png(),action}={}){
 const form=new FormData();form.set('id',id);
 if(action)form.set('action',action);else form.set('picture',new Blob([bytes],{type:'image/png'}),'icon.png');
 return t.worker.fetch(new Request(ACC+'/account/servers/picture',{method:'POST',body:form,redirect:'manual',
  headers:{cookie:user.cookie,origin:ACC,'sec-fetch-site':'same-origin'}}),t.env);
}
const pictureResult=async r=>new URL((await r).headers.get('location'),ACC).searchParams.get('picture');

test('the switcher lists every server the account can open, marking the current one', async()=>{
 const t=await setup();
 const friendServer=pairedServer(t.env,t.friend.id,{id:'99999999-2222-3333-4444-555555555555',identity:'ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee'});
 await invite(t,'friend@gmail.com');
 await act(t,t.friend,'accept',shareId(t));
 const list=async cookie=>(await (await request(t.worker,t.env,'GET',APP+'/__yarr/servers',{headers:{cookie}})).json());
 let mine=await list(t.friend.cookie);
 assert.deepEqual(mine.servers.map(s=>[s.id,s.role,s.owner_name]),[[friendServer.id,'owner',''],[t.server.id,'barnacle','Owner']]);
 assert.equal(mine.current,friendServer.id,'own server first by default');
 mine=await list(t.friend.cookie+'; __Host-yarr_app_server='+t.server.id);
 assert.equal(mine.current,t.server.id);
 assert.equal((await list(t.owner.cookie)).servers.length,1,'the owner has one server: no switcher');
 assert.equal((await request(t.worker,t.env,'GET',APP+'/__yarr/servers')).status,401);
 // Every own server on My Account has its own Open link (also back to your own server).
 const page=await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:t.friend.cookie}})).text();
 assert.match(page,new RegExp('/__yarr/use\\?server='+friendServer.id));
});

test('owners set a server picture that the people they share with see', async()=>{
 const t=await setup();
 await invite(t,'friend@gmail.com');
 await act(t,t.friend,'accept',shareId(t));
 assert.equal(await pictureResult(upload(t,t.owner)),'saved');
 const tv=await signTvIn(t,t.friend);
 const me=await (await request(t.worker,t.env,'GET',PUB+'/api/device/me',{headers:tv})).json();
 assert.equal(me.servers[0].icon_url,ACC+'/api/server-icons/'+t.server.id+'.png?v=1');
 const img=await request(t.worker,t.env,'GET',me.servers[0].icon_url);
 assert.equal(img.status,200);
 assert.equal(img.headers.get('content-type'),'image/png');
 assert.equal(img.headers.get('x-content-type-options'),'nosniff');
 assert.match(img.headers.get('content-security-policy'),/default-src 'none'/);
 assert.deepEqual(new Uint8Array(await img.arrayBuffer()),png());
 const sw=await (await request(t.worker,t.env,'GET',APP+'/__yarr/servers',{headers:{cookie:t.friend.cookie}})).json();
 assert.equal(sw.servers[0].icon_url,'/__yarr/server-icons/'+t.server.id+'.png?v=1');
 assert.equal((await request(t.worker,t.env,'GET',APP+sw.servers[0].icon_url)).status,200);
 assert.match(await (await request(t.worker,t.env,'GET',ACC+'/',{headers:{cookie:t.friend.cookie}})).text(),/class="server-picture"/);
 // A new upload changes the address, so caches pick it up.
 assert.equal(await pictureResult(upload(t,t.owner,{bytes:png(128,128)})),'saved');
 assert.equal(t.db.prepare("SELECT version FROM server_icons").get().version,2);
 // Checks: PNG only, size limits, only the owner, and removal.
 assert.equal(await pictureResult(upload(t,t.owner,{bytes:new TextEncoder().encode('<svg onload=alert(1)>')})),'not_png');
 assert.equal(await pictureResult(upload(t,t.owner,{bytes:png(16,16)})),'size');
 assert.equal(await pictureResult(upload(t,t.owner,{bytes:png(64,64,300*1024)})),'too_large');
 assert.equal(await pictureResult(upload(t,t.friend)),'not_found');
 assert.equal(t.db.prepare("SELECT version FROM server_icons").get().version,2);
 const forged=await t.worker.fetch(new Request(ACC+'/account/servers/picture',{method:'POST',body:new FormData(),redirect:'manual',headers:{cookie:t.owner.cookie,origin:'https://evil.example'}}),t.env);
 assert.equal(forged.status,403);
 assert.equal(await pictureResult(upload(t,t.owner,{action:'remove'})),'removed');
 assert.equal((await request(t.worker,t.env,'GET',ACC+'/api/server-icons/'+t.server.id+'.png')).status,404);
});

test('"needs Pro" is not shown to an account that has Pro, and refusals are recorded', async()=>{
 const t=await setup();
 const page=async user=>(await (await request(t.worker,t.env,'GET',ACC+'/?remote=pro_required',{headers:{cookie:user.cookie}})).text());
 assert.doesNotMatch(await page(t.owner),/Remote access needs Pro/);
 assert.match(await page(t.friend),/Remote access needs Pro/);
 const r=await request(t.worker,t.env,'GET',ACC+'/remote/open?server='+t.server.id,{headers:{cookie:t.friend.cookie},redirect:'manual'});
 assert.match(r.headers.get('location')||'',/remote=not_found/);
 // A friend with their own server and no Pro is refused for their own server, and it's recorded.
 const own=pairedServer(t.env,t.friend.id,{id:'99999999-2222-3333-4444-555555555555',identity:'ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee'});
 t.db.prepare("UPDATE servers SET public_ip='76.183.183.205' WHERE id=?").run(own.id);
 const refused=await request(t.worker,t.env,'GET',ACC+'/remote/open?server='+own.id,{headers:{cookie:t.friend.cookie},redirect:'manual'});
 assert.match(refused.headers.get('location')||'',/remote=pro_required/);
 assert.equal(t.db.prepare("SELECT detail FROM audit_log WHERE event='pass_refused'").get().detail,'pro_required '+own.id);
});
