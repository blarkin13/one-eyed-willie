/* Shared compact navigation and branding for every One-Eyed Willie page. */
document.addEventListener('DOMContentLoaded', () => {
  const target=document.getElementById('app-nav');
  if(!target)return;
  const page=document.body.dataset.page||'home';
  const inSettings=['libraries','remote','metadata','connections','maintenance','playback'].includes(page);
  const active=inSettings?'settings':page;
  const navItems=[
    {id:'home',href:'/',name:'Home',fa:'fa-house',fallback:'home'},
    {id:'movies',href:'/movies',name:'Movies',fa:'fa-film',fallback:'film'},
    {id:'tv',href:'/tv',name:'TV Shows',fa:'fa-tv',fallback:'tv'},
    {id:'settings',href:'/settings/libraries',name:'Settings',fa:'fa-gear',fallback:'settings'}
  ];
  // Inline SVG fallbacks make every control usable without an external font.
  const paths={
    home:'<path d="M3 10.5 12 3l9 7.5V21h-6v-7H9v7H3z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    film:'<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M7 4v16M17 4v16M3 9h4m-4 6h4m10-6h4m-4 6h4" stroke="currentColor" stroke-width="1.5" fill="none"/>',
    tv:'<rect x="3" y="5" width="18" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M9 21h6m-3-3v3m-5-11 3 3 6-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
    compass:'<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
    settings:'<path d="M12 3v2m0 14v2M4.9 4.9l1.5 1.5m11.2 11.2 1.5 1.5M3 12h2m14 0h2M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m15.1 15.1 5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    chevron:'<path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
  };
  function glyph(fa,svg){
    const icon=document.createElement('span');icon.className='nav-icon';icon.setAttribute('aria-hidden','true');
    const font=document.createElement('i');font.className='fa-solid '+fa;
    const fallback=document.createElementNS('http://www.w3.org/2000/svg','svg');
    fallback.setAttribute('viewBox','0 0 24 24');fallback.classList.add('fa-fallback');
    fallback.innerHTML=paths[svg];icon.append(font,fallback);
    return icon;
  }
  // Logo anchors the upper-left corner on desktop and mobile.
  const brand=document.createElement('a');brand.href='/';brand.className='brand';brand.setAttribute('aria-label','One-Eyed Willie — Home');
  brand.title='One-Eyed Willie';
  // Pirate ship logo; the original skull artwork remains the media watermark.
  const logoFrame=document.createElement('span');logoFrame.className='brand-logo-frame';
  logoFrame.setAttribute('aria-hidden','true');
  const image=document.createElement('img');image.className='brand-logo';image.src='/assets/ship-logo.png';
  image.alt='';image.width=90;image.height=90;
  logoFrame.append(image);
  const words=document.createElement('span');words.className='brand-name';words.textContent='One-eyed Willie';
  brand.append(logoFrame,words);target.append(brand);
  const nav=document.createElement('nav');nav.className='side-nav';nav.setAttribute('aria-label','Main navigation');
  navItems.forEach(item=>{
    const a=document.createElement('a');a.href=item.href;a.title=item.name;
    a.className='nav-link';a.setAttribute('aria-label',item.name);
    if(item.id===active)a.setAttribute('aria-current','page');
    a.append(glyph(item.fa,item.fallback));
    const caption=document.createElement('span');caption.className='nav-text';caption.textContent=item.name;a.append(caption);
    nav.append(a);
  });target.append(nav);
  // Each configured library has its own entry in addition to the combined Movies/TV views.
  // Read from the live server so newly created libraries appear without hardcoded names.
  fetch('/api/libraries',{cache:'no-store'}).then(response=>{
    if(!response.ok)throw Error('Libraries unavailable');
    return response.json();
  }).then(libraries=>{
    if(!Array.isArray(libraries))return;
    const selected=new URLSearchParams(location.search).get('library_id');
    for(const library of libraries){
      if(!Number.isInteger(library.id)||!['movies','tv'].includes(library.kind))continue;
      const name=String(library.name||'').trim().slice(0,80);
      if(!name)continue;
      // The combined Movies and TV Shows links already represent standard libraries.
      // Show only separately named collections, e.g. Horror, as additional entries.
      const normalized=name.toLocaleLowerCase().replace(/[^a-z0-9]/g,'');
      if((library.kind==='movies'&&normalized==='movies')||
         (library.kind==='tv'&&(normalized==='tvshows'||normalized==='tv')))continue;
      const url=new URLSearchParams({library_id:String(library.id)});
      const link=document.createElement('a');
      link.href=(library.kind==='tv'?'/tv':'/movies')+'?'+url;
      link.title=name;link.setAttribute('aria-label',name+' library');
      link.className='nav-link library-nav-link';
      if(selected===String(library.id)&&(page==='movies'||page==='tv'))link.setAttribute('aria-current','page');
      // Distinctive initial makes custom collections identifiable with the sidebar collapsed.
      const icon=document.createElement('span');
      icon.className='nav-icon library-initial';
      icon.setAttribute('aria-hidden','true');
      icon.textContent=Array.from(name)[0].toUpperCase();
      link.append(icon);
      const caption=document.createElement('span');caption.className='nav-text';caption.textContent=name;link.append(caption);
      // Keep custom collections alongside Movies/TV Shows, not after Settings.
      const settingsLink=nav.querySelector('a[href="/settings/libraries"]');
      nav.insertBefore(link,settingsLink);
    }
  }).catch(()=>{});
  if(inSettings){
    const subnav=document.createElement('nav');subnav.className='settings-shortcuts';
    subnav.setAttribute('aria-label','Settings sections');
    [['libraries','/settings/libraries','Libraries'],['playback','/settings/playback','Playback'],['remote','/settings/remote','Remote Access'],['metadata','/settings/metadata','Metadata'],['connections','/settings/connections','Connections'],['maintenance','/settings/maintenance','Maintenance']].forEach(([id,href,name])=>{
      const a=document.createElement('a');a.href=href;a.title=name;a.textContent=name;
      if(page===id)a.setAttribute('aria-current','page');
      subnav.append(a);
    });target.append(subnav);
  }
  if(!document.querySelector('link[rel~="icon"]')){
    const favicon=document.createElement('link');
    favicon.rel='icon';favicon.type='image/png';favicon.href='/assets/favicon.png?v=5';
    document.head.append(favicon);
  }
  // Use Font Awesome Free when loaded; keep local SVGs when offline.
  if(document.fonts&&document.fonts.load){
    document.fonts.load('900 16px "Font Awesome 6 Free"').then(faces=>{
      if(faces.length&&faces.some(face=>face.status==='loaded')){
        document.documentElement.classList.add('fontawesome-ready');
      }
    }).catch(()=>{});
  }
  // Keep the default artwork visible if a remote poster fails to load.
  document.addEventListener('error', event => {
    const img=event.target;
    if(!(img instanceof HTMLImageElement))return;
    if(img.classList.contains('poster-image')){
      img.remove(); // Exposes the poster placeholder background on the parent card.
    }else if(['hero-poster','movie-detail-poster','explore-poster'].some(cls=>img.classList.contains(cls))){
      if(!img.src.endsWith('/assets/poster-placeholder.jpg'))img.src='/assets/poster-placeholder.jpg';
    }
  },true);
  // Make the hover-expanded icon rail keyboard-accessible too.
  target.querySelectorAll('.nav-link').forEach(link=>{
    link.addEventListener('focus',()=>target.classList.add('nav-focused'));
    link.addEventListener('blur',()=>target.classList.remove('nav-focused'));
  });
});


