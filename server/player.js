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
  let viewing='', usageTimer=null;
  let audioTracks=[], audioIndex=0, audioChosen=false;
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
  /* One random id per viewing lets the server add up everything it sends for it. */
  function newViewingId(){
    const bytes=new Uint8Array(12);
    if(window.crypto?.getRandomValues)crypto.getRandomValues(bytes);
    else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
    return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  }
  /* Is it worth offering a cheaper quality? Looks at recent buffering stalls:
   * three in a minute and a half, or about ten seconds spent waiting. */
  const SLOW_RULES={window:90000,stalls:3,waitMs:10000,singleMs:8000};
  function connectionLooksSlow(stalls,ongoingMs,now){
    const recent=stalls.filter(item=>now-item.at<=SLOW_RULES.window);
    const count=recent.length+(ongoingMs>0?1:0);
    const waited=recent.reduce((sum,item)=>sum+item.ms,0)+Math.max(0,ongoingMs);
    return count>=SLOW_RULES.stalls||waited>=SLOW_RULES.waitMs||ongoingMs>=SLOW_RULES.singleMs;
  }
  /* The cheaper choice to suggest: the best tier using well under the data the
   * current stream does (60%), otherwise the cheapest; null if already lowest. */
  const STEP_DOWN={original:'720p',full:'720p','1080p':'720p','720p':'480p','480p':'360p','360p':'240p'};
  function lowerQuality(estimates,current){
    const tiers=estimates?.qualities||[];
    const duration=Number(estimates?.duration_seconds)||0;
    let kbps=null;
    if(current==='original')kbps=Number(estimates?.original?.kbps)||null;
    else if(current==='full')kbps=estimates?.full?.bytes>0&&duration?estimates.full.bytes*8/1000/duration:null;
    else kbps=Number(tiers.find(t=>t.id===current)?.kbps)||null;
    if(kbps&&tiers.length){
      const cheaper=tiers.filter(t=>t.id!==current&&Number(t.kbps)>0&&t.kbps<kbps);
      if(!cheaper.length)return null;
      const comfortable=cheaper.find(t=>t.kbps<=kbps*0.6);
      return comfortable||cheaper[cheaper.length-1];
    }
    const id=STEP_DOWN[current];
    return id?(tiers.find(t=>t.id===id)||{id}):null;
  }
  function savedQuality(){
    try{const value=localStorage.getItem('willie:quality');return QUALITIES.some(q=>q[0]===value)?value:'auto'}
    catch(_){return 'auto'}
  }
  // What "Best available" becomes when the original file cannot be played as-is:
  // the untouched video when the server can pass it through, else a 720p transcode.
  let autoTier='720p';
  let passthroughFailed=null;   // set by the open player: drop from Full quality to 720p
  /* The deepest HEVC this browser says it can decode: 10 (Main 10), 8 (Main) or 0.
   * Sent to the server so Full quality is offered for HEVC and 10-bit video only
   * where it can play. Forgotten for the tab if a copied video then failed to decode. */
  function hevcSupport(video){
    try{if(sessionStorage.getItem('willie:hevc-failed')==='1')return 0}catch(_){}
    const supported=codec=>{
      const type='video/mp4; codecs="'+codec+'"';
      try{if(window.MediaSource?.isTypeSupported)return !!MediaSource.isTypeSupported(type)}catch(_){}
      try{return !!video?.canPlayType(type)}catch(_){return false}
    };
    return supported('hvc1.2.4.L120.B0')?10:supported('hvc1.1.6.L120.B0')?8:0;
  }
  let hevcDepth=0;
  /* True while a copied (not re-encoded) non-H.264 video is playing as a stream. */
  function passthroughNeedsDecoder(){
    const tier=quality==='auto'?autoTier:quality;
    const codec=status?.media?.video_codec;
    return playbackMode==='hls'&&tier==='full'&&!!codec&&codec!=='h264';
  }
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
.willie-player{--sel:var(--oew-tv-select-color,#8B5CF6);--sel-soft:#ffffff1f}
@supports(color:color-mix(in srgb,red 20%,transparent)){.willie-player{--sel-soft:color-mix(in srgb,var(--sel) 20%,transparent)}}
.willie-controls{position:absolute;top:0;left:0;right:0;z-index:5;padding:18px 32px 40px;
background:linear-gradient(#0000007a,transparent);display:flex;align-items:center;gap:15px;
opacity:0;transition:opacity .15s}
.willie-player:hover .willie-controls,.willie-player:focus-within .willie-controls{opacity:1}
.willie-controls button,.willie-toolbar button{background:transparent;border:0;border-radius:40px;width:54px;height:54px;display:inline-flex;align-items:center;justify-content:center;color:#F4EFE4;opacity:.88;padding:14px;cursor:pointer;transition:transform .11s,opacity .11s,color .11s;-webkit-tap-highlight-color:transparent}
.willie-toolbar button.willie-large{width:64px;height:64px;padding:15px}
.willie-controls button:focus-visible,.willie-toolbar button:focus-visible{background:transparent;color:var(--sel);opacity:1;transform:scale(1.16)}
@media(hover:hover){.willie-controls button:hover,.willie-toolbar button:hover{background:transparent;color:var(--sel);opacity:1;transform:scale(1.16)}}
.willie-player button:focus-visible{outline:none}
.willie-controls button svg,.willie-toolbar button svg{width:100%;height:100%;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.willie-bottom{position:absolute;bottom:0;left:0;right:0;z-index:5;background:linear-gradient(to top,#000000f2,#090b10db,transparent);padding:64px 50px 23px;transition:opacity .2s}
.willie-preview-tooltip{position:absolute;bottom:102px;left:50%;transform:translateX(-50%);z-index:9;width:180px;text-align:center;pointer-events:none;background:#0A111DEF;border:1px solid #68798D80;border-radius:13px;padding:6px;box-shadow:0 8px 22px #0009}
.willie-preview-tooltip[hidden]{display:none}
.willie-preview-tooltip img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px}
.willie-preview-tooltip span{font-size:13px;color:#F4EFE4;font-variant-numeric:tabular-nums}
.willie-toolbar{display:flex;justify-content:space-between;align-items:center;padding-top:8px}
.willie-group{display:flex;align-items:center;gap:8px}
.willie-subtitle-menu{position:absolute;right:50px;bottom:128px;background:#0A111DEF;border:1px solid #68798D80;border-radius:17px;padding:18px 20px 16px;display:flex;flex-direction:column;gap:10px;width:min(420px,calc(100vw - 40px));color:#F0F2F5;box-shadow:0 14px 48px #000a}
.willie-subtitle-menu[hidden]{display:none}
.willie-subtitle-menu a{color:#F0F2F5;font-size:16px;text-decoration:none;padding:9px}
.willie-menu-title{font-size:22px;font-weight:700;color:#F6F2EB;padding:0 7px 4px}
.willie-provider-search,.willie-subtitle-result{width:100%;min-height:49px;text-align:left;background:transparent;color:#F0F2F5;border:1px solid transparent;border-radius:9px;padding:7px 13px;cursor:pointer;font:inherit;font-size:16px}
.willie-provider-search:hover,.willie-subtitle-result:hover,.willie-provider-search:focus-visible,.willie-subtitle-result:focus-visible{background:var(--sel-soft);border-color:var(--sel);color:var(--sel)}
.willie-subtitle-results{max-height:35vh;overflow-y:auto;display:flex;flex-direction:column;gap:3px;font-size:15px}
.willie-subtitle-menu{max-height:calc(100vh - 230px);overflow-y:auto}
.willie-data-menu{gap:4px}
.willie-data-heading{font-size:15px;color:#C9D6E6;padding:2px 8px 12px;line-height:1.45}
.willie-data-row{display:flex;justify-content:space-between;align-items:center;gap:14px;width:100%;min-height:49px;text-align:left;background:transparent;color:#F0F2F5;border:1px solid transparent;border-radius:9px;padding:7px 13px;cursor:pointer;font:inherit;font-size:16px}
.willie-data-row:hover,.willie-data-row:focus-visible{background:var(--sel-soft);border-color:var(--sel);color:var(--sel)}
.willie-data-row[aria-pressed="true"]{color:var(--sel)}
.willie-data-row[aria-pressed="true"]>span:first-child::before{content:"\\2713\\a0\\a0"}
.willie-audio-title{padding-top:12px}
.willie-audio-row{display:flex;justify-content:space-between;align-items:center;gap:14px;width:100%;min-height:49px;text-align:left;background:transparent;color:#F0F2F5;border:1px solid transparent;border-radius:9px;padding:7px 13px;cursor:pointer;font:inherit;font-size:16px}
.willie-audio-row:hover,.willie-audio-row:focus-visible{background:var(--sel-soft);border-color:var(--sel);color:var(--sel)}
.willie-audio-row[aria-pressed="true"]{color:var(--sel)}
.willie-audio-row[aria-pressed="true"]>span:first-child::before{content:"\\2713\\a0\\a0"}
.willie-data-cost{font-variant-numeric:tabular-nums;color:#C9D6E6;white-space:nowrap}
.willie-data-row:hover .willie-data-cost,.willie-data-row:focus-visible .willie-data-cost,.willie-data-row[aria-pressed="true"] .willie-data-cost{color:inherit}
.willie-data-note{font-size:13px;color:#9fb2c6;padding:4px 8px;line-height:1.45}
.willie-data-used{font-size:14px;color:#C9D6E6;padding:2px 8px 8px;font-variant-numeric:tabular-nums}
.willie-subtitle-menu .willie-subtitle-select{max-width:none;width:100%}
.willie-subtitle-select{background:#ffffff12;border:1px solid #68798D80;border-radius:9px;
color:#F0F2F5;min-height:49px;padding:7px 13px;font:inherit;font-size:16px;max-width:180px;cursor:pointer}
.willie-subtitle-select:focus-visible{outline:none;border-color:var(--sel);background:var(--sel-soft)}
.willie-subtitle-select option{background:#0A111D;color:#F0F2F5}
.willie-subtitle-select[hidden]{display:none}
.willie-titles{display:flex;flex-direction:column;flex:1;min-width:0;justify-content:center}
.willie-kicker{font-size:11px;letter-spacing:.14em;font-weight:700;color:#DDD7CA}
.willie-title{font-size:22px;font-weight:700;color:#F7F3EB;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.willie-usage{font-size:14px;color:#D2CFCA;white-space:nowrap;font-variant-numeric:tabular-nums;padding:6px 12px;border-radius:40px;background:#0A111DB0}
.willie-usage[hidden]{display:none}
.willie-info{position:absolute;left:50%;bottom:150px;transform:translateX(-50%);
background:#101820DD;color:#fff;font-size:16px;
max-width:85vw;padding:15px 24px;text-align:center;z-index:6}
.willie-info:empty{display:none}
.willie-player.willie-chrome-hidden{cursor:none}
.willie-player.willie-chrome-hidden .willie-controls,
.willie-player.willie-chrome-hidden .willie-bottom{opacity:0;pointer-events:none}
.willie-player .willie-timeline{transition:opacity .2s ease}
.willie-player .willie-info:not(:empty){opacity:1}
.willie-player:not(.willie-chrome-hidden) .willie-controls{opacity:1}
.willie-player:not(.willie-chrome-hidden) .willie-bottom{opacity:1}
@media(prefers-reduced-motion:reduce){.willie-controls,.willie-bottom,.willie-controls button,.willie-toolbar button{transition:none}}
.willie-slow-prompt{position:absolute;bottom:128px;right:50px;z-index:8;background:#0A111DEF;border:1px solid #68798D80;border-radius:17px;padding:18px 20px 16px;width:min(420px,calc(100vw - 40px));color:#F0F2F5;box-shadow:0 14px 48px #000a;display:flex;flex-direction:column;gap:4px}
.willie-slow-prompt[hidden]{display:none}
.willie-slow-prompt p{margin:0;padding:2px 8px 12px;text-align:left;font-size:15px;line-height:1.45;color:#C9D6E6}
.willie-slow-prompt button{display:block;width:100%;min-height:49px;text-align:left;background:transparent;color:#F0F2F5;border:1px solid transparent;border-radius:9px;padding:7px 13px;cursor:pointer;font:inherit;font-size:16px}
.willie-slow-prompt button:hover,.willie-slow-prompt button:focus-visible{background:var(--sel-soft);border-color:var(--sel);color:var(--sel)}
.willie-timeline{display:flex;
align-items:center;gap:12px;padding:0;z-index:5;position:relative}
.willie-timeline input{flex:1;height:55px;margin:0;accent-color:var(--sel);cursor:pointer;-webkit-appearance:none;appearance:none;background:transparent}
.willie-timeline input::-webkit-slider-runnable-track{height:4px;border-radius:2px;background:linear-gradient(to right,var(--sel) var(--pos,0%),#F4EFE466 var(--pos,0%))}
.willie-timeline input::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:var(--sel);margin-top:-6px;border:0}
.willie-timeline input::-moz-range-track{height:4px;border-radius:2px;background:#F4EFE466}
.willie-timeline input::-moz-range-progress{height:4px;border-radius:2px;background:var(--sel)}
.willie-timeline input::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--sel);border:0}
.willie-timeline input:focus-visible{outline:none}
.willie-timeline input:focus-visible::-webkit-slider-thumb{box-shadow:0 0 0 5px var(--sel-soft)}
.willie-timeline span{font-size:15px;color:#F4EFE4;font-variant-numeric:tabular-nums;min-width:74px}
.willie-timeline span:last-of-type{color:#D2CFCA;text-align:right}
@media(hover:none){.willie-controls,.willie-bottom{opacity:1}}
@media(max-width:700px){
.willie-controls{padding:12px 12px 32px;gap:8px}
.willie-title{font-size:18px}
.willie-bottom{padding:48px 14px 14px}
.willie-timeline span{min-width:0;font-size:13px}
.willie-timeline input{height:44px}
.willie-controls button,.willie-toolbar button{width:42px;height:48px;padding:12px 9px}
.willie-toolbar button.willie-large{width:52px;height:56px;padding:13px 11px}
.willie-group{gap:2px}
.willie-subtitle-menu,.willie-slow-prompt{left:10px;right:10px;bottom:118px;width:auto;max-height:70vh}
.willie-info{bottom:128px}
}
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
  /* A browser plays only a file's first audio track; any other needs a stream. */
  const directAudio=()=>audioIndex===0;
  /* Saved language first, then the file's default track, else the first. */
  function pickAudio(tracks){
    if(!Array.isArray(tracks)||tracks.length<2)return 0;
    let language='';
    try{language=localStorage.getItem('willie:audio-language')||''}catch(_){}
    const wanted=language&&tracks.find(t=>t.language===language);
    return (wanted||tracks.find(t=>t.default)||tracks[0]).id;
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
    clearInterval(monitor);monitor=null;clearInterval(usageTimer);usageTimer=null;
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
        '&quality='+encodeURIComponent(tier)+'&viewing='+encodeURIComponent(viewing)+'&audio='+audioIndex+
        (hevcDepth?'&hevc='+hevcDepth:'');
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
          // A copied HEVC/10-bit video this browser cannot decode will not improve on retry.
          if(data.type!==Hls.ErrorTypes.NETWORK_ERROR&&passthroughNeedsDecoder()&&passthroughFailed){
            passthroughFailed();return;
          }
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
    back:'<path d="M15,18 L9,12 L15,6 M9,12 L21,12"/>',
    rewind:'<path d="M11,19 L2,12 L11,5 Z M22,19 L13,12 L22,5 Z"/>',
    forward:'<path d="M13,19 L22,12 L13,5 Z M2,19 L11,12 L2,5 Z"/>',
    subtitle:'<path d="M4,5 L20,5 L20,19 L4,19 Z M7,11 L11,11 M7,15 L10,15 M14,11 L18,11 M14,15 L17,15"/>',
    watched:'<path d="M20,6 L9,17 L4,12"/>',
    play:'<path d="M8,5 L19,12 L8,19 Z"/>',
    pause:'<path d="M8,5 L8,19 M16,5 L16,19"/>',
    info:'<path d="M12,2 A10,10 0,1 1,11.99,2 Z M12,11 L12,17 M12,7 L12,7.01"/>',
    next:'<path d="M5,5 L16,12 L5,19 Z M19,5 L19,19"/>',
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
    const replacing=!!current;   // e.g. next episode: the old player's removal ends fullscreen
    if(current)close();
    viewing=newViewingId();audioTracks=[];audioIndex=0;audioChosen=false;passthroughFailed=null;
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
    hevcDepth=hevcSupport(video);
    video.controls=false;video.autoplay=true;video.playsInline=true;video.preload='metadata';
    const controls=document.createElement('div');controls.className='willie-controls';
    const back=document.createElement('button');back.type='button';setIcon(back,'back','Back to library');back.onclick=close;
    const titles=document.createElement('div');titles.className='willie-titles';
    const kicker=document.createElement('span');kicker.className='willie-kicker';kicker.textContent='NOW PLAYING';
    const name=document.createElement('span');name.className='willie-title';name.textContent=title||'Now playing';
    titles.append(kicker,name);
    const usagePill=document.createElement('span');usagePill.className='willie-usage';usagePill.hidden=true;
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
    const tracksReady=requestJson('/api/stream/hls/audio/'+id).then(data=>{
      audioTracks=Array.isArray(data.tracks)?data.tracks:[];
      if(!audioChosen)audioIndex=pickAudio(audioTracks);
      return audioTracks;
    }).catch(()=>[]);
    const stalls=[];let stallBegan=0,slowSnoozeUntil=0,quietUntil=0,usedBytes=0;
    const quiet=ms=>{quietUntil=Math.max(quietUntil,performance.now()+ms)};
    const slowPrompt=document.createElement('div');slowPrompt.className='willie-slow-prompt';slowPrompt.hidden=true;
    slowPrompt.setAttribute('role','dialog');slowPrompt.setAttribute('aria-label','Slow connection');
    const estimatesReady=requestJson('/api/stream/hls/estimates/'+id+(hevcDepth?'?hevc='+hevcDepth:'')).then(data=>{estimates=data;return data}).catch(()=>null);
    const resolveAutoTier=()=>{autoTier=estimates?.full?.available?'full':'720p'};
    function chooseQuality(choice,remember=true){
      quality=choice;resolveAutoTier();
      // A temporary drop for a bad connection is not a new standing preference.
      if(remember)try{localStorage.setItem('willie:quality',quality)}catch(_){}
      stalls.length=0;stallBegan=0;slowSnoozeUntil=0;slowPrompt.hidden=true;quiet(10000);
      qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false');
      surface.focus({preventScroll:true});
      if(pendingStart){const begin=pendingStart;pendingStart=null;begin();return}
      if(!status)return;
      const at=playerPosition(video);
      if(quality==='auto'&&browserCanDirect(video,status)&&directAudio())playDirect(at);
      else playHls(at);
      revealChrome();concealChromeSoon();
    }
    passthroughFailed=()=>{
      if(current!==surface||switching)return;
      try{sessionStorage.setItem('willie:hevc-failed','1')}catch(_){}
      hevcDepth=0;if(estimates?.full)estimates.full.available=false;
      chooseQuality('720p',false);
      setTimeout(()=>{if(current===surface)message('This browser could not play the original video. Using 720p instead.')},900);
    };
    function chooseAudio(index){
      audioChosen=true;audioIndex=index;
      const track=audioTracks.find(t=>t.id===index);
      try{if(track?.language)localStorage.setItem('willie:audio-language',track.language)}catch(_){}
      stalls.length=0;stallBegan=0;slowPrompt.hidden=true;quiet(10000);
      qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false');
      surface.focus({preventScroll:true});
      if(pendingStart){const begin=pendingStart;pendingStart=null;begin();return}
      if(!status)return;
      const at=playerPosition(video);
      if(quality==='auto'&&browserCanDirect(video,status)&&directAudio())playDirect(at);
      else playHls(at);
      revealChrome();concealChromeSoon();
    }
    function renderDataMenu(){
      // Re-rendering (new estimates, usage figures) must not drop the viewer's place.
      const focused=qualityMenu.contains(document.activeElement)?document.activeElement.dataset?.quality:null;
      const focusedAudio=qualityMenu.contains(document.activeElement)?document.activeElement.dataset?.audio:null;
      qualityMenu.textContent='';
      const menuTitle=document.createElement('div');menuTitle.className='willie-menu-title';menuTitle.textContent='Quality and data';
      qualityMenu.append(menuTitle);
      const heading=document.createElement('div');heading.className='willie-data-heading';
      const duration=Number(estimates?.duration_seconds)||Number(status?.duration_seconds)||0;
      const at=started?playerPosition(video):Number(status?.position_seconds)||0;
      const canDirect=!!status&&browserCanDirect(video,status)&&directAudio();
      if(pendingStart){
        heading.textContent='You are on mobile data. Choose how much to use — playback starts when you pick.';
      }else{
        heading.textContent=duration?('Data use for the remaining '+formatSpan(Math.max(0,duration-at))+
          ' of '+formatSpan(duration)+'.'):'Playback quality';
      }
      qualityMenu.append(heading);
      if(usedBytes>0){
        const used=document.createElement('div');used.className='willie-data-used';
        used.textContent='Used so far this viewing: '+formatData(usedBytes);
        qualityMenu.append(used);
      }
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
      if(audioTracks.length>1){
        const audioTitle=document.createElement('div');audioTitle.className='willie-menu-title willie-audio-title';audioTitle.textContent='Audio';
        qualityMenu.append(audioTitle);
        for(const track of audioTracks){
          const button=document.createElement('button');button.type='button';button.className='willie-audio-row';
          button.dataset.audio=String(track.id);button.setAttribute('aria-pressed',String(track.id===audioIndex));
          const label=document.createElement('span');label.textContent=track.label;button.append(label);
          button.onclick=()=>chooseAudio(track.id);
          qualityMenu.append(button);
        }
      }
      if(focused)qualityMenu.querySelector('[data-quality="'+focused+'"]')?.focus({preventScroll:true});
      else if(focusedAudio)qualityMenu.querySelector('[data-audio="'+focusedAudio+'"]')?.focus({preventScroll:true});
    }
    function openDataMenu(){
      subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false');
      qualityMenu.hidden=false;qualityButton.setAttribute('aria-expanded','true');
      renderDataMenu();refreshUsage().then(()=>{if(!qualityMenu.hidden&&usedBytes>0&&!qualityMenu.querySelector('.willie-data-used'))renderDataMenu()});
      estimatesReady.then(()=>{if(!qualityMenu.hidden)renderDataMenu()});
      tracksReady.then(()=>{if(!qualityMenu.hidden)renderDataMenu()});
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
    const subtitleTitle=document.createElement('div');subtitleTitle.className='willie-menu-title';subtitleTitle.textContent='Subtitles';
    subtitleMenu.append(subtitleTitle,cc,language,searchLink,results);
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
    controls.append(back,titles,usagePill);
    const bottom=document.createElement('div');bottom.className='willie-bottom';
    const toolbar=document.createElement('div');toolbar.className='willie-toolbar';
    const left=document.createElement('div');left.className='willie-group';
    const right=document.createElement('div');right.className='willie-group';
    playPause.classList.add('willie-large');
    left.append(backward,playPause,forward);right.append(next,subtitles,qualityButton,watch,diagnostics);
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
    const paintSlider=()=>slider.style.setProperty('--pos',(Number(slider.value)/10)+'%');
    slider.addEventListener('input',paintSlider);
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
    bottom.prepend(timeline);surface.append(video,controls,info,bottom,slowPrompt);
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
    let entered=false,enteredAt=0;
    const fullscreenChanged=()=>{
      if(document.fullscreenElement===surface){entered=true;enteredAt=performance.now()}
      else if(entered&&current===surface){
        // Replacing a fullscreen player makes the browser leave fullscreen a moment
        // after the new one enters it. That is not the viewer leaving: keep playing.
        if(replacing&&performance.now()-enteredAt<1500){entered=false;return}
        close();
      }
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
        if(!slowPrompt.hidden){snoozeSlowPrompt()}
        else if(!qualityMenu.hidden&&!pendingStart){qualityMenu.hidden=true;qualityButton.setAttribute('aria-expanded','false')}
        else if(!subtitleMenu.hidden){subtitleMenu.hidden=true;subtitles.setAttribute('aria-expanded','false')}
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
      paintSlider();
      // A regular heartbeat protects streams that do not emit timeupdate
      // events, including some native HLS implementations.
      if(!video.paused&&!video.ended&&started)saveProgress();
      if(stallBegan)slowCheck();
    },500);
    usageTimer=setInterval(()=>{if(current===surface&&!document.hidden)refreshUsage()},5000);
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
    /* Buffering stalls drive the "slow connection" offer. Start-up buffering
     * (before the first frame), seeks and quality switches do not count. */
    video.addEventListener('waiting',()=>{
      if(!started||video.paused||video.seeking||stallBegan||performance.now()<quietUntil)return;
      stallBegan=performance.now();
    });
    video.addEventListener('playing',()=>{
      if(!stallBegan)return;
      const now=performance.now();
      stalls.push({at:now,ms:now-stallBegan});stallBegan=0;
      if(stalls.length>20)stalls.shift();
      slowCheck();
    });
    video.addEventListener('seeking',()=>{stallBegan=0;quiet(5000)});
    video.addEventListener('pause',()=>{stallBegan=0});
    function slowCheck(){
      if(current!==surface||!started)return;
      const now=performance.now();
      if(connectionLooksSlow(stalls,stallBegan?now-stallBegan:0,now))offerLowerQuality();
    }
    function snoozeSlowPrompt(){
      slowPrompt.hidden=true;slowSnoozeUntil=performance.now()+10*60*1000;
      stalls.length=0;stallBegan=0;surface.focus({preventScroll:true});
    }
    function offerLowerQuality(){
      if(current!==surface||!slowPrompt.hidden||pendingStart||switching||!status)return;
      if(performance.now()<slowSnoozeUntil)return;
      const now=playbackMode==='direct'?'original':(quality==='auto'?autoTier:quality);
      const option=lowerQuality(estimates,now);
      if(!option)return;
      const at=playerPosition(video);
      const row=planDataUse(estimates,at,playbackMode==='direct').find(item=>item.id===option.id);
      slowPrompt.textContent='';
      const heading=document.createElement('div');heading.className='willie-menu-title';heading.textContent='Slow connection';
      const text=document.createElement('p');
      text.textContent='Playback keeps pausing to load more video. '+option.id+' uses less data'+
        (row?.bytes>0?' (about '+formatData(row.bytes)+' for the rest)':'')+' and should play smoothly.';
      const lower=document.createElement('button');lower.type='button';lower.dataset.action='lower';
      lower.textContent='Switch to '+option.id;
      lower.onclick=()=>{slowPrompt.hidden=true;chooseQuality(option.id,false)};
      const keep=document.createElement('button');keep.type='button';keep.dataset.action='keep';
      keep.textContent='Keep current quality';keep.onclick=snoozeSlowPrompt;
      slowPrompt.append(heading,text,lower,keep);
      slowPrompt.hidden=false;revealChrome();lower.focus({preventScroll:true});
    }
    const usagePillText=bytes=>formatData(bytes)+' used';
    function refreshUsage(){
      return requestJson('/api/stream/hls/usage/'+viewing).then(data=>{
        if(current!==surface)return;
        usedBytes=Number(data.bytes)||0;
        if(usedBytes>0){
          usagePill.hidden=false;usagePill.textContent=usagePillText(usedBytes);
          usagePill.setAttribute('aria-label','Data used this viewing: '+formatData(usedBytes));
          const line=qualityMenu.querySelector('.willie-data-used');
          if(line)line.textContent='Used so far this viewing: '+formatData(usedBytes);
        }
      }).catch(()=>{});
    }
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
      }else if(passthroughNeedsDecoder()&&video.error?.code!==2&&passthroughFailed)passthroughFailed();
      else recoverStream();
    });
    message('Opening video…');
    requestJson('/api/watch/'+id+'/status').then(data=>{
      if(current!==surface)return;
      status=data;
      if(typeof data.stream_url==='string')
        data.stream_url+=(data.stream_url.includes('?')?'&':'?')+'viewing='+viewing;
      watch.setAttribute('aria-pressed',String(data.watched));watch.title=data.watched?'Mark unwatched':'Mark watched';watch.setAttribute('aria-label',watch.title);
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
        if(quality==='auto'&&browserCanDirect(video,data)&&directAudio()){
          playbackMode='direct';surface.dataset.engine='Browser';video.src=data.stream_url;
          if(resume>5)video.addEventListener('loadedmetadata',()=>{
            if(Number.isFinite(video.duration)&&resume<video.duration-4)video.currentTime=resume;
          },{once:true});
          video.play().catch(()=>message('Press Play to start.'));
        }else playHls(resume);
      };
      const beginWhenPlanned=async()=>{
        await Promise.race([tracksReady,new Promise(resolve=>setTimeout(resolve,1500))]);
        // "Best available" on a file the browser cannot play as-is: find out
        // (briefly) whether the original video can be passed through.
        if(quality==='auto'&&!(browserCanDirect(video,data)&&directAudio()))
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
