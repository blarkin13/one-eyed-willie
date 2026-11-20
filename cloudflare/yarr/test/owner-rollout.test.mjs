import test from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,signedInUser,request,mockFetch,jsonResponse} from './harness.mjs';
import {recordPublicPage,readSiteStats,readReleaseStats} from '../owner-site-stats.js';
test('site stats count requests without storing personal identifiers',async()=>{
 const env=makeEnv({YARR_OWNER_ANALYTICS_ENABLED:'true'});
 await recordPublicPage(env,'/');await recordPublicPage(env,'/');
 const row=await readSiteStats(env);assert.equal(row.total,2);
 assert.deepEqual(Object.keys(env.ACCOUNTS.raw.prepare('SELECT * FROM owner_site_daily').get()).sort(),['day','path','requests']);
 const fetcher=async()=>jsonResponse([{draft:false,prerelease:false,assets:[{name:'yarr-media-google-tv.apk',download_count:12},{name:'install.sh',download_count:3},{name:'yarr.deb',download_count:7}]},{draft:true,assets:[{name:'yarr-media-google-tv.apk',download_count:100}]}]);
 assert.deepEqual(await readReleaseStats(env,fetcher),{tv:12,android:0,linux:7,installer:3});
});
test('email worker forwards, stores originals and deduplicates',async()=>{
 const objects=new Map();const env=makeEnv({YARR_OWNER_ACCOUNT_ID:'owner',SUPPORT_MAIL_INBOX_ENABLED:'true',SUPPORT_MAIL_FORWARD_TO:'owner@example.com',MAIL_MESSAGES:{put:async(k,v)=>objects.set(k,v),delete:async(k)=>objects.delete(k),get:async(k)=>objects.has(k)?{body:objects.get(k)}:null}});
 const worker=await loadWorker(),owner=await signedInUser(env,{id:'owner'});
 const raw='From: test@example.net\r\nTo: support@yarr.media\r\nSubject: Hello\r\nMessage-ID: <test@example.net>\r\nContent-Type: text/plain\r\n\r\nTest body';
 let forwarded=0;
 const message=()=>({to:'support@yarr.media',from:'test@example.net',headers:new Headers({'subject':'Hello','message-id':'<test@example.net>'}),raw:new Blob([raw]).stream(),rawSize:new TextEncoder().encode(raw).length,forward:async(dest)=>{assert.equal(dest,'owner@example.com');forwarded++;}});
 await worker.email(message(),env);await worker.email(message(),env);
 assert.equal(forwarded,2);assert.equal(objects.size,1);
 const root='https://yarr.media/api/support-mail/',headers={cookie:owner.cookie};
 const list=await (await request(worker,env,'GET',root+'threads',{headers})).json();
 assert.equal(list.threads.length,1);assert.equal(list.threads[0].alias,'support@yarr.media');
 const thread=await (await request(worker,env,'GET',root+'threads/'+list.threads[0].id,{headers})).json();
 assert.equal(thread.messages.length,1);assert.match(thread.messages[0].body_text,/Test body/);
 const original=await request(worker,env,'GET',root+'messages/'+thread.messages[0].id+'/original',{headers});
 assert.equal(await original.text(),raw);assert.match(original.headers.get('content-disposition'),/attachment/);
 const bad=message();bad.forward=async()=>{throw Error('forward failed')};await assert.rejects(()=>worker.email(bad,env));assert.equal(objects.size,1);
 env.SUPPORT_MAIL_SEND_ENABLED='true';env.RESEND_API_KEY='fake';
 const mock=mockFetch(async(url,method,body)=>{assert.equal(url,'https://api.resend.com/emails');assert.match(JSON.parse(body).from,/support@yarr.media/);return jsonResponse({id:'12345678-1234-1234-1234-123456789abc'});});
 try{const reply=await request(worker,env,'POST',root+'threads/'+list.threads[0].id+'/reply',{headers:{...headers,origin:'https://yarr.media'},json:{body:'Test reply'}});assert.equal(reply.status,200);assert.equal(mock.calls.length,1);}finally{mock.restore();}
});