/* Interactive cinematic backdrop on Home, library catalogs and Explore.
 * Only the active hovered/focused title fetches metadata, with a short delay
 * and a bounded cache. The app remains readable under a permanent dark veil. */
document.addEventListener('DOMContentLoaded',()=>{
  if(!['home','movies','tv','explore'].includes(document.body.dataset.page))return;
  const backdrop=document.createElement('div');
  backdrop.className='willie-hover-backdrop';
  backdrop.setAttribute('aria-hidden','true');
  const layers=[document.createElement('div'),document.createElement('div')];
  for(const layer of layers){layer.className='willie-hover-backdrop-layer';backdrop.append(layer)}
  document.body.prepend(backdrop);
  const cache=new Map();
  let active=null,showTimer=null,hideTimer=null,generation=0,visible=-1,currentUrl='';
  const valid=url=>typeof url==='string'&&(
    url.startsWith('/api/artwork/')||url.startsWith('https://image.tmdb.org/t/p/'));
  function clear(){
    generation++;active=null;currentUrl='';visible=-1;
    for(const layer of layers)layer.classList.remove('is-visible');
  }
  function cancel(){clearTimeout(showTimer);clearTimeout(hideTimer)}
  async function lookup(element){
    const direct=element.dataset.hoverBackdrop;
    if(valid(direct))return direct;
    const exploreProvider=element.dataset.hoverExploreProvider;
    if(['radarr','sonarr'].includes(exploreProvider)){
      const identity='explore|'+exploreProvider+'|'+(element.dataset.hoverTmdbId||element.dataset.hoverTitle||'')+'|'+(element.dataset.hoverYear||'');
      if(cache.has(identity))return cache.get(identity);
      const query=new URLSearchParams();
      if(/^\d+$/.test(element.dataset.hoverTmdbId||''))query.set('tmdb_id',element.dataset.hoverTmdbId);
      else{
        if(!element.dataset.hoverTitle)return null;
        query.set('title',element.dataset.hoverTitle);
        if(element.dataset.hoverYear)query.set('year',element.dataset.hoverYear);
      }
      const promise=fetch('/api/arr/'+exploreProvider+'/detail?'+query,{cache:'default'})
        .then(response=>response.ok?response.json():null)
        .then(data=>valid(data?.backdrop_url)?data.backdrop_url:null)
        .catch(()=>null);
      cache.set(identity,promise);
      if(cache.size>90)cache.delete(cache.keys().next().value);
      return promise;
    }
    const kind=element.dataset.hoverKind;
    const id=element.dataset.hoverLibraryId;
    const key=element.dataset.hoverKey;
    if(!['tv','movies'].includes(kind)||!/^\d+$/.test(id||'')||!key)return null;
    const identity=kind+'|'+id+'|'+key;
    if(cache.has(identity))return cache.get(identity);
    const query=new URLSearchParams({library_id:id,key});
    const url=kind==='tv'?'/api/tv/show?'+query:'/api/movies/details?'+query;
    const promise=fetch(url,{cache:'default'}).then(response=>{
      if(!response.ok)throw Error('Backdrop unavailable');
      return response.json();
    }).then(data=>valid(data.backdrop_url)?data.backdrop_url:null).catch(()=>null);
    cache.set(identity,promise);
    if(cache.size>90)cache.delete(cache.keys().next().value);
    return promise;
  }
  function apply(url,serial){
    if(serial!==generation)return;
    if(!valid(url)){clear();return}
    if(currentUrl===url)return;
    const img=new Image();
    img.onload=()=>{
      if(serial!==generation)return;
      const index=visible===0?1:0;
      layers[index].style.backgroundImage='url("'+url+'")';
      layers[index].classList.add('is-visible');
      layers[1-index].classList.remove('is-visible');
      visible=index;currentUrl=url;
    };
    img.onerror=()=>{if(serial===generation)clear()};
    img.src=url;
  }
  function select(element){
    if(element===active)return;
    cancel();
    active=element;const serial=++generation;
    if(!element){clear();return}
    showTimer=setTimeout(async()=>{
      const url=await lookup(element);
      if(serial!==generation)return;
      apply(url,serial);
    },180);
  }
  const locate=target=>target instanceof Element?
    target.closest('[data-hover-kind],[data-hover-backdrop]'):null;
  document.addEventListener('pointerover',event=>{
    const element=locate(event.target);
    if(element)select(element);
  });
  document.addEventListener('pointerout',event=>{
    const element=locate(event.target);
    if(!element||element!==active)return;
    if(event.relatedTarget instanceof Node&&element.contains(event.relatedTarget))return;
    cancel();
    hideTimer=setTimeout(()=>{
      const focused=locate(document.activeElement);
      if(focused&&focused.isConnected)select(focused);
      else select(null);
    },130);
  });
  document.addEventListener('focusin',event=>{
    const element=locate(event.target);
    if(element)select(element);
  });
  document.addEventListener('focusout',event=>{
    const element=locate(event.target);
    if(!element||active!==element)return;
    hideTimer=setTimeout(()=>{
      const focused=locate(document.activeElement);
      if(focused&&focused.isConnected)select(focused);
      else select(null);
    },140);
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)select(null)});
});
