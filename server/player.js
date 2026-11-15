/* Fullscreen-first native player with HLS compatibility streaming.
 * HLS assets come only from the NUC's protected direct origin.
 * Hls.js 1.7.4 is pinned for MSE browsers; Safari plays HLS natively. */
(() => {
  let current=null, mediaId=0, status=null, hls=null, session=null;
  let started=false, saveAt=0, offset=0, switching=false, playbackMode='direct';
  let monitor=null;
  let chromeTimer=null;
  function revealChrome(){
    if(!current)return;
    current.classList.remove('willie-chrome-hidden');
    clearTimeout(chromeTimer);
    const video=current.querySelector('video');
    if(video&&!video.paused&&!video.ended&&current.querySelector('.willie-subtitle-menu')?.hidden){
      chromeTimer=setTimeout(()=>{
        if(current&&!video.paused&&!video.ended)current.classList.add('willie-chrome-hidden');
      },2200);
    }
  }
  function concealChromeSoon(){
    if(!current)return;
    clearTimeout(chromeTimer);
    const video=current.querySelector('video');
    if(video&&!video.paused&&!video.ended&&current.querySelector('.willie-subtitle-menu')?.hidden){
      chromeTimer=setTimeout(()=>{
        if(current&&!video.paused&&!video.ended)current.classList.add('willie-chrome-hidden');
      },2200);
    }
  }
  let captions=null;
  let captionsSelect=null;
  function syncCaptions(){
    if(captions){captions.remove();captions=null}
    if(!current||!captionsSelect)return;
    const value=captionsSelect.value;
    if(!/^(?:external|embedded)-[0-9]{1,3}$|^downloaded-[1-9][0-9]{0,11}-[a-z]{2,3}(?:-[a-z]{2})?$/.test(value))return;
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
.willie-controls button,.willie-toolbar button{background:transparent;border:0;border-radius:50%;width:46px;height:46px;display:inline-flex;align-items:center;justify-content:center;color:var(--ink,#fff);padding:11px;cursor:pointer}
.willie-controls button:hover,.willie-toolbar button:hover,.willie-controls button:focus-visible,.willie-toolbar button:focus-visible{background:#ffffff2c}
.willie-controls button svg,.willie-toolbar button svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.willie-bottom{position:absolute;bottom:0;left:0;right:0;z-index:5;background:linear-gradient(transparent,#000e 65%);padding:44px 25px 20px;transition:opacity .2s}
.willie-preview-tooltip{position:absolute;bottom:102px;left:50%;transform:translateX(-50%);z-index:9;width:180px;text-align:center;pointer-events:none;background:#090c11ed;border:1px solid #ffffff50;border-radius:9px;padding:6px;box-shadow:0 8px 22px #0009}
.willie-preview-tooltip[hidden]{display:none}
.willie-preview-tooltip img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:5px}
.willie-preview-tooltip span{font-size:12px;color:var(--ink,#fff);font-variant-numeric:tabular-nums}
.willie-toolbar{display:flex;justify-content:space-between;align-items:center}
.willie-group{display:flex;align-items:center;gap:8px}
.willie-subtitle-menu{position:absolute;right:25px;bottom:90px;background:var(--panel,#171b20);border:1px solid var(--line,#535b64);border-radius:12px;padding:15px;display:flex;flex-direction:column;gap:13px;width:min(360px,calc(100vw - 40px))}
.willie-subtitle-menu[hidden]{display:none}
.willie-subtitle-menu a{color:var(--ink,#fff);font-size:14px;text-decoration:none;padding:9px}
.willie-provider-search,.willie-subtitle-result{width:100%;text-align:left;background:transparent;color:var(--ink,#fff);border:0;border-radius:8px;padding:11px 10px;cursor:pointer;font:inherit}
.willie-provider-search:hover,.willie-subtitle-result:hover,.willie-provider-search:focus-visible,.willie-subtitle-result:focus-visible{background:#ffffff25;outline:2px solid var(--accent,#fff)}
.willie-subtitle-results{max-height:35vh;overflow-y:auto;display:flex;flex-direction:column;gap:3px;font-size:13px}
.willie-subtitle-menu{max-height:75vh;overflow-y:auto}
.willie-subtitle-menu .willie-subtitle-select{max-width:none;width:100%}

.willie-subtitle-select{background:#172636e9;border:1px solid #4b6078;border-radius:10px;
color:#fff;padding:10px 12px;font:inherit;max-width:180px;cursor:pointer}
.willie-subtitle-select option{background:#172636;color:#fff}
.willie-subtitle-select[hidden]{display:none}
.willie-title{font-weight:650;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.willie-info{position:absolute;left:50%;bottom:90px;transform:translateX(-50%);
background:#172637ec;color:#e8f3ff;border:1px solid #324c66;border-radius:12px;
max-width:85vw;padding:13px 19px;text-align:center;z-index:6}
.willie-info:empty{display:none}
.willie-player.willie-chrome-hidden{cursor:none}
.willie-player.willie-chrome-hidden .willie-controls,
.willie-player.willie-chrome-hidden .willie-bottom{opacity:0;pointer-events:none}
.willie-player .willie-timeline{transition:opacity .2s ease}
.willie-player .willie-info:not(:empty){opacity:1}
.willie-player:not(.willie-chrome-hidden) .willie-controls{opacity:1}
.willie-player:not(.willie-chrome-hidden) .willie-bottom{opacity:1}
@media(prefers-reduced-motion:reduce){.willie-controls,.willie-bottom{transition:none}}
.willie-next-prompt{position:absolute;bottom:110px;right:24px;z-index:7;background:#102137f5;border:1px solid #47627f;border-radius:13px;padding:18px;max-width:min(380px,calc(100vw - 48px));color:#fff;box-shadow:0 14px 48px #000a}
.willie-next-prompt[hidden]{display:none}
.willie-next-prompt p{margin:0 0 12px;line-height:1.4}
.willie-next-actions{display:flex;gap:10px;justify-content:flex-end}
.willie-next-actions button{border:1px solid #6685a4;border-radius:8px;padding:9px 14px;background:#1e3955;color:#fff;cursor:pointer;font:inherit}
.willie-next-actions button:focus-visible{outline:2px solid #fff}
.willie-timeline{display:flex;
align-items:center;gap:12px;padding:10px 15px;z-index:5}
.willie-timeline input{flex:1;accent-color:var(--accent,#e5e0d5);cursor:pointer}
.willie-timeline span{font-size:12px;color:#bccddd;font-variant-numeric:tabular-nums}
@media(hover:none){.willie-controls,.willie-bottom{opacity:1}}
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
    node.dispatchEvent(new Event('willie:closing'));
    saveProgress(true);
    clearInterval(monitor);monitor=null;
    clearTimeout(chromeTimer);chromeTimer=null;
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
      surface.dataset.engine=ready.engine||'Unknown';
      video.play().then(()=>message('')).catch(()=>message('Press Play to start the video.'));
    }catch(error){if(current===surface)message(error.message)}
    finally{switching=false}
  }
  const icons={
    back:'<path d="m15 18-6-6 6-6"/><path d="M9 12h12"/>',
    rewind:'<path d="M11 19 2 12l9-7v14ZM22 19l-9-7 9-7v14Z"/>',
    forward:'<path d="m13 19 9-7-9-7v14ZM2 19l9-7-9-7v14Z"/>',
    subtitle:'<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 12h5m-5 4h4m4-4h4m-5 4h5"/>',
    watched:'<path d="M20 6 9 17l-5-5"/>',
    play:'<path d="m8 5 12 7-12 7z"/>',
    pause:'<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6m0-10h.01"/>',
    next:'<path d="m5 5 11 7-11 7z"/><path d="M19 5v14"/>',
    autoplay:'<path d="m5 5 11 7-11 7z"/><path d="M19 5v14"/><path d="M4 2h16"/>'
  };
  function setIcon(button,icon,label){
    button.setAttribute('aria-label',label);button.title=label;
    button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[icon]+'</svg>';
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
    video.controls=false;video.autoplay=true;video.playsInline=true;video.preload='metadata';
    const controls=document.createElement('div');controls.className='willie-controls';
    const back=document.createElement('button');back.type='button';setIcon(back,'back','Back to library');back.onclick=close;
    const name=document.createElement('span');name.className='willie-title';name.textContent=title||'Now playing';
    const backward=document.createElement('button');setIcon(backward,'rewind','Rewind 10 seconds');
    const forward=document.createElement('button');setIcon(forward,'forward','Forward 10 seconds');
    const cc=document.createElement('select');cc.className='willie-subtitle-select';
    cc.setAttribute('aria-label','Subtitles');cc.title='Subtitles';
    cc.hidden=false;
    const off=document.createElement('option');off.value='';off.textContent='CC Off';cc.append(off);
    cc.onchange=()=>{syncCaptions();subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false');revealChrome();concealChromeSoon()};
    const watch=document.createElement('button');setIcon(watch,'watched','Mark watched');watch.setAttribute('aria-pressed','false');
    watch.onclick=async()=>{
      try{
        const value=!status.watched;
        await requestJson('/api/watch/'+id+'/watched',{method:'PUT',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({watched:value})});
        status.watched=value;watch.setAttribute('aria-pressed',String(value));watch.title=value?'Mark unwatched':'Mark watched';watch.setAttribute('aria-label',watch.title);
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
    const subtitles=document.createElement('button');setIcon(subtitles,'subtitle','Subtitles');
    subtitles.setAttribute('aria-expanded','false');
    const subtitleMenu=document.createElement('div');subtitleMenu.className='willie-subtitle-menu';subtitleMenu.hidden=true;
    const language=document.createElement('select');language.className='willie-subtitle-select';
    language.setAttribute('aria-label','Subtitle search language');
    for(const [code,label] of [['en','English'],['es','Spanish'],['fr','French'],['de','German'],['it','Italian'],['pt','Portuguese'],['ja','Japanese'],['ko','Korean']]){
      const option=document.createElement('option');option.value=code;option.textContent=label;language.append(option);
    }
    const searchLink=document.createElement('button');searchLink.type='button';
    searchLink.className='willie-provider-search';searchLink.textContent='Search subtitles';
    const results=document.createElement('div');results.className='willie-subtitle-results';
    results.setAttribute('aria-live','polite');
    const reloadTracks=async(selected)=>{
      const info=await requestJson('/api/stream/subtitles/'+id);
      cc.replaceChildren(off);
      for(const item of info.tracks||[]){
        if(!/^(?:external|embedded)-[0-9]{1,3}$|^downloaded-[1-9][0-9]{0,11}-[a-z]{2,3}(?:-[a-z]{2})?$/.test(item.id))continue;
        const option=document.createElement('option');option.value=item.id;
        option.textContent=String(item.label||'Subtitles').slice(0,80);cc.append(option);
      }
      if(selected){cc.value=selected;syncCaptions();}
    };
    searchLink.onclick=async()=>{
      results.replaceChildren();results.textContent='Searching OpenSubtitles…';
      searchLink.disabled=true;
      try{
        const data=await requestJson('/api/stream/subtitles/'+id+'/search?language='+encodeURIComponent(language.value));
        results.replaceChildren();
        if(!data.results?.length){results.textContent='No subtitle matches found.';return;}
        for(const item of data.results){
          const choice=document.createElement('button');choice.type='button';choice.className='willie-subtitle-result';
          choice.textContent=item.release+' · '+item.language+(item.hearing_impaired?' · SDH':'');
          choice.onclick=async()=>{
            choice.disabled=true;choice.textContent='Downloading subtitle…';
            try{
              const result=await requestJson('/api/stream/subtitles/'+id+'/download?language='+encodeURIComponent(language.value),{
                method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:item.file_id})
              });
              await reloadTracks(result.track_id);
              subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false');
              message('Subtitle downloaded and enabled.');revealChrome();concealChromeSoon();
            }catch(error){choice.textContent=error.message;choice.disabled=false;}
          };
          results.append(choice);
        }
      }catch(error){results.textContent=error.message;}
      finally{searchLink.disabled=false;}
    };
    subtitleMenu.append(cc,language,searchLink,results);
    subtitles.onclick=()=>{subtitleMenu.hidden=!subtitleMenu.hidden;subtitles.setAttribute('aria-expanded',String(!subtitleMenu.hidden));if(!subtitleMenu.hidden)cc.focus()};
    const playPause=document.createElement('button');setIcon(playPause,'pause','Pause');
    playPause.onclick=()=>video.paused?video.play().catch(()=>{}):video.pause();
    let nextEpisode=null;
    let countdownTimer=null;
    let autoPlayNext=false;
    const next=document.createElement('button');setIcon(next,'next','Play next episode');next.hidden=true;
    function stopCountdown(){if(countdownTimer!==null){clearInterval(countdownTimer);countdownTimer=null}}
    function launchNext(){
      stopCountdown();
      if(!nextEpisode||current!==surface)return;
      const chosen=nextEpisode;
      start(chosen.media_id,chosen.title,{restart:true});
    }
    next.onclick=launchNext;
    const nextPrompt=document.createElement('div');nextPrompt.className='willie-next-prompt';nextPrompt.hidden=true;
    nextPrompt.setAttribute('role','group');nextPrompt.setAttribute('aria-label','Play next episode');
    const nextLabel=document.createElement('p');
    const nextActions=document.createElement('div');nextActions.className='willie-next-actions';
    const cancelNext=document.createElement('button');cancelNext.type='button';cancelNext.textContent='Cancel';cancelNext.onclick=()=>{stopCountdown();nextPrompt.hidden=true};
    const playNext=document.createElement('button');playNext.type='button';playNext.textContent='Play Next';playNext.onclick=launchNext;
    nextActions.append(cancelNext,playNext);nextPrompt.append(nextLabel,nextActions);
    function showNextCountdown(){
      if(!autoPlayNext||!nextEpisode||current!==surface)return;
      stopCountdown();nextPrompt.hidden=false;surface.classList.remove('willie-chrome-hidden');
      let remaining=8;
      nextLabel.textContent='Up next: '+nextEpisode.title+' · Playing in '+remaining+' seconds';
      playNext.focus({preventScroll:true});
      countdownTimer=setInterval(()=>{
        if(current!==surface){stopCountdown();return}
        remaining--;
        if(remaining<=0){launchNext();return}
        nextLabel.textContent='Up next: '+nextEpisode.title+' · Playing in '+remaining+' seconds';
      },1000);
    }
    const diagnostics=document.createElement('button');setIcon(diagnostics,'info','Playback diagnostics');
    diagnostics.onclick=()=>message((playbackMode==='direct'?'Direct Play — browser decoding':'HLS transcoding')+
      ' · Server: '+(surface.dataset.engine||'Not reported')+
      ' · Video: '+(video.videoWidth||'?')+'×'+(video.videoHeight||'?')+
      ' · Client GPU decoding depends on browser, device and codec.');
    controls.append(back,name);
    const bottom=document.createElement('div');bottom.className='willie-bottom';
    const toolbar=document.createElement('div');toolbar.className='willie-toolbar';
    const left=document.createElement('div');left.className='willie-group';
    const right=document.createElement('div');right.className='willie-group';
    left.append(playPause,backward,forward);right.append(next,subtitles,watch,diagnostics);
    toolbar.append(left,right);bottom.append(toolbar,subtitleMenu);
    const info=document.createElement('div');info.className='willie-info';info.setAttribute('role','status');
    const timeline=document.createElement('div');timeline.className='willie-timeline';
    const elapsed=document.createElement('span');elapsed.textContent='0:00:00';
    const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='1000';slider.value='0';
    slider.setAttribute('aria-label','Playback position');
    const total=document.createElement('span');total.textContent='0:00:00';
    const preview=document.createElement('div');preview.className='willie-preview-tooltip';preview.hidden=true;
    const previewImage=document.createElement('img');previewImage.alt='Video preview thumbnail';
    const previewTime=document.createElement('span');preview.append(previewImage,previewTime);
    let previewImages=[];
    const previewAt=fraction=>{
      if(!previewImages.length)return;
      const index=Math.max(0,Math.min(previewImages.length-1,Math.floor(fraction*previewImages.length)));
      previewImage.src=previewImages[index];
      const duration=Number(status?.duration_seconds)||video.duration;
      previewTime.textContent=Number.isFinite(duration)?formatTime(duration*fraction):'';
      preview.hidden=false;
    };
    slider.addEventListener('input',()=>previewAt(Math.max(0,Math.min(1,Number(slider.value)/1000))));
    slider.addEventListener('pointermove',event=>{
      const rect=slider.getBoundingClientRect();
      if(rect.width>0)previewAt(Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)));
    });
    for(const eventName of ['pointerleave','blur','change'])slider.addEventListener(eventName,()=>{preview.hidden=true});
    requestJson('/api/maintenance/preview/'+id).then(data=>{
      if(current===surface&&data.enabled&&Array.isArray(data.images))previewImages=data.images.filter(url=>/^\/api\/maintenance\/preview\/\d+\/00[0-5]\.jpg$/.test(url));
    }).catch(()=>{});
    timeline.append(preview);
    timeline.append(elapsed,slider,total);
    bottom.prepend(timeline);surface.append(video,controls,info,bottom,nextPrompt);
    document.body.append(surface);current=surface;mediaId=id;started=false;offset=0;captionsSelect=cc;
    surface.addEventListener('pointermove',()=>{revealChrome();concealChromeSoon()});
    surface.addEventListener('willie:closing',stopCountdown);
    surface.addEventListener('pointerdown',revealChrome);
    surface.addEventListener('focusin',revealChrome);
    surface.addEventListener('focusout',concealChromeSoon);
    video.addEventListener('click',()=>{
      if(video.paused)video.play().catch(()=>{});
      else video.pause();
      revealChrome();concealChromeSoon();
    });
    // Must be synchronous with user's Play click for fullscreen permission.
    try{surface.requestFullscreen?.().catch(()=>{})}catch(_){}
    let entered=false;
    const fullscreenChanged=()=>{
      if(document.fullscreenElement===surface)entered=true;
      else if(entered&&current===surface)close();
      if(current!==surface)document.removeEventListener('fullscreenchange',fullscreenChanged);
    };
    document.addEventListener('fullscreenchange',fullscreenChanged);
    surface.addEventListener('keydown',e=>{
      if(e.key==='Escape'||e.key==='Backspace'){
        if(!subtitleMenu.hidden){subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false')}
        else if(!document.fullscreenElement)close();
        e.preventDefault();
      }else if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&e.target!==slider&&e.target!==cc){
        seekBy(e.key==='ArrowLeft'?-10:10);e.preventDefault();
      }
    });
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
    video.addEventListener('playing',()=>{started=true;setIcon(playPause,'pause','Pause');message('');concealChromeSoon()});
    video.addEventListener('pause',()=>{setIcon(playPause,'play','Play');revealChrome()});
    video.addEventListener('timeupdate',()=>saveProgress());
    video.addEventListener('pause',()=>saveProgress(true));
    video.addEventListener('ended',()=>{saveProgress(true,true);if(status)status.watched=true;
      watch.setAttribute('aria-pressed','true');watch.title='Mark unwatched';watch.setAttribute('aria-label',watch.title);
      document.dispatchEvent(new CustomEvent('willie:watch-updated'));showNextCountdown()});
    video.addEventListener('error',()=>{
      if(playbackMode==='direct')playHls(playerPosition(video));
      else message('Unable to decode HLS stream. Check FFmpeg and media format.');
    });
    message('Opening video…');
    requestJson('/api/watch/'+id+'/status').then(data=>{
      if(current!==surface)return;
      status=data;watch.setAttribute('aria-pressed',String(data.watched));watch.title=data.watched?'Mark unwatched':'Mark watched';watch.setAttribute('aria-label',watch.title);
      // Server-wide saved setting; no per-playback toggle required.
      requestJson('/api/settings/playback').then(prefs=>{
        if(current!==surface)return;
        autoPlayNext=!!prefs.auto_play_next;
        if(video.ended)showNextCountdown();
      }).catch(()=>{autoPlayNext=false});
      reloadTracks().catch(()=>{});
      requestJson('/api/tv/next?media_id='+id).then(result=>{
        if(current!==surface)return;
        nextEpisode=result.next||null;
        next.hidden=!nextEpisode;
        // If status/next results race with a very short clip, still offer next.
        if(video.ended)showNextCountdown();
      }).catch(()=>{next.hidden=true});
      const resume=options.restart||data.watched?0:Number(data.position_seconds)||0;
      if(data.mode==='direct'){
        playbackMode='direct';surface.dataset.engine='Browser';video.src=data.stream_url;
        if(resume>5)video.addEventListener('loadedmetadata',()=>{
          if(Number.isFinite(video.duration)&&resume<video.duration-4)video.currentTime=resume;
        },{once:true});
        video.play().catch(()=>message('Press Play to start.'));
      }else playHls(resume);
    }).catch(e=>message(e.message));
  }
  window.WilliePlayer={open:start,close};
})();
