/* Fullscreen-first native player with HLS compatibility streaming.
 * HLS assets come only from the NUC's protected direct origin.
 * Hls.js 1.7.4 is pinned for MSE browsers; Safari plays HLS natively. */
(() => {
  let current=null, mediaId=0, status=null, hls=null, session=null;
  let seasonShuffle=false, shuffleQueue=[];
  let started=false, saveAt=0, offset=0, switching=false, playbackMode='direct';
  let monitor=null;
  let chromeTimer=null, seekTimer=null, stallTimer=null;
  let queuedSeek=null, recoveryAttempts=0, lastRecovery=0, recoveryHandler=null;
  // Playback quality: 'auto' plays the original when the browser can, otherwise
  // transcodes at the default size; the others always transcode at that size.
  const QUALITIES=[['auto','Best available'],['full','Full quality'],['1080p','1080p'],['720p','720p'],['480p','480p'],['360p','360p'],['240p','240p']];
  const BUDGETS=[[250e6,'250 MB'],[500e6,'500 MB'],[1e9,'1 GB'],[2e9,'2 GB'],[5e9,'5 GB']];
  function hasChosenQuality(){try{return localStorage.getItem('willie:quality')!==null}catch(_){return false}}
  /* Metered connections: ask before spending data. Chrome on Android reports
   * the connection type; "Data Saver" is honoured everywhere it is exposed. */
  function onMeteredConnection(){
    const connection=navigator.connection||navigator.mozConnection||navigator.webkitConnection;
    return !!connection&&(connection.type==='cellular'||connection.saveData===true);
  }
  function formatData(bytes){
    if(!(bytes>0))return '—';
    if(bytes>=1e9)return (bytes/1e9).toFixed(bytes>=1e10?0:1)+' GB';
    return Math.max(1,Math.round(bytes/1e6))+' MB';
  }
  function formatSpan(seconds){
    const total=Math.max(0,Math.round(seconds)),h=Math.floor(total/3600),m=Math.floor(total%3600/60);
    return h?h+'h '+String(m).padStart(2,'0')+'m':Math.max(1,m)+'m';
  }
  /* Data cost of each choice for the part of the video still to watch, best
   * quality first. "Original" streams the file as-is (its size is exact);
   * transcodes come from the server's per-tier estimates. */
  function planDataUse(estimates,position,canDirect){
    const duration=Number(estimates?.duration_seconds)||0;
    if(!duration)return [];
    const left=Math.max(0,Math.min(1,(duration-position)/duration));
    const original=Number(estimates.original?.bytes)||0;
    const rows=[];
    if(canDirect&&original)rows.push({id:'auto',name:'Original quality',kind:'exact',bytes:original*left,
      perHour:original*3600/duration});
    if(!canDirect&&estimates.full?.available&&estimates.full.bytes>0)
      rows.push({id:'full',name:'Full quality (original video)',kind:'about',
        bytes:estimates.full.bytes*left,perHour:estimates.full.bytes*3600/duration});
    for(const tier of estimates.qualities||[]){
      // A re-encode never needs more than the file it came from.
      const whole=tier.kind==='up_to'&&original?Math.min(tier.bytes,original):tier.bytes;
      rows.push({id:tier.id,name:tier.id,kind:tier.kind,bytes:whole*left,perHour:whole*3600/duration});
    }
    return rows;
  }
  /* Best quality that fits [budget] bytes; falls back to the cheapest tier. */
  function pickForBudget(rows,budget){
    const fit=rows.find(row=>row.bytes<=budget);
    return fit?{row:fit,fits:true}:{row:rows[rows.length-1],fits:false};
  }
  function savedQuality(){
    try{const value=localStorage.getItem('willie:quality');return QUALITIES.some(q=>q[0]===value)?value:'auto'}
    catch(_){return 'auto'}
  }
  // What "Best available" becomes when the original file cannot be played as-is:
  // the untouched video when the server can pass it through, else a 720p transcode.
  let autoTier='720p';
  let quality=savedQuality(), directRetries=0, hlsRecover={network:0,media:0}, hlsRecoverAt=0;
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
  // Browser WebVTT cues should not inherit a permanent black caption box.
  // Users can opt back into a translucent/opaque background in Settings.
  const cueStyle=document.createElement('style');
  cueStyle.id='willie-subtitle-appearance';
  document.head.append(cueStyle);
  function applySubtitleStyle(input={}){
    const allowedBg=new Set(['none','25','50','75','100']);
    const bg=allowedBg.has(input.background)?input.background:'none';
    const alpha=bg==='none'?0:Number(bg)/100;
    const size=({small:'85%',normal:'100%',large:'125%'})[input.size]||'100%';
    const color=input.color==='yellow'?'#ffff00':'#ffffff';
    const shadow=input.outline===false?'none':
      '-1px -1px 1px #000,1px -1px 1px #000,-1px 1px 1px #000,1px 1px 1px #000';
    cueStyle.textContent=
      '.willie-video::cue{background-color:rgba(0,0,0,'+alpha+
      ')!important;color:'+color+'!important;font-size:'+size+
      '!important;text-shadow:'+shadow+'!important}';
  }
  applySubtitleStyle();
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
.willie-controls button:hover,.willie-toolbar button:hover,.willie-controls button:focus-visible,.willie-toolbar button:focus-visible{background:#ffffff1c;color:var(--oew-tv-select-color,#8B5CF6)}
.willie-player button:focus-visible{outline:2px solid var(--oew-tv-select-color,#8B5CF6);outline-offset:2px}
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
.willie-data-menu{gap:6px}
.willie-data-heading{font-size:13px;color:#bccddd;padding:2px 4px 8px;line-height:1.4}
.willie-data-row{display:flex;justify-content:space-between;align-items:center;gap:14px;width:100%;text-align:left;background:transparent;color:var(--ink,#fff);border:1px solid transparent;border-radius:9px;padding:11px 12px;cursor:pointer;font:inherit}
.willie-data-row:hover,.willie-data-row:focus-visible{background:#ffffff25}
.willie-data-row[aria-pressed="true"]{border-color:var(--oew-tv-select-color,#8B5CF6);background:#ffffff14}
.willie-data-cost{font-variant-numeric:tabular-nums;color:#d6e2ee;white-space:nowrap}
.willie-data-note{font-size:12px;color:#9fb2c6;padding:4px;line-height:1.4}
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
.willie-timeline input{flex:1;accent-color:var(--oew-tv-select-color,#8B5CF6);cursor:pointer}
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
    const time=Number(video?.currentTime);
    const base=playbackMode==='hls'?offset:0;
    const result=base+(Number.isFinite(time)&&time>=0?time:0);
    return Number.isFinite(result)?Math.max(0,result):0;
  }
  // Do not infer playback support from .mp4/.mkv alone. FFprobe provides
  // actual stream codecs and the browser reports formats it can decode.
  function browserCanDirect(video, info) {
    const media=info?.media;
    if(!media?.video_codec)return info?.mode==='direct';
    const ext=String(media.container||'').toLowerCase();
    const types={mp4:'video/mp4',m4v:'video/mp4',mov:'video/mp4',
      webm:'video/webm',ogv:'video/ogg'};
    const mime=types[ext];
    if(!mime)return false;
    const videos={h264:'avc1.42E01E',hevc:'hvc1',vp9:'vp09.00.10.08',
      vp8:'vp8',av1:'av01.0.05M.08',theora:'theora'};
    const audios={aac:'mp4a.40.2',mp3:'mp3',ac3:'ac-3',eac3:'ec-3',
      opus:'opus',vorbis:'vorbis'};
    const vc=videos[media.video_codec],ac=media.audio_codec?audios[media.audio_codec]:null;
    if(!vc||(media.audio_codec&&!ac))return false;
    // Reject unexpected codec/container combinations before testing a MIME.
    if(mime==='video/webm'&&!['vp8','vp9','av1'].includes(media.video_codec))return false;
    if(mime==='video/mp4'&&!['h264','hevc','av1','vp9'].includes(media.video_codec))return false;
    const codecs=vc+(ac?', '+ac:'');
    return !!video.canPlayType(mime+'; codecs="'+codecs+'"');
  }
  function destroyStream(){
    if(hls){hls.destroy();hls=null}
    const old=session;session=null;
    if(old)fetch('/api/stream/hls/'+old,{method:'DELETE',keepalive:true}).catch(()=>{});
  }
  let progressWrite=Promise.resolve();
  function progressSnapshot(done=false){
    if(!current||!started||!mediaId)return null;
    const video=current.querySelector('video');
    const position=playerPosition(video);
    if(position<1&&!done)return null;
    // Native HLS and fragmented MP4 often expose an infinite timeline.
    const reported=Number(status?.duration_seconds);
    const timeline=Number(video.duration);
    const duration=Number.isFinite(reported)&&reported>0?reported:
      Number.isFinite(timeline)&&timeline>0?timeline:0;
    return {
      media_id:mediaId,duration_seconds:duration,
      position_seconds:duration>0?Math.min(duration,position):position,
      completed:done||Boolean(status?.watched)||(duration>0&&position>=duration*.95)
    };
  }
  function saveProgress(force=false,done=false){
    const payload=progressSnapshot(done);
    if(!payload)return progressWrite;
    const timestamp=Date.now();
    if(!force&&timestamp-saveAt<12000)return progressWrite;
    saveAt=timestamp;
    // Serialize saves. A delayed heartbeat must never arrive after a final
    // completed/paused position and overwrite it with older information.
    progressWrite=progressWrite.catch(()=>{}).then(async()=>{
      try{
        await requestJson('/api/playback/progress',{
          method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(payload),keepalive:force
        });
      }catch(error){
        saveAt=0;
        console.warn('Could not save playback progress:',error);
        if(current&&!current.querySelector('video')?.ended)
          message('Playback progress could not be saved: '+error.message);
      }
    });
    return progressWrite;
  }
  function onVisibilityChange(){
    if(document.visibilityState==='hidden')saveProgress(true);
  }
  function onPageHide(){
    // Beacon is not canceled when a viewer navigates away or closes a tab.
    const payload=progressSnapshot();
    if(payload&&navigator.sendBeacon){
      try{
        const json=new Blob([JSON.stringify(payload)],{type:'application/json'});
        if(navigator.sendBeacon('/api/playback/progress',json))return;
      }catch(_){}
    }
    saveProgress(true);
  }
  function close(){
    if(!current)return;
    const node=current,video=node.querySelector('video');
    node.dispatchEvent(new Event('willie:closing'));
    const finalSave=saveProgress(true);
    document.removeEventListener('visibilitychange',onVisibilityChange);
    window.removeEventListener('pagehide',onPageHide);
    clearInterval(monitor);monitor=null;
    clearTimeout(chromeTimer);chromeTimer=null;
    clearTimeout(seekTimer);seekTimer=null;queuedSeek=null;
    clearTimeout(stallTimer);stallTimer=null;recoveryAttempts=0;recoveryHandler=null;
    video.pause();destroyStream();
    video.removeAttribute('src');video.load();
    current=null;mediaId=0;status=null;started=false;offset=0;switching=false;captions=null;captionsSelect=null;
    if(document.fullscreenElement===node)document.exitFullscreen().catch(()=>{});
    node.remove();
    // Reload Continue Watching only after the final PUT has been processed.
    Promise.resolve(finalSave).finally(()=>{
      document.dispatchEvent(new CustomEvent('willie:watch-updated'));
    });
  }
  function injectScript(src){
    return new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      script.src=src;script.async=true;
      script.onload=()=>window.Hls?resolve(window.Hls):reject(Error('HLS support unavailable'));
      script.onerror=()=>{script.remove();reject(Error('HLS script failed to load'))};
      document.head.append(script);
    });
  }
  /* Prefer the copy served by this server so playback works without internet
   * access; the public CDN is only a fallback. A failure is not cached. */
  async function loadHlsLibrary(){
    if(window.Hls)return window.Hls;
    if(!window.__willieHlsPromise){
      window.__willieHlsPromise=injectScript('/assets/vendor/hls-1.7.4.min.js')
        .catch(()=>injectScript('https://cdn.jsdelivr.net/npm/hls.js@1.7.4/dist/hls.min.js'))
        .catch(()=>{window.__willieHlsPromise=null;throw Error('HLS player could not load. Check the server and your connection.')});
    }
    return window.__willieHlsPromise;
  }
  async function playHls(startSeconds){
    if(!current||switching)return;
    switching=true;
    clearTimeout(stallTimer);stallTimer=null;
    const surface=current,video=surface.querySelector('video');
    const seek=Math.max(0,Math.min(Number(status?.duration_seconds)||1e7,startSeconds));
    await saveProgress(true);
    started=false;
    destroyStream();video.pause();video.removeAttribute('src');video.load();
    offset=seek;playbackMode='hls';hlsRecover={network:0,media:0};
    syncCaptions();
    message('Preparing compatible HLS stream…');
    try{
      const startUrl=tier=>'/api/stream/hls/start/'+mediaId+'?start='+encodeURIComponent(seek)+
        '&quality='+encodeURIComponent(tier);
      let result;
      try{result=await requestJson(startUrl(quality==='auto'?autoTier:quality),{method:'POST'})}
      catch(error){
        // A saved "Full quality" choice may not suit this particular video.
        if(quality!=='full'||!/^Full quality is not available/.test(error.message))throw error;
        message(error.message.replace('Full quality is not available for this file. ','Full quality is not available: ')+' Using 720p.');
        result=await requestJson(startUrl('720p'),{method:'POST'});
      }
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
      // Chromium (Chrome, Edge, Opera, Android) now claims native HLS support, but its
      // built-in demuxer rejects these streams (DEMUXER_ERROR_COULD_NOT_PARSE).
      // hls.js is the reliable path wherever Media Source is available; Safari
      // and iOS keep their own, mature native HLS.
      const chromium=/Chrom(?:e|ium)\//.test(navigator.userAgent)&&!!window.MediaSource;
      if(!chromium&&video.canPlayType('application/vnd.apple.mpegurl')){
        // EVENT playlists are seekable from the beginning; Safari may otherwise
        // jump to the currently advertised live edge.
        video.addEventListener('loadedmetadata',()=>{
          if(current===surface&&playbackMode==='hls')video.currentTime=0;
        },{once:true});
        video.src=url;
      }else{
        const Hls=await loadHlsLibrary();
        if(!Hls.isSupported())throw Error('This browser does not support HLS playback.');
        hls=new Hls({lowLatencyMode:false,maxBufferLength:30,liveSyncDurationCount:3,startPosition:0});
        hls.on(Hls.Events.ERROR,(_event,data)=>{
          if(!data.fatal)return;
          hlsRecoverAt=Date.now();
          // Recover in place first: a dropped request or a bad segment should not
          // throw away the transcode. An expired session (404) cannot be resumed.
          if(data.type===Hls.ErrorTypes.NETWORK_ERROR&&data.response?.code!==404&&hlsRecover.network<3){
            hlsRecover.network++;message('Connection hiccup. Retrying…');hls.startLoad();return;
          }
          if(data.type===Hls.ErrorTypes.MEDIA_ERROR&&hlsRecover.media<2){
            hlsRecover.media++;message('Recovering playback…');hls.recoverMediaError();return;
          }
          message('Recovering HLS stream: '+(data.details||data.type));
          recoveryHandler?.();
        });
        hls.loadSource(url);
        hls.attachMedia(video);
      }
      surface.dataset.engine=ready.engine||'Unknown';
      video.play().then(()=>message('')).catch(()=>message('Press Play to start the video.'));
    }catch(error){if(current===surface)message(error.message)}
    finally{switching=false}
  }
  /* Switch from a transcode back to the original file at [position]. */
  async function playDirect(position){
    if(!current||switching||!status)return;
    switching=true;
    try{
      const surface=current,video=surface.querySelector('video');
      await saveProgress(true);
      started=false;destroyStream();video.pause();
      playbackMode='direct';offset=0;directRetries=0;surface.dataset.engine='Browser';
      syncCaptions();message('Switching to original quality…');
      video.addEventListener('loadedmetadata',()=>{
        if(current===surface&&Number.isFinite(video.duration)&&position>1&&position<video.duration-4)
          video.currentTime=position;
      },{once:true});
      video.src=status.stream_url;
      video.play().then(()=>message('')).catch(()=>message('Press Play to start.'));
    }finally{switching=false}
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
    quality:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    autoplay:'<path d="m5 5 11 7-11 7z"/><path d="M19 5v14"/><path d="M4 2h16"/>'
  };
  function setIcon(button,icon,label){
    button.setAttribute('aria-label',label);button.title=label;
    button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[icon]+'</svg>';
  }
  function start(media, title, options={}){
    window.WillieThemeMusic?.stop(true);
    const id=Number(media);
    if(!Number.isInteger(id)||id<=0)return;
    if(current)close();
    // Explicit playback (unlike refreshes/checkpoints) restores dismissed
    // Continue Watching titles for this movie or television series.
    fetch('/api/home/continue/'+id+'/start',{method:'POST'}).catch(()=>{});
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
    document.addEventListener('visibilitychange',onVisibilityChange);
    window.addEventListener('pagehide',onPageHide);
    const surface=document.createElement('div');surface.className='willie-player';
    requestJson('/api/settings/tv-appearance').then(settings=>{
      if(current!==surface)return;
      const color=settings.selection_color;
      if(/^#[0-9A-Fa-f]{6}$/.test(color||''))
        surface.style.setProperty('--oew-tv-select-color',color);
    }).catch(()=>{});
    surface.setAttribute('role','dialog');surface.setAttribute('aria-label','Media player');
    surface.tabIndex=0;
    requestJson('/api/settings/subtitle-appearance')
      .then(pref=>{if(current===surface)applySubtitleStyle(pref)})
      .catch(()=>{});
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
    function recoverStream(){
      if(current!==surface||switching||video.paused)return;
      const now=Date.now();
      if(now-lastRecovery>60000)recoveryAttempts=0;
      if(recoveryAttempts>=2){
        message('Playback stalled. Please retry playback or check the server logs.');
        return;
      }
      recoveryAttempts++;lastRecovery=now;
      queueSeek(playerPosition(video),true);
    }
    recoveryHandler=recoverStream;
    function queueSeek(seconds,forceRestart=false){
      if(!status)return;
      const duration=Number(status.duration_seconds)||1e7;
      const target=Math.max(0,Math.min(duration,seconds));
      queuedSeek=target;
      clearTimeout(seekTimer);
      seekTimer=setTimeout(()=>{
        if(current!==surface)return;
        if(switching){queueSeek(queuedSeek,forceRestart);return;}
        const desired=queuedSeek;queuedSeek=null;
        if(playbackMode!=='hls'){
          video.currentTime=desired;
          return;
        }
        const relative=desired-offset;
        if(!forceRestart&&relative>=0){
          for(let n=0;n<video.seekable.length;n++){
            if(relative>=video.seekable.start(n)&&relative<video.seekable.end(n)-0.25){
              video.currentTime=relative;
              return;
            }
          }
        }
        playHls(desired);
      },200);
    }
    const seekBy=delta=>{
      if(!status)return;
      const currentTarget=queuedSeek??playerPosition(video);
      queueSeek(currentTarget+delta);
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
    const qualityButton=document.createElement('button');setIcon(qualityButton,'quality','Data use and quality');
    qualityButton.setAttribute('aria-expanded','false');
    const qualityMenu=document.createElement('div');qualityMenu.className='willie-subtitle-menu willie-data-menu';qualityMenu.hidden=true;
    let estimates=null,pendingStart=null;
    const estimatesReady=requestJson('/api/stream/hls/estimates/'+id).then(data=>{estimates=data;return data}).catch(()=>null);
    const resolveAutoTier=()=>{autoTier=estimates?.full?.available?'full':'720p'};
    function chooseQuality(choice){
      quality=choice;resolveAutoTier();
      try{localStorage.setItem('willie:quality',quality)}catch(_){}
      qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false');
      if(pendingStart){const begin=pendingStart;pendingStart=null;begin();return}
      if(!status)return;
      const at=playerPosition(video);
      if(quality==='auto'&&browserCanDirect(video,status))playDirect(at);
      else playHls(at);
      revealChrome();concealChromeSoon();
    }
    function renderDataMenu(){
      qualityMenu.textContent='';
      const heading=document.createElement('div');heading.className='willie-data-heading';
      const duration=Number(estimates?.duration_seconds)||Number(status?.duration_seconds)||0;
      const at=started?playerPosition(video):Number(status?.position_seconds)||0;
      const canDirect=!!status&&browserCanDirect(video,status);
      if(pendingStart){
        heading.textContent='You are on mobile data. Choose how much to use — playback starts when you pick.';
      }else{
        heading.textContent=duration?('Data use for the remaining '+formatSpan(Math.max(0,duration-at))+
          ' of '+formatSpan(duration)+'.'):'Playback quality';
      }
      qualityMenu.append(heading);
      const rows=planDataUse(estimates,at,canDirect);
      const options=rows.length?rows:QUALITIES.filter(q=>q[0]!=='full').map(([value,label])=>
        ({id:value,name:value==='auto'?'Best available':label,kind:null,bytes:0}));
      for(const row of options){
        const button=document.createElement('button');button.type='button';button.className='willie-data-row';
        button.dataset.quality=row.id;
        const selected=row.id===quality||(quality==='auto'&&!canDirect&&row.id===autoTier);
        button.setAttribute('aria-pressed',String(selected));
        const name=document.createElement('span');name.textContent=row.name;
        const cost=document.createElement('span');cost.className='willie-data-cost';
        cost.textContent=row.bytes>0?((row.kind==='up_to'?'up to ':row.kind==='about'?'about ':'')+formatData(row.bytes)):'';
        if(row.perHour>0)button.title=formatData(row.perHour)+' per hour';
        button.append(name,cost);
        button.onclick=()=>chooseQuality(row.id);
        qualityMenu.append(button);
      }
      if(rows.length){
        const budget=document.createElement('select');budget.className='willie-subtitle-select';
        budget.setAttribute('aria-label','Fit to a data limit');
        const first=document.createElement('option');first.value='';first.textContent='Fit to a data limit…';budget.append(first);
        for(const [bytes,label] of BUDGETS){
          const option=document.createElement('option');option.value=String(bytes);option.textContent='Use at most '+label;budget.append(option);
        }
        const note=document.createElement('div');note.className='willie-data-note';note.setAttribute('aria-live','polite');
        budget.onchange=()=>{
          if(!budget.value)return;
          const limit=Number(budget.value),result=pickForBudget(rows,limit);
          if(!result.fits){
            note.textContent='Even '+result.row.name+' needs about '+formatData(result.row.bytes)+
              ' for the rest. Choosing it anyway.';
            setTimeout(()=>chooseQuality(result.row.id),1500);
          }else chooseQuality(result.row.id);
        };
        qualityMenu.append(budget,note);
        const foot=document.createElement('div');foot.className='willie-data-note';
        foot.textContent='Estimates include audio and streaming overhead. "Up to" tiers are capped, '+
          'not fixed, so real use is often lower.';
        qualityMenu.append(foot);
      }
    }
    function openDataMenu(){
      subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false');
      qualityMenu.hidden=false;qualityButton.setAttribute('aria-expanded','true');
      renderDataMenu();
      estimatesReady.then(()=>{if(!qualityMenu.hidden)renderDataMenu()});
      const target=qualityMenu.querySelector('[aria-pressed="true"]')||qualityMenu.querySelector('button');
      target?.focus();
    }
    qualityButton.onclick=()=>{
      if(!qualityMenu.hidden){
        if(pendingStart)return;   // a choice is required before anything plays
        qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false');return;
      }
      openDataMenu();
    };
    subtitleMenu.append(cc,language,searchLink,results);
    subtitles.onclick=()=>{qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false');subtitleMenu.hidden=!subtitleMenu.hidden;subtitles.setAttribute('aria-expanded',String(!subtitleMenu.hidden));if(!subtitleMenu.hidden)cc.focus()};
    const playPause=document.createElement('button');setIcon(playPause,'pause','Pause');
    playPause.onclick=()=>video.paused?video.play().catch(()=>{}):video.pause();
    let nextEpisode=null;
    let autoPlayNext=false;
    const next=document.createElement('button');setIcon(next,'next','Play next episode');next.hidden=true;
    function launchNext(){
      if(!nextEpisode||current!==surface)return;
      const chosen=nextEpisode;
      if(seasonShuffle && shuffleQueue[0]?.media_id===chosen.media_id)shuffleQueue.shift();
      start(chosen.media_id,chosen.title,{restart:chosen.restart!==false});
    }
    next.onclick=launchNext;
    // When auto-play is enabled, proceed at the end without a countdown,
    // confirmation dialog, or focus-stealing overlay.
    function showNextCountdown(){
      if(autoPlayNext&&nextEpisode&&current===surface)launchNext();
    }
    const diagnostics=document.createElement('button');setIcon(diagnostics,'info','Playback diagnostics');
    diagnostics.onclick=()=>message((playbackMode==='direct'?'Direct Play — browser decoding':(quality==='auto'?autoTier:quality)==='full'?'HLS — original video, audio converted':
      'HLS transcoding ('+(quality==='auto'?autoTier:quality)+')')+
      ' · Server: '+(surface.dataset.engine||'Not reported')+
      ' · Video: '+(video.videoWidth||'?')+'×'+(video.videoHeight||'?')+
      ' · Client GPU decoding depends on browser, device and codec.');
    controls.append(back,name);
    const bottom=document.createElement('div');bottom.className='willie-bottom';
    const toolbar=document.createElement('div');toolbar.className='willie-toolbar';
    const left=document.createElement('div');left.className='willie-group';
    const right=document.createElement('div');right.className='willie-group';
    left.append(playPause,backward,forward);right.append(next,subtitles,qualityButton,watch,diagnostics);
    toolbar.append(left,right);bottom.append(toolbar,subtitleMenu,qualityMenu);
    const info=document.createElement('div');info.className='willie-info';info.setAttribute('role','status');
    const timeline=document.createElement('div');timeline.className='willie-timeline';
    const elapsed=document.createElement('span');elapsed.textContent='0:00:00';
    const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='1000';slider.value='0';
    slider.setAttribute('aria-label','Playback position');
    const total=document.createElement('span');total.textContent='0:00:00';
    const preview=document.createElement('div');preview.className='willie-preview-tooltip';preview.hidden=true;
    const previewImage=document.createElement('img');previewImage.alt='Video preview thumbnail';
    const previewTime=document.createElement('span');preview.append(previewImage,previewTime);
    let previewFrames=[];
    const previewAt=fraction=>{
      if(!previewFrames.length)return;
      const duration=Number(status?.duration_seconds)||video.duration;
      const target=Number.isFinite(duration)?duration*fraction:0;
      const frame=previewFrames.reduce((best,frame)=>
        Math.abs(frame.time-target)<Math.abs(best.time-target)?frame:best,previewFrames[0]);
      if(previewImage.getAttribute('src')!==frame.url)previewImage.src=frame.url;
      previewTime.textContent=Number.isFinite(duration)?formatTime(target):'';
      preview.hidden=false;
    };
    slider.addEventListener('input',()=>previewAt(Math.max(0,Math.min(1,Number(slider.value)/1000))));
    slider.addEventListener('pointermove',event=>{
      const rect=slider.getBoundingClientRect();
      if(rect.width>0)previewAt(Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)));
    });
    for(const eventName of ['pointerleave','blur','change'])slider.addEventListener(eventName,()=>{preview.hidden=true});
    let previewPolls=0;
    const loadPreviews=()=>{
      requestJson('/api/maintenance/preview/'+id).then(data=>{
        if(current!==surface)return;
        if(data.enabled&&Array.isArray(data.frames)){
          previewFrames=data.frames.filter(x=>
            typeof x.url==='string'&&/^\/api\/maintenance\/preview\/\d+\/0(?:0\d|1\d|2[0-3])\.jpg$/.test(x.url))
            .map(x=>({url:x.url,time:Number(x.time_seconds)||0}));
        }
        if(data.generating&&previewPolls++<18)setTimeout(loadPreviews,3000);
      }).catch(()=>{});
    };
    loadPreviews();
    timeline.append(preview);
    timeline.append(elapsed,slider,total);
    bottom.prepend(timeline);surface.append(video,controls,info,bottom);
    document.body.append(surface);current=surface;mediaId=id;started=false;saveAt=0;offset=0;captionsSelect=cc;
    surface.focus({preventScroll:true});
    surface.addEventListener('pointermove',()=>{revealChrome();concealChromeSoon()});
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
      if((e.key==='Enter'||e.key===' ')&&
         (e.target===surface||e.target===video)){
        if(video.paused)video.play().catch(()=>{});
        else video.pause();
        revealChrome();concealChromeSoon();e.preventDefault();return;
      }
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
      queueSeek(target);
    });
    monitor=setInterval(()=>{
      if(current!==surface)return;
      const now=playerPosition(video);
      const reported=Number(status?.duration_seconds);
      const timeline=Number(video.duration);
      const duration=Number.isFinite(reported)&&reported>0?reported:
        Number.isFinite(timeline)&&timeline>0?timeline:0;
      elapsed.textContent=formatTime(now);
      total.textContent=duration>0?formatTime(duration):'--:--';
      if(duration>0&&document.activeElement!==slider){
        slider.value=String(Math.round(1000*Math.min(duration,now)/duration));
      }
      // A regular heartbeat protects streams that do not emit timeupdate
      // events, including some native HLS implementations.
      if(!video.paused&&!video.ended&&started)saveProgress();
    },500);
    video.addEventListener('playing',()=>{
      started=true;clearTimeout(stallTimer);stallTimer=null;
      if(Date.now()-hlsRecoverAt>30000)hlsRecover={network:0,media:0};
      if(Date.now()-hlsRecoverAt>30000)directRetries=0;
      setIcon(playPause,'pause','Pause');message('');concealChromeSoon();
    });
    video.addEventListener('waiting',()=>{
      if(!started||video.paused||playbackMode!=='hls')return;
      clearTimeout(stallTimer);
      stallTimer=setTimeout(()=>{if(current===surface&&!video.paused)recoverStream()},15000);
    });
    video.addEventListener('pause',()=>{clearTimeout(stallTimer);stallTimer=null;setIcon(playPause,'play','Play');revealChrome()});
    video.addEventListener('timeupdate',()=>saveProgress());
    video.addEventListener('pause',()=>saveProgress(true));
    video.addEventListener('ended',()=>{
      const finalSave=saveProgress(true,true);
      if(status)status.watched=true;
      watch.setAttribute('aria-pressed','true');watch.title='Mark unwatched';watch.setAttribute('aria-label',watch.title);
      Promise.resolve(finalSave).finally(()=>{
        document.dispatchEvent(new CustomEvent('willie:watch-updated'));
      });
      showNextCountdown();
    });
    /* True when the original file can be fetched right now. */
    async function originalReachable(){
      const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),4000);
      try{
        const response=await fetch(status.stream_url,{method:'HEAD',cache:'no-store',signal:abort.signal});
        return response.ok;
      }catch(_){return false}
      finally{clearTimeout(timer)}
    }
    video.addEventListener('error',()=>{
      if(playbackMode==='direct'){
        const at=playerPosition(video),code=video.error?.code;
        if(directRetries>=2||!status?.stream_url){playHls(at);return}
        const attempt=++directRetries;hlsRecoverAt=Date.now();
        // A dropped connection is not an unplayable file. Browsers report an
        // early network failure as "format not supported", so ask the server:
        // if the file cannot be fetched, retry it; if it can be (and the error
        // was not a mid-stream network error), the browser cannot decode it.
        originalReachable().then(reachable=>{
          if(current!==surface||playbackMode!=='direct')return;
          if(reachable&&code!==2){playHls(at);return}
          message('Connection hiccup. Retrying…');
          setTimeout(()=>{
            if(current!==surface||playbackMode!=='direct')return;
            video.addEventListener('loadedmetadata',()=>{
              if(Number.isFinite(video.duration)&&at>1&&at<video.duration-4)video.currentTime=at;
            },{once:true});
            video.src=status.stream_url;
            video.play().catch(()=>{});
          },1000*attempt);
        });
      }else recoverStream();
    });
    message('Opening video…');
    requestJson('/api/watch/'+id+'/status').then(data=>{
      if(current!==surface)return;
      status=data;watch.setAttribute('aria-pressed',String(data.watched));watch.title=data.watched?'Mark unwatched':'Mark watched';watch.setAttribute('aria-label',watch.title);
      // Server-wide saved setting; no per-playback toggle required.
      requestJson('/api/settings/playback').then(prefs=>{
        if(current!==surface)return;
        autoPlayNext=!!prefs.auto_play_next||seasonShuffle;
        if(video.ended)showNextCountdown();
      }).catch(()=>{autoPlayNext=seasonShuffle});
      reloadTracks().catch(()=>{});
      (seasonShuffle?Promise.resolve({next:null}):requestJson('/api/tv/next?media_id='+id)).then(result=>{
        if(current!==surface)return;
        nextEpisode=seasonShuffle?(shuffleQueue[0]||null):(result.next||null);
        next.hidden=!nextEpisode;
        // If status/next results race with a very short clip, still offer next.
        if(video.ended)showNextCountdown();
      }).catch(()=>{next.hidden=true});
      const resume=options.restart||data.watched?0:Number(data.position_seconds)||0;
      const begin=()=>{
        if(current!==surface)return;
        if(quality==='auto'&&browserCanDirect(video,data)){
          playbackMode='direct';surface.dataset.engine='Browser';video.src=data.stream_url;
          if(resume>5)video.addEventListener('loadedmetadata',()=>{
            if(Number.isFinite(video.duration)&&resume<video.duration-4)video.currentTime=resume;
          },{once:true});
          video.play().catch(()=>message('Press Play to start.'));
        }else playHls(resume);
      };
      const beginWhenPlanned=async()=>{
        // "Best available" on a file the browser cannot play as-is: find out
        // (briefly) whether the original video can be passed through.
        if(quality==='auto'&&!browserCanDirect(video,data))
          await Promise.race([estimatesReady,new Promise(resolve=>setTimeout(resolve,2500))]);
        resolveAutoTier();begin();
      };
      if(onMeteredConnection()&&!hasChosenQuality()){
        // Nothing is downloaded until the viewer has seen what each choice costs.
        pendingStart=begin;message('Choose how much data to use.');
        estimatesReady.finally(()=>{if(current===surface&&pendingStart)openDataMenu()});
      }else beginWhenPlanned();
    }).catch(e=>message(e.message));
  }
  const open=(id,title,options={})=>{
    seasonShuffle=false;shuffleQueue=[];
    start(id,title,options);
  };
  function shuffleSeason(episodes){
    if(!Array.isArray(episodes))return;
    const list=episodes.slice(0,500).filter(item=>Number.isInteger(item?.id)&&item.id>0)
      .map(item=>({media_id:item.id,title:String(item.title||'Episode').slice(0,160),
        restart:!item.resume}));
    if(!list.length)return;
    // Fisher-Yates: one pass plays every episode exactly once.
    for(let i=list.length-1;i>0;i--){
      const j=Math.floor(Math.random()*(i+1));
      [list[i],list[j]]=[list[j],list[i]];
    }
    seasonShuffle=true;shuffleQueue=list.slice(1);
    const first=list[0];
    start(first.media_id,first.title,{restart:first.restart});
  }
  window.WilliePlayer={open,close,shuffleSeason};
})();
