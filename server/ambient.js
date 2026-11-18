/* One-Eyed Willie ambient particles: browser and Google TV WebView.
 * No library dependency, no hit testing, bounded canvas work and no playback.
 */
(() => {
  if (window.WillieAmbient) return;
  const valid = new Set(['off','snow','rain','leaves','fireflies']);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const tv = /(Android|Google TV)/i.test(navigator.userAgent);
  const defaults = {effect:'off', intensity:10, speed:'normal', layer:'foreground'};
  let settings = {...defaults}, canvas=null, ctx=null, frame=0;
  let particles=[], width=0, height=0, last=0, running=false, stopped=false;
  let previousTime=0;
  const speedMap={slow:.55,normal:1,fast:1.65};
  const rand=(min,max)=>min+Math.random()*(max-min);
  const suppress=()=>document.hidden||reduced.matches||!!document.fullscreenElement||
    !!document.querySelector('.willie-player')||
    document.body?.classList.contains('willie-player-open');
  function normalize(input) {
    const raw={...defaults,...input};
    return {
      effect: valid.has(raw.effect)?raw.effect:'off',
      intensity:Math.min(100,Math.max(10,Math.round(Number(raw.intensity)||10))),
      speed: Object.hasOwn(speedMap,raw.speed)?raw.speed:'normal',
      layer: raw.layer==='background'?'background':'foreground'
    };
  }
  function size() {
    if (!canvas||!ctx) return;
    const dpr=Math.min(window.devicePixelRatio||1, tv?1.25:1.6);
    width=window.innerWidth;height=window.innerHeight;
    canvas.width=Math.max(1,Math.ceil(width*dpr));
    canvas.height=Math.max(1,Math.ceil(height*dpr));
    ctx.setTransform(dpr,0,0,dpr,0,0);
    regenerate();
  }
  function particle(randomY=true) {
    const p={x:rand(0,width),y:randomY?rand(0,height):rand(-35,-2),
      phase:rand(0,Math.PI*2),size:rand(1.2,3.2),rate:rand(.4,1.3),
      drift:rand(-.35,.35),spin:rand(-.015,.015),rotation:rand(0,6.28),
      color: ['#d9a34f','#c66a36','#ecbb6e','#a94b2b'][Math.floor(rand(0,4))]};
    if(settings.effect==='rain'){
      p.size=rand(7,16);p.rate=rand(4,8);p.drift=-1.2;
    }else if(settings.effect==='leaves'){
      p.size=rand(5,9);p.rate=rand(.5,1.35);
    }else if(settings.effect==='fireflies'){
      p.size=rand(1.2,3.1);p.rate=rand(.1,.33);
      p.y=rand(height*.1,height*.9);
    }
    return p;
  }
  function regenerate(){
    const area=Math.max(0,width*height);
    const scale=settings.intensity/100;
    const weight={snow:1.2,rain:2.2,leaves:.55,fireflies:.36};
    const cap=tv?90:170;
    const desired=settings.effect==='off'?0:
      Math.max(2,Math.round(area/2900*scale*(weight[settings.effect]||1)));
    particles=Array.from({length:Math.min(cap,desired)},()=>particle());
  }
  function draw(now){
    if(!ctx||!canvas)return;
    const dt=Math.min(2.3,Math.max(.2,(now-last)/16.666||1));
    last=now;
    ctx.clearRect(0,0,width,height);
    const multi=dt*speedMap[settings.speed];
    const effect=settings.effect;
    for(let i=0;i<particles.length;i++){
      const p=particles[i];p.phase+=.022*multi;p.rotation+=p.spin*multi;
      if(effect==='snow'){
        p.y+=p.rate*multi;
        p.x+=(Math.sin(p.phase)*.42+p.drift*.2)*multi;
        ctx.fillStyle='rgba(242,249,255,.83)';
        ctx.beginPath();ctx.arc(p.x,p.y,p.size,0,Math.PI*2);ctx.fill();
      }else if(effect==='rain'){
        p.y+=p.rate*multi;p.x-=1.1*multi;
        ctx.strokeStyle='rgba(180,215,249,.48)';ctx.lineWidth=.9;
        ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+2.6,p.y-p.size);ctx.stroke();
      }else if(effect==='leaves'){
        p.y+=p.rate*multi;
        p.x+=(Math.sin(p.phase)*1.05+p.drift)*multi;
        ctx.save();ctx.translate(p.x,p.y);
        ctx.rotate(p.rotation+Math.sin(p.phase)*.5);
        ctx.scale(.7+.3*Math.cos(p.phase),1);
        ctx.beginPath();ctx.moveTo(0,-p.size);
        ctx.quadraticCurveTo(p.size,-p.size*.4,0,p.size);
        ctx.quadraticCurveTo(-p.size,p.size*.4,0,-p.size);
        ctx.fillStyle=p.color;ctx.globalAlpha=.83;ctx.fill();ctx.restore();
      }else if(effect==='fireflies'){
        p.x+=Math.cos(p.phase)*p.rate*multi;
        p.y+=Math.sin(p.phase*.8)*p.rate*multi;
        const alpha=(1+Math.sin(now*.002+p.rotation))* .35+.1;
        // Simple circles avoid expensive gradients on low-power TV GPUs.
        ctx.fillStyle='rgba(229,255,128,'+alpha+')';
        ctx.beginPath();ctx.arc(p.x,p.y,p.size*2.2,0,Math.PI*2);ctx.fill();
        ctx.fillStyle='rgba(255,255,204,'+Math.min(1,alpha+.2)+')';
        ctx.beginPath();ctx.arc(p.x,p.y,p.size*.75,0,Math.PI*2);ctx.fill();
      }
      if(p.y>height+20||p.x>width+20||p.x< -25)particles[i]=particle(false);
    }
  }
  function loop(now){
    frame=0;
    if(!running||stopped)return;
    // Google TV uses 30 fps, other devices 45 fps maximum.
    if(now-previousTime>=(tv?32:21)){
      draw(now);previousTime=now;
    }
    frame=requestAnimationFrame(loop);
  }
  function sync(){
    if(!canvas)return;
    const show=settings.effect!=='off'&&!suppress();
    canvas.hidden=!show;
    canvas.style.zIndex=settings.layer==='background'?'0':'700';
    if(show&&!running){
      running=true;last=performance.now();previousTime=0;
      frame=requestAnimationFrame(loop);
    }else if(!show&&running){
      running=false;cancelAnimationFrame(frame);frame=0;
      ctx?.clearRect(0,0,width,height);
    }
  }
  function update(next){
    settings=normalize(next);
    regenerate();sync();
    document.dispatchEvent(new CustomEvent('willie:ambient-updated',{detail:{...settings}}));
  }
  async function load(){
    try{
      const response=await fetch('/api/settings/ambient',{cache:'no-store'});
      if(response.ok)update(await response.json());
    }catch(_){/* Off by default; network failures must not affect navigation. */}
  }
  function init(){
    if(!document.body||canvas)return;
    canvas=document.createElement('canvas');ctx=canvas.getContext('2d',{alpha:true});
    if(!ctx)return;
    canvas.id='willie-ambient-effects';canvas.setAttribute('aria-hidden','true');
    canvas.style.cssText='position:fixed;inset:0;width:100%;height:100%;pointer-events:none;'+
      'display:block;contain:strict;z-index:700';
    canvas.hidden=true;
    document.body.append(canvas);
    size();
    window.addEventListener('resize',size,{passive:true});
    document.addEventListener('visibilitychange',sync);
    document.addEventListener('fullscreenchange',sync);
    if(reduced.addEventListener)reduced.addEventListener('change',sync);
    // Web player is inserted/removed at body level.
    const observer=new MutationObserver(sync);
    observer.observe(document.body,{childList:true});
    window.addEventListener('pagehide',()=>{
      stopped=true;running=false;cancelAnimationFrame(frame);
      observer.disconnect();
    },{once:true});
    load();
  }
  window.WillieAmbient={
    preview:next=>update({...settings,...next}),
    refresh:load,
    current:()=>({...settings})
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
