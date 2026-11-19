// Runs the real worker.js against an in-memory SQLite copy of the D1 schema.
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import {webcrypto} from 'node:crypto';

const HERE=new URL('.',import.meta.url);
const MIGRATIONS=new URL('../migrations/',HERE);

class Stmt {
 constructor(db,sql,args=[]){this.db=db;this.sql=sql;this.args=args;}
 bind(...args){
  for(const v of args)if(v===undefined)throw new Error('D1_TYPE_ERROR: undefined bound in '+this.sql);
  return new Stmt(this.db,this.sql,args.map(v=>typeof v==='boolean'?(v?1:0):v));
 }
 async first(col){const r=this.db.prepare(this.sql).get(...this.args);if(!r)return null;const o={...r};return col?o[col]:o;}
 async all(){return {success:true,results:this.db.prepare(this.sql).all(...this.args).map(r=>({...r}))};}
 runSync(){
  const st=this.db.prepare(this.sql);
  if(/\bRETURNING\b/i.test(this.sql)){const rows=st.all(...this.args);return {success:true,results:rows,meta:{changes:rows.length}};}
  const r=st.run(...this.args);
  return {success:true,meta:{changes:Number(r.changes),last_row_id:Number(r.lastInsertRowid)}};
 }
 async run(){return this.runSync();}
}
export function fakeD1(){
 const db=new DatabaseSync(':memory:');
 db.exec('PRAGMA foreign_keys=ON');
 for(const f of readdirSync(MIGRATIONS).filter(f=>f.endsWith('.sql')).sort())db.exec(readFileSync(new URL(f,MIGRATIONS),'utf8'));
 return {
  raw:db,
  prepare:sql=>new Stmt(db,sql),
  async batch(list){db.exec('BEGIN');try{const out=list.map(s=>s.runSync());db.exec('COMMIT');return out;}catch(e){db.exec('ROLLBACK');throw e;}}
 };
}

export const b64url=bytes=>Buffer.from(bytes).toString('base64url');
export async function digest(value){return b64url(new Uint8Array(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(value))));}

export async function newPassKey(kid='test-1'){
 const pair=await webcrypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
 const jwk=await webcrypto.subtle.exportKey('jwk',pair.privateKey);
 return {...jwk,kid};
}

export async function loadWorker(){
 // Fresh module per test file so module-level caches do not leak between envs.
 return (await import(new URL('../worker.js?'+Math.random(),HERE))).default;
}

export function makeEnv(extra={}){
 return {ACCOUNTS:fakeD1(),GOOGLE_CLIENT_ID:'client-id',GOOGLE_CLIENT_SECRET:'client-secret',...extra};
}

// A signed-in user with a session cookie for accounts.yarr.media.
export async function signedInUser(env,{id='user-1',email='owner@example.com'}={}){
 const db=env.ACCOUNTS.raw;
 db.prepare("INSERT INTO users(id,google_sub,email,display_name) VALUES(?,?,?,?)").run(id,'g-'+id,email,'Owner');
 const token='session-'+id+'-'+'x'.repeat(20);
 db.prepare("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,datetime('now','+1 day'))").run('s-'+id,id,await digest(token));
 return {id,email,cookie:'__Secure-yarr_session='+token};
}
export function pairedServer(env,ownerId,{id='11111111-2222-3333-4444-555555555555',identity='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',publicUrl=null}={}){
 env.ACCOUNTS.raw.prepare("INSERT INTO servers(id,owner_user_id,display_name,status,server_identity,public_url) VALUES(?,?,?,?,?,?)").run(id,ownerId,'Home','paired',identity,publicUrl);
 return {id,identity};
}

export function request(worker,env,method,url,{headers={},body,form,json:obj}={}){
 const h=new Headers(headers);
 let payload=body;
 if(form){payload=new URLSearchParams(form).toString();h.set('content-type','application/x-www-form-urlencoded');}
 if(obj!==undefined){payload=JSON.stringify(obj);h.set('content-type','application/json');}
 return worker.fetch(new Request(url,{method,headers:h,body:payload,redirect:'manual'}),env);
}

// Swap globalThis.fetch for the duration of a test.
export function mockFetch(handler){
 const original=globalThis.fetch;
 const calls=[];
 globalThis.fetch=async(input,init={})=>{
  const req=input instanceof Request?input:new Request(input,init);
  const body=req.method==='GET'||req.method==='HEAD'?'':await req.text();
  calls.push({url:req.url,method:req.method,body,headers:req.headers});
  const res=await handler(req.url,req.method,body,req.headers);
  if(res)return res;
  throw new Error('unexpected fetch '+req.method+' '+req.url);
 };
 return {calls,restore(){globalThis.fetch=original;}};
}
export const jsonResponse=(obj,status=200)=>new Response(JSON.stringify(obj),{status,headers:{'content-type':'application/json'}});
