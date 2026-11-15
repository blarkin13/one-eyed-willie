/* Immersive player: fullscreen requested synchronously from user click.
   Media bytes never cross the Cloudflare Worker. */
(() => {
  let current = null;
  let saveAt = 0;
  let lastMediaId = 0;
  let savedStatus = null;
  let timeOffset=0;
  let enteredFullscreen=false;
  let hasStarted=false;
  const css = `
.willie-player{position:fixed;inset:0;z-index:10000;background:#03060b;color:#edf4fb;
 display:flex;align-items:center;justify-content:center;font:16px system-ui,-apple-system,sans-serif}
.willie-player:fullscreen{width:100vw;height:100vh}
.willie-video{display:block;width:100%;height:100%;object-fit:contain;background:#000}
.willie-controls{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;
 gap:12px;padding:14px 18px;background:linear-gradient(#03060bc9,transparent);
 opacity:0;transition:opacity .2s}
.willie-player:hover .willie-controls,.willie-player:focus-within .willie-controls{opacity:1}
.willie-controls button{background:#192839;color:#fff;border:1px solid #40566d;
 border-radius:9px;padding:10px 14px;cursor:pointer;font:inherit}
.willie-controls button:hover{background:#30465c}
.willie-controls .willie-title{flex:1;text-overflow:ellipsis;overflow:hidden;white-space:nowrap;font-weight:600}
.willie-info{position:absolute;bottom:56px;left:50%;transform:translateX(-50%);
 max-width:min(90vw,640px);color:#fff;border-radius:12px;background:#111c2be8;
 padding:13px 19px;text-align:center;z-index:3}
.willie-info:empty{display:none}
.willie-compatible-seek{display:flex;gap:8px;align-items:center}
.willie-compatible-seek button{background:#192839;color:#fff;border:1px solid #40566d;
 border-radius:9px;padding:10px 12px;cursor:pointer;font:inherit}
@media(hover:none){.willie-controls{opacity:1}}
`;
  const style=document.createElement('style');style.textContent=css;document.head.append(style);
  const statusUrl = id => '/api/watch/'+id+'/status';
  const progressUrl = '/api/playback/progress';

  async function saveProgress(force=false, ended=false) {
    if(!current || !lastMediaId || !hasStarted)return;
    const video=current.querySelector('video');
    if(!video)return;
    const duration=Number(savedStatus?.duration_seconds)||video.duration;
    if(!Number.isFinite(duration) || duration<=0)return;
    const now=Date.now();
    if(!force&&now-saveAt<12000)return;
    saveAt=now;
    const position=Math.min((video.currentTime||0)+timeOffset,duration);
    try{
      await fetch(progressUrl,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({media_id:lastMediaId,position_seconds:position,
          duration_seconds:duration,completed:ended||position>=duration*.95}),
        keepalive:force});
    }catch(_){}
  }
  function setMessage(text) {
    const box=current?.querySelector('.willie-info');if(box)box.textContent=text;
  }
  function close() {
    if(!current)return;
    const container=current;
    const video=container.querySelector('video');
    saveProgress(true);
    video.pause();video.removeAttribute('src');video.load();
    current=null;lastMediaId=0;savedStatus=null;timeOffset=0;enteredFullscreen=false;hasStarted=false;
    if(document.fullscreenElement===container)document.exitFullscreen().catch(()=>{});
    container.remove();
    document.dispatchEvent(new CustomEvent('willie:watch-updated'));
  }

  async function start(mediaId, title, options={}) {
    if(!Number.isInteger(Number(mediaId))||Number(mediaId)<=0)return;
    const id=Number(mediaId);
    if(current)close();
    // The edge Worker must never serve video, even if its HTML API works.
    if(location.hostname.endsWith('.workers.dev')){
      try {
        const response=await fetch('/api/remote/settings',{cache:'no-store'});
        const data=await response.json();
        const address=String(data.public_ip||'');
        const parts=address.split('.').map(Number);
        if(parts.length!==4 || parts.some(x=>!Number.isInteger(x)||x<0||x>255))throw Error('Remote origin missing');
        const host=parts.join('-')+'.sslip.io';
        location.href='https://'+host+'/watch/'+id;
      }catch(_){
        alert('Open One-Eyed Willie through its direct HTTPS server address or home network to play video. The Cloudflare Worker cannot stream media.');
      }
      return;
    }
    const surface=document.createElement('div');surface.className='willie-player';
    surface.setAttribute('role','dialog');surface.setAttribute('aria-label','Media player');
    const video=document.createElement('video');video.className='willie-video';
    video.controls=true;video.autoplay=true;video.playsInline=true;
    video.preload='metadata';
    const controls=document.createElement('div');controls.className='willie-controls';
    const back=document.createElement('button');back.type='button';back.textContent='← Back';
    back.setAttribute('aria-label','Close playback');back.onclick=close;
    const name=document.createElement('span');name.className='willie-title';name.textContent=title||'Now Playing';
    const watched=document.createElement('button');watched.type='button';watched.textContent='Mark watched';
    watched.addEventListener('click',async()=>{
      const next=!savedStatus?.watched;
      try{
        const r=await fetch('/api/watch/'+id+'/watched',{method:'PUT',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({watched:next})});
        if(!r.ok)throw Error('Unable to save watch status');
        savedStatus={...savedStatus,watched:next};
        watched.textContent=next?'Mark unwatched':'Mark watched';
        document.dispatchEvent(new CustomEvent('willie:watch-updated'));
      }catch(_){setMessage('Unable to update watched status');}
    });
    const skip=document.createElement('span');skip.className='willie-compatible-seek';
    skip.hidden=true;
    for(const [label,delta] of [['−30s',-30],['+30s',30]]){
      const control=document.createElement('button');control.type='button';control.textContent=label;
      control.setAttribute('aria-label',delta<0?'Back 30 seconds':'Forward 30 seconds');
      control.onclick=()=>{
        if(!savedStatus||current!==surface)return;
        const duration=Number(savedStatus.duration_seconds)||0;
        const next=Math.max(0,Math.min(duration||1e7,timeOffset+(video.currentTime||0)+delta));
        saveProgress(true);
        timeOffset=next;
        video.src=savedStatus.compatible_url+'?start='+encodeURIComponent(next);
        video.play().catch(()=>setMessage('Press Play to resume'));
      };
      skip.append(control);
    }
    controls.append(back,name,skip,watched);
    const info=document.createElement('p');info.className='willie-info';info.setAttribute('role','status');
    surface.append(video,controls,info);
    document.body.append(surface);
    current=surface;lastMediaId=id;
    // Synchronous call from the click handler, before any awaited fetch.
    try{const promise=surface.requestFullscreen?.();promise?.catch(()=>{});}catch(_){}
    setMessage('Preparing playback…');
    const keyHandler=(event)=>{
      if(event.key==='Escape'&&current===surface&&!document.fullscreenElement)close();
    };
    surface.addEventListener('keydown',keyHandler);
    const onFullscreenChange=()=>{
      if(document.fullscreenElement===surface)enteredFullscreen=true;
      else if(enteredFullscreen&&current===surface&&!options.keepOpen)close();
      if(current!==surface)document.removeEventListener('fullscreenchange',onFullscreenChange);
    };
    document.addEventListener('fullscreenchange',onFullscreenChange);
    video.addEventListener('playing',()=>{hasStarted=true;});
    video.addEventListener('timeupdate',()=>saveProgress());
    video.addEventListener('pause',()=>saveProgress(true));
    video.addEventListener('ended',()=>{saveProgress(true,true);watched.textContent='Mark unwatched';if(savedStatus)savedStatus.watched=true;document.dispatchEvent(new CustomEvent('willie:watch-updated'));});
    video.addEventListener('error',()=>{
      if(savedStatus?.mode==='direct' && !video.dataset.compatTried){
        // A .mp4 filename can still contain HEVC/unsupported audio codecs.
        video.dataset.compatTried='true';
        skip.hidden=false;timeOffset=Math.max(0,video.currentTime||0);
        video.src=savedStatus.compatible_url+
          (timeOffset>5?'?start='+encodeURIComponent(timeOffset):'');
        setMessage('Switching to compatibility playback…');
        video.play().then(()=>setMessage('')).catch(()=>setMessage('Press Play to start'));
      } else {
        setMessage('This file could not be played. Check the media format or server transcoding.');
      }
    });
    try{
      const response=await fetch(statusUrl(id),{cache:'no-store'});
      if(!response.ok)throw Error('Media unavailable');
      savedStatus=await response.json();
      watched.textContent=savedStatus.watched?'Mark unwatched':'Mark watched';
      if(current!==surface)return;
      const isCompat=savedStatus.mode==='compatible';
      skip.hidden=!isCompat;
      video.src=isCompat?savedStatus.compatible_url:savedStatus.stream_url;
      // Native byte-range streams seek normally. A compatible FFmpeg stream
      // can restart at its saved position using the ?start parameter.
      const resume=options.restart?0:(savedStatus.watched?0:Number(savedStatus.position_seconds||0));
      timeOffset=isCompat&&resume>5?resume:0;
      if(isCompat&&resume>5)video.src=savedStatus.compatible_url+'?start='+encodeURIComponent(resume);
      if(!isCompat&&resume>5){
        video.addEventListener('loadedmetadata',()=>{
          if(Number.isFinite(video.duration)&&video.duration>resume+4)video.currentTime=resume;
        },{once:true});
      }
      video.play().then(()=>setMessage('')).catch(()=>{
        setMessage('Press Play to start. Your browser may require a click for video with sound.');
      });
    }catch(e){setMessage(e.message);}
  }
  window.WilliePlayer={open:start,close};
})();
