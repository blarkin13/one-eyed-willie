/* Yarr direct-media Service Worker.
 * Converts same-origin browser media GET requests into streams supplied by the
 * authenticated page's encrypted peer connection, without proxying video
 * through Cloudflare. No caching or cross-origin requests.
 */
const MEDIA=[
 /^\/api\/watch\/[1-9]\d*\/stream$/,
 /^\/api\/stream\/hls\/[a-f0-9]{32}\/(?:index\.m3u8|init\.mp4|segment_\d{6}\.(?:ts|m4s))$/,
 /^\/api\/stream\/subtitles\/[1-9]\d*\/(?:external|embedded)-\d{1,3}\.vtt$/,
 /^\/api\/maintenance\/preview\/[1-9]\d*\/0(?:0\d|1\d|2[0-3])\.jpg$/
];
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
 const req=event.request, url=new URL(req.url);
 if(req.method!=='GET'||url.origin!==self.location.origin||!MEDIA.some(pattern=>pattern.test(url.pathname)))return;
 event.respondWith((async()=>{
  const client=event.clientId&&await self.clients.get(event.clientId);
  if(!client)return new Response('Direct viewer unavailable',{status:503});
  return new Promise(resolve=>{
   const pipe=new MessageChannel();
   let streamController,ready=false,finished=false;
   let timer=setTimeout(()=>fail('Peer connection timed out'),18000);
   const finish=()=>{
    if(finished)return;finished=true;
    clearTimeout(timer);
    pipe.port1.close();
   };
   const fail=message=>{
    if(finished)return;
    if(!ready){finish();resolve(new Response(message,{status:503,headers:{'cache-control':'no-store'}}));}
    else{streamController.error(new Error(message));finish();}
   };
   const stream=new ReadableStream({
    start(controller){streamController=controller;},
    cancel(){pipe.port1.postMessage({type:'cancel'});finish();}
   },{highWaterMark:16});
   pipe.port1.onmessage=({data})=>{
    if(!data||finished)return;
    if(data.type==='headers'){
     if(ready)return fail('Duplicate response headers');
     ready=true;clearTimeout(timer);
     timer=setTimeout(()=>fail('Peer media stream timed out'),120000);
     const headers=new Headers(data.headers||{});
     headers.set('cache-control','private, no-store');
     resolve(new Response(stream,{status:data.status||200,headers}));
    }else if(data.type==='chunk'){
     if(!ready)return fail('Media bytes arrived before headers');
     streamController.enqueue(data.body);
     clearTimeout(timer);
     timer=setTimeout(()=>fail('Peer media stream timed out'),120000);
    }else if(data.type==='done'){
     if(!ready)return fail('Missing response headers');
     streamController.close();finish();
    }else if(data.type==='error'){
     fail(data.message||'Direct media request failed');
    }
   };
   client.postMessage({
    type:'yarr:peer:get',path:url.pathname+url.search,
    headers:Object.fromEntries([...req.headers].filter(([k])=>['range','if-range','if-none-match','accept'].includes(k.toLowerCase())))
   },[pipe.port2]);
  });
 })());
});
