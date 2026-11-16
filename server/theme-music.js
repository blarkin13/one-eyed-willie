/* Background audio from a user's own local theme file, never external streams. */
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
    if(!found.available||!found.url||!preferences[kind==='tv'?'tv_theme_music':'movie_theme_music'])return;
    const audio=new Audio();
    audio.src=found.url;
    audio.volume=0;
    audio.preload='none';
    audio.loop=!!preferences.theme_loop;
    const volume=Math.max(0,Math.min(1,(Number(preferences.theme_volume)||0)/100));
    const fade=!!preferences.theme_fade&&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let muted=false,disposed=false,frame=0,armed=false;
    const button=document.createElement('button');
    button.type='button';button.className='media-icon-action theme-music-toggle';
    const update=()=>{
      button.innerHTML=icon(muted);
      button.title=muted?'Unmute theme music':'Mute theme music';
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
        if(fade)ramp(volume,650);
      }catch(_){
        // Browser autoplay is frequently restricted: try again on user gesture.
        armed=true;
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
      muted=!muted;update();
      if(muted){cancelAnimationFrame(frame);audio.pause()}
      else play();
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
