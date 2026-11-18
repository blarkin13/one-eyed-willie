/* Yarr: negotiate peer transport using the signed-in account, then bridge
 * native <video> / Hls.js requests through a Service Worker. Fails closed.
 * Experimental pilot: no silent Cloudflare video relay fallback.
 */
(()=>{
 if(!location.hostname.startsWith('yarr.')||!window.RTCPeerConnection||!navigator.serviceWorker)return;
 const isMediaPath=path=>/^\/api\/(?:watch\/\d+\/stream|stream\/hls\/) /.test(path);
 let pc=null,ready=false,attempt=null;
 const sessions=new Set();
 const note=msg=>{window.YarrDirectPeerStatus=msg;window.dispatchEvent(new CustomEvent('yarr:peer:status',{detail:msg}));};
 const waitIce=peer=>new Promise((resolve,reject)=>{
  if(peer.iceGatheringState==='complete')return resolve();
  const timer=setTimeout(()=>reject(Error('ICE gathering timeout')),16000);
  peer.addEventListener('icegatheringstatechange',function changed(){
   if(peer.iceGatheringState==='complete'){
    clearTimeout(timer);peer.removeEventListener('icegatheringstatechange',changed);resolve();
   }
  });
 });
 const waitConnected=peer=>new Promise((resolve,reject)=>{
  if(peer.connectionState==='connected')return resolve();
  const timer=setTimeout(()=>reject(Error('Direct connection timeout')),15000);
  peer.addEventListener('connectionstatechange',function changed(){
   if(peer.connectionState==='connected'||peer.connectionState==='failed'||peer.connectionState==='closed'){
    clearTimeout(timer);peer.removeEventListener('connectionstatechange',changed);
    if(peer.connectionState==='connected')resolve();else reject(Error('Direct connection failed'));
   }
  });
 });
 async function connect(){
  if(attempt)return attempt;
  attempt=(async()=>{
   note('connecting');
   const peer=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
   pc=peer;
   // A setup data channel ensures SDP contains application/SCTP negotiation.
   const setup=peer.createDataChannel('yarr-media-v1:setup');
   setup.onopen=()=>setup.close();
   await peer.setLocalDescription(await peer.createOffer());
   await waitIce(peer);
   const response=await fetch('/api/yarr/direct/offer',{
    method:'POST',headers:{'content-type':'application/json'},
    credentials:'same-origin',body:JSON.stringify({type:'offer',sdp:peer.localDescription.sdp}),cache:'no-store'
   });
   if(!response.ok)throw Error('Direct connection offer rejected ('+response.status+')');
   const answer=await response.json();
   await peer.setRemoteDescription({type:answer.type,sdp:answer.sdp});
   await waitConnected(peer);
   ready=true;note('connected');
   return peer;
  })().catch(error=>{ready=false;note('unavailable: '+error.message);pc?.close();pc=null;attempt=null;throw error;});
  return attempt;
 }
 navigator.serviceWorker.addEventListener('message',async event=>{
  const data=event.data,port=event.ports?.[0];
  if(data?.type!=='yarr:peer:get'||!port)return;
  let channel,closed=false;
  const abort=message=>{if(closed)return;closed=true;port.postMessage({type:'error',message});channel?.close();port.close();};
  port.onmessage=({data:cmd})=>{if(cmd?.type==='cancel')abort('Cancelled')};
  try{
   await connect();
   channel=pc.createDataChannel('yarr-media-v1:'+crypto.randomUUID());
   sessions.add(channel);
   channel.binaryType='arraybuffer';
   channel.onopen=()=>channel.send(JSON.stringify({type:'get',path:data.path,headers:data.headers||{}}));
   channel.onmessage=({data:payload})=>{
    if(closed)return;
    if(typeof payload==='string'){
     let control;try{control=JSON.parse(payload)}catch(_){return abort('Invalid peer response')}
     if(control.type==='headers')port.postMessage({type:'headers',status:control.status,headers:control.headers});
     else if(control.type==='done'){port.postMessage({type:'done'});closed=true;channel.close();port.close();}
     else if(control.type==='error')abort(control.message||'Media unavailable');
    }else port.postMessage({type:'chunk',body:payload},[payload]);
   };
   channel.onerror=()=>abort('Direct media channel error');
   channel.onclose=()=>{sessions.delete(channel);if(!closed)abort('Direct media channel closed')};
  }catch(error){abort(error.message)}
 });
 (async()=>{
  try{
   await navigator.serviceWorker.register('/_yarr_direct_sw.js',{scope:'/',updateViaCache:'none'});
   if(!navigator.serviceWorker.controller){
    await navigator.serviceWorker.ready;
    if(!sessionStorage.getItem('yarr:direct-sw-ready')){
     sessionStorage.setItem('yarr:direct-sw-ready','1');
     location.reload();return;
    }
   }
   // Begin ICE negotiation before the user presses play.
   connect().catch(()=>{});
  }catch(error){note('unavailable: '+error.message)}
 })();
 window.addEventListener('pagehide',()=>{for(const channel of sessions)channel.close();pc?.close()});
})();
