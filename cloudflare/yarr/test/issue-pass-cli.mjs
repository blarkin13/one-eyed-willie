// Prints {pass, keys, server_identity} issued by the real Worker code.
// Used by tests/test_remote_access.py to check the Python verifier against it.
import {loadWorker,makeEnv,signedInUser,pairedServer,request,newPassKey} from './harness.mjs';
const worker=await loadWorker();
const env=makeEnv({PASS_SIGNING_KEY:JSON.stringify(await newPassKey('cli-key'))});
const user=await signedInUser(env);
const server=pairedServer(env,user.id,{identity:process.argv[2]||'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'});
env.ACCOUNTS.raw.prepare("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('m',?,'active','manual')").run(user.id);
const res=await request(worker,env,'POST','https://accounts.yarr.media/api/passes',{headers:{cookie:user.cookie,origin:'https://accounts.yarr.media'},json:{server_id:server.id}});
const keys=await (await request(worker,env,'GET','https://yarr.media/api/passes/keys')).json();
process.stdout.write(JSON.stringify({pass:(await res.json()).pass,keys,server_identity:server.identity}));
