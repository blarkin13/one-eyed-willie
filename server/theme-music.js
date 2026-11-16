/* Background audio from local files or on-demand TelevisionTunes personal listening copies. */
(()=>{
  'use strict';
  let active=null;
  const icon=(muted)=>muted
    ?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5ZM16 9l5 6m0-6-5 6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    :'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5ZM15 9a5 5 0 0 1 0 6m3-9a9 9 0 0 1 0 12" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  async function attach(mediaId,kind,container){
    if(active)active.stop(true);
    if(!Number.isInteger(mediaId)||mediaId<=0||!['tv','movies'].includes(kind)||!container)return;
    let preferences,found;
    try{
      const responses=await Promise.all([
        fetch('/api/settings/playback',{cache:'no-store'}),
        fetch('/api/themes/'+mediaId+'/info',{cache:'no-store'})
      ]);
      if(!responses.every(r=>r.ok))return;
      [preferences,found]=await Promise.all(responses.map(r=>r.json()));
    }catch(_){return}
    if(!preferences[kind==='tv'?'tv_theme_music':'movie_theme_music'])return;
    if(!found.available||!found.url){
      const reasons={
        tv_only_source:'Movie theme playback requires a local theme file.',
        title_not_recognized:'This TV show could not be identified for theme lookup.',
        not_available_from_source:'No matching TV theme page was found on TelevisionTunes.',
        source_title_mismatch:'TelevisionTunes returned a different show title.',
        source_download_link_unrecognized:'TelevisionTunes changed its download links; automatic theme retrieval is unavailable.',
        source_access_denied:'TelevisionTunes blocked automatic access to its theme music.',
        source_unreachable:'Could not reach TelevisionTunes for this theme.',
        source_dns_failure:'The server cannot resolve the TelevisionTunes hostname (DNS).',
        source_tls_failure:'The server could not establish a secure HTTPS connection to TelevisionTunes.',
        source_timeout:'TelevisionTunes did not respond before the connection timed out.',
        source_connection_refused:'The connection to TelevisionTunes was refused.',
        source_network_error:'The server could not connect to TelevisionTunes.',
        source_http_error:'TelevisionTunes returned an unexpected HTTP error.',
        source_page_not_found:'The matching TelevisionTunes page could not be found.',
        unexpected_source_response:'TelevisionTunes returned an unexpected response instead of a theme MP3.'
      };
      const hint=document.createElement('span');
      hint.className='theme-music-hint';
      hint.textContent=reasons[found.reason]||'No theme music available for this title.';
      hint.setAttribute('role','status');
      container.replaceChildren(hint);
      if(kind==='tv'&&typeof found.source_page==='string'
          &&/^https:\/\/televisiontunes\.com\/[A-Za-z0-9_%()-]+\.html$/.test(found.source_page)){
        const link=document.createElement('a');
        link.href=found.source_page;
        link.target='_blank';
        link.rel='noopener noreferrer';
        link.className='theme-source-link';
        link.textContent='View theme on TelevisionTunes';
        link.title='Open the source website to listen or download manually';
        container.append(link);
      }
      return;
    }
    const audio=new Audio();
    audio.src=found.url;
    audio.volume=0;
    audio.preload='none';
    audio.loop=!!preferences.theme_loop;
    const volume=Math.max(0,Math.min(1,(Number(preferences.theme_volume)||0)/100));
    const fade=!!preferences.theme_fade&&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let muted=false,disposed=false,frame=0,armed=false,playing=false;
    const button=document.createElement('button');
    button.type='button';button.className='media-icon-action theme-music-toggle';
    const update=()=>{
      button.innerHTML=icon(muted);
      button.title=armed?'Play theme music':muted?'Unmute theme music':'Mute theme music';
      button.setAttribute('aria-label',button.title);
      button.setAttribute('aria-pressed',String(muted));
    };
    update();container.append(button);
    const ramp=(target,duration,done)=>{
      cancelAnimationFrame(frame);
      if(!duration){audio.volume=target;done?.();return}
      const start=performance.now(),initial=audio.volume;
      const step=(now)=>{
        const t=Math.min(1,(now-start)/duration);
        audio.volume=initial+(target-initial)*t;
        if(t<1)frame=requestAnimationFrame(step);
        else done?.();
      };
      frame=requestAnimationFrame(step);
    };
    const stop=(immediate=false)=>{
      if(disposed)return;
      disposed=true;armed=false;
      document.removeEventListener('pointerdown',gesture,true);
      document.removeEventListener('keydown',gesture,true);
      if(immediate||!fade||audio.paused){cancelAnimationFrame(frame);audio.pause();audio.removeAttribute('src');audio.load()}
      else ramp(0,240,()=>{audio.pause();audio.removeAttribute('src');audio.load()});
      button.remove();
    };
    const play=async()=>{
      if(disposed||muted)return;
      audio.volume=fade?0:volume;
      try{
        await audio.play();
        armed=false;
        playing=true;
        update();
        if(fade)ramp(volume,650);
      }catch(error){
        // A visible Play control is necessary when browser autoplay is blocked.
        armed=true;
        update();
        if(error?.name!=='NotAllowedError'){
          button.title='Theme audio could not play — press to retry';
          button.setAttribute('aria-label',button.title);
        }
      }
    };
    const gesture=(event)=>{
      if(!armed||disposed||muted)return;
      if(event.type==='keydown'&&!['Enter',' ','ArrowDown','ArrowUp','ArrowLeft','ArrowRight'].includes(event.key))return;
      if(event.target?.closest?.('#play-movie,#resume-movie,#series-play-button,#series-shuffle-button,#season-play-button,.season-episode-tile'))return;
      play();
    };
    document.addEventListener('pointerdown',gesture,true);
    document.addEventListener('keydown',gesture,true);
    button.onclick=()=>{
      if(armed){play();return}
      muted=!muted;
      if(muted){cancelAnimationFrame(frame);audio.pause();playing=false}
      update();
      if(!muted)play();
    };
    const stopOnPlay=(event)=>{
      if(event.target?.closest?.('#play-movie,#resume-movie,#series-play-button,#series-shuffle-button,#season-play-button,.season-episode-tile,#trailer-movie,.tv-trailer-launch')){
        stop(true);
      }
    };
    document.addEventListener('click',stopOnPlay,true);
    const stopOnExit=()=>stop(false);
    window.addEventListener('pagehide',stopOnExit,{once:true});
    active={stop:immediate=>{
      document.removeEventListener('click',stopOnPlay,true);
      window.removeEventListener('pagehide',stopOnExit);
      stop(immediate);
    }};
    await play();
  }
  window.WillieThemeMusic={attach,stop:(immediate=true)=>active?.stop(immediate)};
})();
