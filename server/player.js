/* Fullscreen-first native player with HLS compatibility streaming.
 * HLS assets come only from the NUC's protected direct origin.
 * Hls.js 1.7.4 is pinned for MSE browsers; Safari plays HLS natively. */
(() => {
  let current=null, mediaId=0, status=null, hls=null, session=null;
  let started=false, saveAt=0, offset=0, switching=false, playbackMode='direct';
  let monitor=null;
  let captions=null;
  let captionsSelect=null;
  function syncCaptions(){
    if(captions){captions.remove();captions=null}
    if(!current||!captionsSelect)return;
    const value=captionsSelect.value;
    if(!/^(external|embedded)-[0-9]{1,3}$/.test(value))return;
    const video=current.querySelector('video');
    const track=document.createElement('track');
    track.kind='subtitles';track.label=captionsSelect.selectedOptions[0].textContent;
    track.srclang='en';
    track.src='/api/stream/subtitles/'+mediaId+'/'+value+'.vtt'+
      (playbackMode==='hls'&&offset>0?'?start='+encodeURIComponent(offset):'');
    track.default=true;
    track.onload=()=>{if(track.track)track.track.mode='showing'};
    track.onerror=()=>message('This subtitle track could not be loaded.');
    video.append(track);captions=track;
    if(track.track)track.track.mode='showing';
  }
  const css=`
.willie-player{position:fixed;inset:0;z-index:10000;background:#000;color:#f0f5fb;
display:flex;align-items:center;justify-content:center;font:16px system-ui,sans-serif}
.willie-player:fullscreen{width:100vw;height:100vh}
.willie-video{width:100%;height:100%;object-fit:contain;background:#000}
.willie-controls{position:absolute;top:0;left:0;right:0;z-index:5;padding:17px 20px;
background:linear-gradient(#020711df,transparent);display:flex;align-items:center;gap:10px;
opacity:0;transition:opacity .15s}
.willie-player:hover .willie-controls,.willie-player:focus-within .willie-controls{opacity:1}
.willie-controls button{background:#172636e9;border:1px solid #4b6078;border-radius:10px;
color:#fff;padding:10px 13px;cursor:pointer;font:inherit}
.willie-controls button:hover{background:#2a435f}
.willie-subtitle-select{background:#172636e9;border:1px solid #4b6078;border-radius:10px;
color:#fff;padding:10px 12px;font:inherit;max-width:180px;cursor:pointer}
.willie-subtitle-select option{background:#172636;color:#fff}
.willie-subtitle-select[hidden]{display:none}
.willie-title{font-weight:650;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.willie-info{position:absolute;left:50%;bottom:90px;transform:translateX(-50%);
background:#172637ec;color:#e8f3ff;border:1px solid #324c66;border-radius:12px;
max-width:85vw;padding:13px 19px;text-align:center;z-index:6}
.willie-info:empty{display:none}
.willie-timeline{position:absolute;bottom:9px;left:20px;right:20px;display:flex;
align-items:center;gap:12px;background:#0b1620d9;padding:10px 15px;border-radius:12px;z-index:5}
.willie-timeline input{flex:1;accent-color:#b2cde8;cursor:pointer}
.willie-timeline span{font-size:12px;color:#bccddd;font-variant-numeric:tabular-nums}
@media(hover:none){.willie-controls{opacity:1}}
`;
  const style=document.createElement('style');style.textContent=css;document.head.append(style);
  const requestJson=async(url,opts={})=>{
    const res=await fetch(url,{cache:'no-store',...opts});
    let data={};try{data=await res.json()}catch(_){}
    if(!res.ok)throw Error(data.detail||('Server returned '+res.status));
    return data;
  };
  const formatTime=seconds=>{
    const value=Math.max(0,Math.floor(Number(seconds)||0));
    return [Math.floor(value/3600),Math.floor(value%3600/60),value%60]
      .map((x,i)=>i===0?String(x):String(x).padStart(2,'0')).join(':');
  };
  function message(text){const el=current?.querySelector('.willie-info');if(el)el.textContent=text;}
  function playerPosition(video){
    return Math.max(0,(playbackMode==='hls'?offset:0)+(video.currentTime||0));
  }
  function destroyStream(){
    if(hls){hls.destroy();hls=null}
    const old=session;session=null;
    if(old)fetch('/api/stream/hls/'+old,{method:'DELETE',keepalive:true}).catch(()=>{});
  }
  async function saveProgress(force=false,done=false){
    if(!current||!started||!mediaId)return;
    const video=current.querySelector('video');
    const duration=Number(status?.duration_seconds)||video.duration;
    if(!Number.isFinite(duration)||duration<=0)return;
    if(!force&&Date.now()-saveAt<12000)return;
    saveAt=Date.now();
    try{await requestJson('/api/playback/progress',{
      method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({media_id:mediaId,duration_seconds:duration,
        position_seconds:Math.min(duration,playerPosition(video)),
        completed:done||Boolean(status?.watched)||playerPosition(video)>=duration*.95}),keepalive:force});
    }catch(_){}
  }
  function close(){
    if(!current)return;
    const node=current,video=node.querySelector('video');
    saveProgress(true);
    clearInterval(monitor);monitor=null;
    video.pause();destroyStream();
    video.removeAttribute('src');video.load();
    current=null;mediaId=0;status=null;started=false;offset=0;switching=false;captions=null;captionsSelect=null;
    if(document.fullscreenElement===node)document.exitFullscreen().catch(()=>{});
    node.remove();
    document.dispatchEvent(new CustomEvent('willie:watch-updated'));
  }
  async function loadHlsLibrary(){
    if(window.Hls)return window.Hls;
    if(!window.__willieHlsPromise){
      window.__willieHlsPromise=new Promise((resolve,reject)=>{
        const script=document.createElement('script');
        script.src='https://cdn.jsdelivr.net/npm/hls.js@1.7.4/dist/hls.min.js';
        script.async=true;script.onload=()=>window.Hls?resolve(window.Hls):reject(Error('HLS support unavailable'));
        script.onerror=()=>reject(Error('HLS player could not load. Check your internet connection.'));
        document.head.append(script);
      });
    }
    return window.__willieHlsPromise;
  }
  async function playHls(startSeconds){
    if(!current||switching)return;
    switching=true;started=false;
    const surface=current,video=surface.querySelector('video');
    const seek=Math.max(0,Math.min(Number(status?.duration_seconds)||1e7,startSeconds));
    await saveProgress(true);
    destroyStream();video.pause();video.removeAttribute('src');video.load();
    offset=seek;playbackMode='hls';
    syncCaptions();
    message('Preparing compatible HLS stream…');
    try{
      const result=await requestJson('/api/stream/hls/start/'+mediaId+
        '?start='+encodeURIComponent(seek),{method:'POST'});
      if(current!==surface)return;
      session=result.session;
      status.duration_seconds=status.duration_seconds||result.duration;
      let ready=null;
      for(let i=0;i<80;i++){
        await new Promise(resolve=>setTimeout(resolve,400));
        if(current!==surface)return;
        ready=await requestJson('/api/stream/hls/'+session+'/status');
        if(ready.ready)break;
      }
      if(!ready?.ready)throw Error('HLS transcoding did not start. Check server transcoder logs.');
      const url=ready.playlist;
      message('Starting '+ready.engine+' playback…');
      if(video.canPlayType('application/vnd.apple.mpegurl')){
        video.src=url;
      }else{
        const Hls=await loadHlsLibrary();
        if(!Hls.isSupported())throw Error('This browser does not support HLS playback.');
        hls=new Hls({lowLatencyMode:false,maxBufferLength:20,liveSyncDurationCount:3});
        hls.on(Hls.Events.ERROR,(_event,data)=>{
          if(data.fatal)message('HLS stream error: '+(data.details||data.type));
        });
        hls.loadSource(url);
        hls.attachMedia(video);
      }
      video.play().then(()=>message('')).catch(()=>message('Press Play to start the video.'));
    }catch(error){if(current===surface)message(error.message)}
    finally{switching=false}
  }
  function start(media, title, options={}){
    const id=Number(media);
    if(!Number.isInteger(id)||id<=0)return;
    if(current)close();
    if(location.hostname.endsWith('.workers.dev')){
      fetch('/api/remote/settings',{cache:'no-store'}).then(r=>r.json()).then(data=>{
        const ip=String(data.public_ip||'').split('.').map(Number);
        if(ip.length!==4||ip.some(x=>!Number.isInteger(x)||x<0||x>255))
          throw Error('Server address unavailable');
        location.href='https://'+ip.join('-')+'.sslip.io/watch/'+id+
          (options.restart?'?restart=1':'');
      }).catch(()=>alert('Open the protected direct NUC address for video playback.'));
      return;
    }
    const surface=document.createElement('div');surface.className='willie-player';
    surface.setAttribute('role','dialog');surface.setAttribute('aria-label','Media player');
    const video=document.createElement('video');video.className='willie-video';
    video.controls=true;video.autoplay=true;video.playsInline=true;video.preload='metadata';
    const controls=document.createElement('div');controls.className='willie-controls';
    const back=document.createElement('button');back.type='button';back.textContent='← Back';back.onclick=close;
    const name=document.createElement('span');name.className='willie-title';name.textContent=title||'Now playing';
    const backward=document.createElement('button');backward.textContent='−10s';
    const forward=document.createElement('button');forward.textContent='+10s';
    const cc=document.createElement('select');cc.className='willie-subtitle-select';
    cc.setAttribute('aria-label','Subtitles');cc.title='Subtitles';
    cc.hidden=true;
    const off=document.createElement('option');off.value='';off.textContent='CC Off';cc.append(off);
    cc.onchange=syncCaptions;
    const watch=document.createElement('button');watch.textContent='Mark watched';
    watch.onclick=async()=>{
      try{
        const value=!status.watched;
        await requestJson('/api/watch/'+id+'/watched',{method:'PUT',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({watched:value})});
        status.watched=value;watch.textContent=value?'✓ Watched':'Mark watched';
        document.dispatchEvent(new CustomEvent('willie:watch-updated'));
      }catch(error){message(error.message)}
    };
    const seekBy=delta=>{
      if(!status)return;
      const target=playerPosition(video)+delta;
      if(playbackMode==='hls')playHls(target);
      else video.currentTime=Math.max(0,Math.min(video.duration||1e7,target));
    };
    backward.onclick=()=>seekBy(-10);forward.onclick=()=>seekBy(10);
    controls.append(back,name,backward,forward,cc,watch);
    const info=document.createElement('div');info.className='willie-info';info.setAttribute('role','status');
    const timeline=document.createElement('div');timeline.className='willie-timeline';
    const elapsed=document.createElement('span');elapsed.textContent='0:00:00';
    const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='1000';slider.value='0';
    slider.setAttribute('aria-label','Playback position');
    const total=document.createElement('span');total.textContent='0:00:00';
    timeline.append(elapsed,slider,total);
    surface.append(video,controls,info,timeline);
    document.body.append(surface);current=surface;mediaId=id;started=false;offset=0;captionsSelect=cc;
    // Must be synchronous with user's Play click for fullscreen permission.
    try{surface.requestFullscreen?.().catch(()=>{})}catch(_){}
    let entered=false;
    const fullscreenChanged=()=>{
      if(document.fullscreenElement===surface)entered=true;
      else if(entered&&current===surface)close();
      if(current!==surface)document.removeEventListener('fullscreenchange',fullscreenChanged);
    };
    document.addEventListener('fullscreenchange',fullscreenChanged);
    surface.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.fullscreenElement)close()});
    slider.addEventListener('change',()=>{
      if(!status)return;
      const duration=Number(status.duration_seconds)||video.duration;
      if(!Number.isFinite(duration)||duration<=0)return;
      const target=duration*Number(slider.value)/1000;
      if(playbackMode==='hls')playHls(target);
      else video.currentTime=target;
    });
    monitor=setInterval(()=>{
      if(current!==surface)return;
      const duration=Number(status?.duration_seconds)||video.duration;
      if(Number.isFinite(duration)&&duration>0){
        const now=Math.min(duration,playerPosition(video));
        if(document.activeElement!==slider)slider.value=String(Math.round(1000*now/duration));
        elapsed.textContent=formatTime(now);total.textContent=formatTime(duration);
      }
    },500);
    video.addEventListener('playing',()=>{started=true;message('')});
    video.addEventListener('timeupdate',()=>saveProgress());
    video.addEventListener('pause',()=>saveProgress(true));
    video.addEventListener('ended',()=>{saveProgress(true,true);if(status)status.watched=true;
      watch.textContent='✓ Watched';document.dispatchEvent(new CustomEvent('willie:watch-updated'))});
    video.addEventListener('error',()=>{
      if(playbackMode==='direct')playHls(playerPosition(video));
      else message('Unable to decode HLS stream. Check FFmpeg and media format.');
    });
    message('Opening video…');
    requestJson('/api/watch/'+id+'/status').then(data=>{
      if(current!==surface)return;
      status=data;watch.textContent=data.watched?'✓ Watched':'Mark watched';
      requestJson('/api/stream/subtitles/'+id).then(info=>{
        if(current!==surface)return;
        for(const item of info.tracks||[]){
          if(!/^(external|embedded)-[0-9]{1,3}$/.test(item.id))continue;
          const option=document.createElement('option');option.value=item.id;
          option.textContent='CC '+String(item.label||'Subtitles').slice(0,80);
          cc.append(option);
        }
        cc.hidden=cc.options.length===1;
      }).catch(()=>{});
      const resume=options.restart||data.watched?0:Number(data.position_seconds)||0;
      if(data.mode==='direct'){
        playbackMode='direct';video.src=data.stream_url;
        if(resume>5)video.addEventListener('loadedmetadata',()=>{
          if(Number.isFinite(video.duration)&&resume<video.duration-4)video.currentTime=resume;
        },{once:true});
        video.play().catch(()=>message('Press Play to start.'));
      }else playHls(resume);
    }).catch(e=>message(e.message));
  }
  window.WilliePlayer={open:start,close};
})();
