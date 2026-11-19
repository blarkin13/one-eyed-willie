/* At a Glance: independent Clock, Weather and News widgets in the Yarr Media
 * browser, Google TV WebView, player pause screen and idle screensaver.
 * The native Media3 player renders its own pause cards from the same API.
 */
(() => {
  'use strict';
  const names=['clock','weather','news'];
  const friendly={clock:'Clock',weather:'Weather',news:'News'};
  const css=`
.yarr-glance-strip{display:flex;align-items:stretch;flex-wrap:wrap;gap:10px;
 margin:8px 0 16px;max-width:100%;padding-right:clamp(16px,4vw,55px)}
.yarr-glance-card{box-sizing:border-box;min-width:160px;max-width:390px;flex:1 1 190px;
 padding:12px 16px;border-radius:12px;background:#080808;color:#f6f3ed;
 border:1px solid #444;line-height:1.3;font:inherit}
.yarr-glance-label{font-weight:800;text-transform:uppercase;letter-spacing:.12em;
 font-size:11px;color:#cecece;margin-bottom:6px}
.yarr-glance-value{font-size:clamp(20px,2vw,28px);font-weight:800;
 font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.yarr-glance-detail{font-size:12px;font-weight:550;color:#c5c5c5;line-height:1.55;margin-top:4px}
.yarr-glance-card a{color:#f5f5f5;text-decoration:underline;text-underline-offset:3px}
.yarr-glance-card a:focus-visible{outline:2px solid var(--oew-tv-select-color,#A61E1E);outline-offset:3px}
.yarr-glance-card[data-name=news] .yarr-glance-value{font-size:15px;line-height:1.4}
.yarr-glance-card[data-name=news] .yarr-glance-detail{font-size:11px}
.yarr-glance-pause{position:absolute;z-index:11;top:clamp(190px,25vh,290px);
 right:clamp(15px,3vw,50px);left:auto;max-width:min(420px,46vw);
 display:flex;flex-direction:column;pointer-events:none;gap:7px;margin:0;padding:0}
.yarr-glance-pause .yarr-glance-card{width:100%;min-width:0;max-width:100%;
 flex:0 0 auto;padding:10px 14px;pointer-events:auto}
.yarr-glance-pause[hidden]{display:none!important}
.yarr-glance-idle{position:fixed;inset:0;z-index:9000;background:#050505;
 color:white;display:flex;align-items:center;justify-content:center;padding:clamp(25px,5vw,80px);
 box-sizing:border-box;cursor:default}
.yarr-glance-idle[hidden]{display:none!important}
.yarr-glance-idle-body{width:min(1200px,100%);display:flex;flex-direction:column;gap:30px}
.yarr-glance-idle-title{font-size:clamp(14px,2vw,23px);font-weight:750;
 letter-spacing:.2em;text-transform:uppercase;color:#a8a8a8}
.yarr-glance-idle .yarr-glance-strip{padding:0;margin:0;gap:18px}
.yarr-glance-idle .yarr-glance-card{padding:22px 26px;flex:1 1 280px;max-width:none;background:#0d0d0d}
.yarr-glance-idle .yarr-glance-value{font-size:clamp(28px,4vw,52px)}
.yarr-glance-idle .yarr-glance-card[data-name=news] .yarr-glance-value{font-size:clamp(17px,2vw,29px)}
.yarr-glance-idle-hint{font-size:13px;color:#aaa}
@media(max-width:700px){.yarr-glance-pause{left:12px;right:12px;top:125px;max-width:none}
 .yarr-glance-pause .yarr-glance-card{min-width:0}
 .yarr-glance-strip .yarr-glance-card{flex:1 1 155px}
 .yarr-glance-idle{padding:24px}}
@media(prefers-reduced-motion:reduce){.yarr-glance-idle{transition:none}}
`;
  const style=document.createElement('style');style.textContent=css;document.head.append(style);
  let settingsPromise=null;
  const getSettings=()=>settingsPromise||(settingsPromise=fetch('/api/glance/settings',
    {cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Integration settings unavailable');return r.json()})
      .then(v=>v.integrations||{}).catch(()=>({})));
  const asText=(value,max=160)=>String(value??'').slice(0,max);
  const add=(parent,tag,cls,text)=>{
    const el=document.createElement(tag);el.className=cls;
    if(text!==undefined)el.textContent=asText(text);parent.append(el);return el;
  };
  const fmtClock=config=>{
    try {
      const zone=config.clock_zone==='local'?undefined:config.clock_zone;
      return new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',
        second:'2-digit',hour12:config.clock_format!=='24h',timeZone:zone}).format(new Date());
    }catch(_){return new Date().toLocaleTimeString();}
  };
  const fmtDate=config=>{
    try{return new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',
      timeZone:config.clock_zone==='local'?undefined:config.clock_zone}).format(new Date());}
    catch(_){return '';}
  };
  async function loadData(name,value,detail){
    try {
      const response=await fetch('/api/glance/'+name,{cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(data.detail||'Provider unavailable');
      if(!value.isConnected)return;
      if(name==='weather'){
        value.textContent=asText(data.period)+' · '+asText(data.temperature,6)+'°'+asText(data.unit,2);
        detail.textContent=asText(data.location)+' · '+asText(data.conditions);
        detail.append(document.createTextNode(' · '));
        const link=document.createElement('a');link.href='https://www.weather.gov/';
        link.textContent='NWS';link.target='_blank';link.rel='noopener noreferrer';detail.append(link);
      }else if(name==='news'){
        const headline=data.headlines?.[0];
        value.replaceChildren();
        if(headline&&/^https:\/\//.test(headline.url)){
          const link=document.createElement('a');link.href=headline.url;
          link.rel='noopener noreferrer';link.target='_blank';
          link.textContent=asText(headline.title,180);value.append(link);
          detail.textContent=asText(data.source)+' · Headlines · Open article';
        }else throw Error('No headlines available');
      }
    }catch(error){
      if(value.isConnected){value.textContent=name==='weather'?'Weather unavailable':'News unavailable';
        detail.textContent=asText(error.message,120);}
    }
  }
  function makeCard(name,config){
    const card=document.createElement('article');card.className='yarr-glance-card';card.dataset.name=name;
    add(card,'div','yarr-glance-label',friendly[name]);
    const value=add(card,'div','yarr-glance-value');
    const detail=add(card,'div','yarr-glance-detail');
    if(name==='clock'){
      const update=()=>{if(!card.isConnected)return;value.textContent=fmtClock(config);detail.textContent=fmtDate(config);};
      update(); // Initial update runs again once the card enters the DOM.
      card._glanceUpdate=update;
    }else if(name==='weather'){
      value.textContent=config.zip_code?'Loading forecast…':'ZIP code required';
      detail.textContent=config.zip_code?'NWS forecast':'Set a US ZIP under Settings → Integrations';
      if(config.zip_code)card._glanceLoad=()=>loadData(name,value,detail);
    }else{
      value.textContent='Loading headlines…';
      detail.textContent='Headlines with source attribution';
      card._glanceLoad=()=>loadData(name,value,detail);
    }
    return card;
  }
  async function createStrip(where){
    const config=await getSettings();
    const active=names.filter(name=>config[name]?.enabled&&config[name][where]);
    if(!active.length)return null;
    const strip=document.createElement('div');strip.className='yarr-glance-strip';
    for(const name of active)strip.append(makeCard(name,config[name]));
    return strip;
  }
  function activate(strip){
    if(!strip)return;
    for(const card of strip.querySelectorAll('.yarr-glance-card')){
      card._glanceUpdate?.();card._glanceLoad?.();
    }
  }
  async function home(){
    const main=document.querySelector('body[data-page="home"] main.content');
    if(!main)return;
    const strip=await createStrip('home');
    if(!strip||!main.isConnected)return;
    const status=main.querySelector('#status');
    if(status)status.after(strip);else main.prepend(strip);
    activate(strip);
    // The Home clock stays live; refreshed headlines/forecasts never require
    // reloading the page or disturb poster focus.
    const clockTick=setInterval(()=>{
      if(!strip.isConnected){clearInterval(clockTick);return}
      if(!document.hidden)for(const card of strip.children)card._glanceUpdate?.();
    },1000);
    const dataTick=setInterval(()=>{
      if(!strip.isConnected){clearInterval(dataTick);return}
      if(!document.hidden)for(const card of strip.children)card._glanceLoad?.();
    },300000);
  }
  async function pause(surface){
    const video=surface.querySelector('video');
    if(!video)return;
    const strip=await createStrip('pause');
    if(!strip||!surface.isConnected)return;
    strip.classList.add('yarr-glance-pause');strip.hidden=true;
    surface.append(strip);activate(strip);
    function update(){
      const shouldShow=surface.isConnected&&video.paused&&!video.ended&&video.readyState>=2;
      strip.hidden=!shouldShow;
      if(shouldShow)for(const card of strip.children)card._glanceUpdate?.();
    }
    video.addEventListener('pause',update);
    video.addEventListener('playing',update);
    video.addEventListener('ended',update);
    const tick=setInterval(()=>{
      if(!surface.isConnected){clearInterval(tick);return}
      update();
    },1000);
    update();
  }
  async function idle(){
    if(!document.querySelector('body[data-page] .app-shell'))return;
    const config=await getSettings();
    if(config.ambient?.enabled===false)return;
    const delayMs=Math.max(60000,Math.min(600000,
      Number(config.ambient?.idle_timeout_seconds||120)*1000));
    const strip=await createStrip('idle');
    if(!strip)return;
    const overlay=document.createElement('div');
    overlay.className='yarr-glance-idle';overlay.hidden=true;
    overlay.setAttribute('aria-label','At a Glance idle screen');
    const body=document.createElement('div');body.className='yarr-glance-idle-body';
    add(body,'div','yarr-glance-idle-title','Yarr Media · At a Glance');
    body.append(strip);add(body,'div','yarr-glance-idle-hint','Press a remote button or move the mouse to return');
    overlay.append(body);document.body.append(overlay);activate(strip);
    let timer=null;
    function shouldSkip(){
      if(document.hidden||document.querySelector('.willie-player')||
         document.querySelector('dialog[open]')||
         document.activeElement?.matches('input,textarea,select,[contenteditable="true"]'))return true;
      return [...document.querySelectorAll('video')].some(v=>!v.paused&&!v.ended);
    }
    function schedule(){
      clearTimeout(timer);
      timer=setTimeout(()=>{
        if(shouldSkip()){schedule();return;}
        overlay.hidden=false;
        for(const card of strip.children){card._glanceUpdate?.();card._glanceLoad?.();}
      },delayMs);
    }
    function activity(event){
      if(!overlay.hidden){
        overlay.hidden=true;
        if(event.type==='keydown'){event.preventDefault();event.stopImmediatePropagation();}
      }
      schedule();
    }
    for(const type of ['keydown','pointerdown','pointermove','wheel','touchstart']){
      document.addEventListener(type,activity,true);
    }
    document.addEventListener('visibilitychange',()=>{
      if(document.hidden){overlay.hidden=true;clearTimeout(timer);}
      else schedule();
    });
    const tick=setInterval(()=>{
      if(!overlay.isConnected){clearInterval(tick);return}
      if(!overlay.hidden)for(const card of strip.children)card._glanceUpdate?.();
    },1000);
    schedule();
  }
  window.YarrGlance={mountPause:pause,refreshSettings:()=>{settingsPromise=null}};
  window.dispatchEvent(new Event('yarr:glance-ready'));
  if(document.readyState==='loading')
    document.addEventListener('DOMContentLoaded',()=>{home();idle();},{once:true});
  else {home();idle();}
})();
