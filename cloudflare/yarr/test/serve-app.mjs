// Serves the real Worker on http://localhost:<port> as if it were app.yarr.media,
// for tests/test_app_service_worker_browser.py. Prints one JSON line when ready.
//   node serve-app.mjs <port> <server-origin> <server-identity>
import http from 'node:http';
import {loadWorker,makeEnv,signedInUser,pairedServer,request,newPassKey} from './harness.mjs';
const [port,serverOrigin,identity]=process.argv.slice(2);
const worker=await loadWorker();
const env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(await newPassKey('e2e'))});
const user=await signedInUser(env);
pairedServer(env,user.id,{identity,publicUrl:serverOrigin});
env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m',?,'active','manual')").run(user.id);
const keys=await (await request(worker,env,'GET','https://yarr.media/api/passes/keys')).json();
http.createServer(async(req,res)=>{
 const chunks=[];for await(const c of req)chunks.push(c);
 const headers=new Headers();
 for(const [k,v] of Object.entries(req.headers))if(k!=='host')headers.set(k,Array.isArray(v)?v.join(', '):v);
 const body=['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks);
 const r=await worker.fetch(new Request('https://app.yarr.media'+req.url,{method:req.method,headers,body,redirect:'manual'}),env);
 const out={};r.headers.forEach((v,k)=>{out[k]=v;});
 let loc=out.location;
 if(loc&&loc.startsWith('https://app.yarr.media'))out.location=loc.slice('https://app.yarr.media'.length)||'/';
 res.writeHead(r.status,out);
 res.end(Buffer.from(await r.arrayBuffer()));
}).listen(Number(port),'127.0.0.1',()=>{
 process.stdout.write(JSON.stringify({cookie:user.cookie.split('=').slice(1).join('='),keys})+'\n');
});
