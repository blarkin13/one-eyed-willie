/* Shared compact navigation and branding for every One-Eyed Willie page. */
document.addEventListener('DOMContentLoaded', () => {
  const target=document.getElementById('app-nav');
  if(!target)return;
  const page=document.body.dataset.page||'home';
  const inSettings=['settings','general','appearance','libraries','remote','metadata','connections','maintenance','playback'].includes(page);
  const active=page==='connectionshub'?'connections':inSettings?'settings':page;
  const navItems=[
    {id:'home',href:'/',name:'Home',fa:'fa-house',fallback:'home'},
    {id:'movies',href:'/movies',name:'Movies',fa:'fa-film',fallback:'film'},
    {id:'tv',href:'/tv',name:'TV Shows',fa:'fa-tv',fallback:'tv'},
    {id:'connections',href:'/connections',name:'Connections',fa:'fa-plug',fallback:'connections'},
    {id:'settings',href:'/settings',name:'Settings',fa:'fa-gear',fallback:'settings'}
  ];
  // Inline SVG fallbacks make every control usable without an external font.
  const paths={
    home:'<path d="M3 10.5 12 3l9 7.5V21h-6v-7H9v7H3z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    film:'<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M7 4v16M17 4v16M3 9h4m-4 6h4m10-6h4m-4 6h4" stroke="currentColor" stroke-width="1.5" fill="none"/>',
    tv:'<rect x="3" y="5" width="18" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M9 21h6m-3-3v3m-5-11 3 3 6-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
    compass:'<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
    settings:'<path d="M12 3v2m0 14v2M4.9 4.9l1.5 1.5m11.2 11.2 1.5 1.5M3 12h2m14 0h2M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m15.1 15.1 5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    chevron:'<path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    services:'<rect x="3" y="3" width="8" height="8" rx="1.7" stroke="currentColor" stroke-width="1.8" fill="none"/><rect x="13" y="3" width="8" height="8" rx="1.7" stroke="currentColor" stroke-width="1.8" fill="none"/><rect x="3" y="13" width="8" height="8" rx="1.7" stroke="currentColor" stroke-width="1.8" fill="none"/><rect x="13" y="13" width="8" height="8" rx="1.7" stroke="currentColor" stroke-width="1.8" fill="none"/>',
    radarr:'<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="4.8" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/>',
    sonarr:'<path d="M3 12c3-6 6 6 9 0s6-6 9 0M3 17c3-6 6 6 9 0s6-6 9 0M3 7c3-6 6 6 9 0s6-6 9 0" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/>',
    connections:'<path d="M8 3v6m8-6v6M5 9h14v3a7 7 0 0 1-6 6v3h-2v-3a7 7 0 0 1-6-6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    sabnzbd:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
  };
  // Font Awesome Free is the Clean theme's default icon set.
  // A local SVG fallback keeps navigation usable if the font CDN is unavailable.
  window.WillieCleanIcons={
    names:{
      home:['fa-house','home'],movies:['fa-film','film'],tv:['fa-tv','tv'],
      connections:['fa-plug','connections'],sabnzbd:['fa-download','sabnzbd'],
      settings:['fa-gear','settings']
    },
    create(name,size=30){
      const [fa,key]=this.names[name]||this.names.settings;
      const wrap=document.createElement('span');
      wrap.className='nav-icon nav-clean-icon';
      wrap.setAttribute('aria-hidden','true');
      wrap.style.fontSize=size+'px';
      const font=document.createElement('i');
      font.className='fa-solid '+fa;
      const fallback=document.createElementNS('http://www.w3.org/2000/svg','svg');
      fallback.setAttribute('viewBox','0 0 24 24');
      fallback.classList.add('fa-fallback');
      fallback.setAttribute('width',String(size));
      fallback.setAttribute('height',String(size));
      fallback.innerHTML=paths[key]||paths.settings;
      wrap.append(font,fallback);
      return wrap;
    },
    // Custom libraries use the Font Awesome equivalent of their selected icon.
    // Their original icon selection and uploaded artwork are retained for Pirate.
    libraryIcons:{
      film:'fa-film',tv:'fa-tv',folder:'fa-folder',clapperboard:'fa-clapperboard',
      play:'fa-play',reel:'fa-film',popcorn:'fa-bowl-food',ticket:'fa-ticket',
      camera:'fa-camera',video:'fa-video',headphones:'fa-headphones',music:'fa-music',
      star:'fa-star',heart:'fa-heart',ghost:'fa-ghost',skull:'fa-skull',
      pumpkin:'fa-face-grin',flame:'fa-fire',zap:'fa-bolt',rocket:'fa-rocket',
      planet:'fa-earth-americas',robot:'fa-robot',alien:'fa-user-astronaut',
      wand:'fa-wand-magic-sparkles',sword:'fa-shield-halved',crown:'fa-crown',
      shield:'fa-shield',smile:'fa-face-smile',drama:'fa-masks-theater',
      eye:'fa-eye',fingerprint:'fa-fingerprint',trophy:'fa-trophy',
      gamepad:'fa-gamepad',book:'fa-book',archive:'fa-box-archive',
      layers:'fa-layer-group',grid:'fa-table-cells',bookmark:'fa-bookmark',
      gem:'fa-gem',award:'fa-award',clock:'fa-clock',calendar:'fa-calendar',
      hourglass:'fa-hourglass',search:'fa-magnifying-glass',map:'fa-map',
      compass:'fa-compass',globe:'fa-globe',mountain:'fa-mountain',
      tree:'fa-tree',leaf:'fa-leaf',paw:'fa-paw',users:'fa-users',
      sun:'fa-sun',moon:'fa-moon',snowflake:'fa-snowflake',gift:'fa-gift',
      plane:'fa-plane',ship:'fa-ship',car:'fa-car',sparkles:'fa-wand-magic-sparkles'
    },
    createLibrary(name,appearance,size=24){
      const wrap=this.create('movies',size);
      wrap.classList.add('library-custom-icon');
      wrap.querySelector('i').className='fa-solid '+(this.libraryIcons[name]||'fa-folder');
      if(appearance?.icons?.[name]){
        const fallback=appearance.createIcon(name,size);
        fallback.classList.add('fa-fallback');
        fallback.setAttribute('width',String(size));
        fallback.setAttribute('height',String(size));
        wrap.querySelector('svg')?.replaceWith(fallback);
      }
      return wrap;
    }
  };
  function glyph(fa,svg){
    const icon=document.createElement('span');icon.className='nav-icon';icon.setAttribute('aria-hidden','true');
    const font=document.createElement('i');font.className='fa-solid '+fa;
    const fallback=document.createElementNS('http://www.w3.org/2000/svg','svg');
    fallback.setAttribute('viewBox','0 0 24 24');fallback.classList.add('fa-fallback');
    fallback.innerHTML=paths[svg];icon.append(font,fallback);
    return icon;
  }
  function coloredIcon(url,size=34){
    const wrap=document.createElement('span');wrap.className='nav-icon nav-colored-icon';
    wrap.setAttribute('aria-hidden','true');
    const image=document.createElement('img');image.className='sidebar-colored-image';
    image.src=url;image.alt='';image.width=size;image.height=size;
    // Keep navigation usable if a configured image fails to load.
    image.addEventListener('error',()=>{
      const fallback=glyph('fa-gear','settings');
      fallback.classList.add('nav-icon-fallback');
      wrap.replaceWith(fallback);
    },{once:true});
    wrap.append(image);return wrap;
  }
  // Clean is the default. Pirate preserves the original sidebar artwork.
  const ICON_THEME_KEY='willie-icon-theme';
  const iconTheme=()=>localStorage.getItem(ICON_THEME_KEY)==='pirate'?'pirate':'clean';
  function defaultIcon(kind){
    const safe=['home','movies','tv','connections','settings'].includes(kind)?kind:'movies';
    if(iconTheme()==='pirate')
      return coloredIcon('/assets/sidebar-icon-'+(safe==='connections'?'sabnzbd':safe)+'.png?v=pirate-v3');
    return window.WillieCleanIcons.create(safe,24);
  }
  document.documentElement.dataset.iconTheme=iconTheme();
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

  // Greet once when the desktop rail opens, not on each navigation focus step.
  // Hover and keyboard focus both open the existing CSS-driven sidebar.
  let railExpanded=false;
  const canGreet=()=>window.matchMedia('(min-width:701px)').matches;
  function updateRailGreeting(){
    const open=canGreet()&&(target.matches(':hover')||target.contains(document.activeElement));
    if(open===railExpanded)return;
    railExpanded=open;
    target.classList.toggle('brand-yarr-open',open);
  }
  target.addEventListener('pointerenter',updateRailGreeting);
  target.addEventListener('pointerleave',updateRailGreeting);
  target.addEventListener('focusin',updateRailGreeting);
  target.addEventListener('focusout',()=>{
    // The next focused item is known after the focus transition.
    requestAnimationFrame(updateRailGreeting);
  });
  window.addEventListener('resize',updateRailGreeting);
  const nav=document.createElement('nav');nav.className='side-nav';nav.setAttribute('aria-label','Main navigation');
  navItems.forEach(item=>{
    const a=document.createElement('a');a.href=item.href;a.title=item.name;
    a.className='nav-link';a.setAttribute('aria-label',item.name);
    if(item.id==='connections')a.dataset.serviceNav=item.id;
        if(item.id===active)a.setAttribute('aria-current','page');
    a.dataset.navId=item.id;
    a.append(defaultIcon(item.id));
    const caption=document.createElement('span');caption.className='nav-text';caption.textContent=item.name;a.append(caption);
    nav.append(a);
  });target.append(nav);
  // Uploaded replacements win in both themes; removing one restores the active theme.
  function updateSystemIcon(name,url,custom=false){
    const link=nav.querySelector('a[data-nav-id="'+(name==='sabnzbd'?'connections':name)+'"]');
    if(!link)return;
    const existing=link.querySelector('.nav-icon');
    if(!existing)return;
    const next=custom?coloredIcon(url):defaultIcon(name);
    existing.replaceWith(next);
  }
  fetch('/api/settings/sidebar/icons',{cache:'no-store'}).then(r=>r.ok?r.json():null)
    .then(data=>data?.icons?.forEach(icon=>{
      if(icon.custom)updateSystemIcon(icon.name,icon.url,true);
    })).catch(()=>{});
  document.addEventListener('willie:sidebar-icon-updated',event=>{
    const detail=event.detail;
    if(detail?.name)updateSystemIcon(detail.name,detail.url,Boolean(detail.custom));
  });
  // The gear is the only Settings destination in the sidebar.
  // General, Library, Metadata and Connections live on /settings only.
  // The same first-party SVG set powers the editor preview and actual sidebar.
  const appearanceReady=window.WillieLibraryAppearance
    ?Promise.resolve(window.WillieLibraryAppearance)
    :new Promise(resolve=>{
      const script=document.createElement('script');
      script.src='/assets/library-appearance.js?v=appearance-1';
      script.onload=()=>resolve(window.WillieLibraryAppearance||null);
      script.onerror=()=>resolve(null);
      document.head.append(script);
    });
  function libraryGlyph(appearance,library,isStandard=false){
    const kind=library.kind==='tv'?'tv':'movies';
    // Theme selection takes precedence for the main Movies and TV Shows links.
    // Their library image uploads and Pirate presets are used only by Pirate.
    // Custom named libraries keep their individually selected artwork.
    if(iconTheme()==='clean'){
      if(isStandard)return defaultIcon(kind);
      return window.WillieCleanIcons.createLibrary(library.icon,appearance,24);
    }
    if(library.icon_image_url && /^\/api\/libraries\/[0-9]+\/icon\.png\?v=[0-9]+$/.test(library.icon_image_url))
      return coloredIcon(library.icon_image_url);
    // Pirate mode preserves the existing library appearance choices.
    if(isStandard && ['film','tv','folder'].includes(library.icon))
      return defaultIcon(kind);
    if(!appearance?.icons[library.icon])
      return defaultIcon(kind);
    const wrap=document.createElement('span');wrap.className='nav-icon library-symbol';
    wrap.setAttribute('aria-hidden','true');
    wrap.append(appearance.createIcon(library.icon,28));
    return wrap;
  }
  Promise.all([
    fetch('/api/libraries',{cache:'no-store'}).then(r=>r.ok?r.json():[]).catch(()=>[]),
    fetch('/api/settings/sidebar',{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null),
    appearanceReady,
  ]).then(([libraries,layout,appearance])=>{
    const selected=new URLSearchParams(location.search).get('library_id');
    for(const library of libraries){
      if(!Number.isInteger(library.id)||!['movies','tv'].includes(library.kind))continue;
      const name=String(library.name||'').trim().slice(0,80);
      if(!name)continue;
      // A standard Movies/TV entry already exists, but a custom appearance
      // makes that library an intentional named entry.
      const normalized=name.toLocaleLowerCase().replace(/[^a-z0-9]/g,'');
      const isDefault=(library.kind==='movies'&&normalized==='movies')||
        (library.kind==='tv'&&(normalized==='tvshows'||normalized==='tv'));
      if(isDefault){
        // A standard Movies/TV Shows library decorates the existing combined
        // entry instead of creating a second identically named sidebar link.
        const base=nav.querySelector('a[data-nav-id="'+library.kind+'"]');
        if(base){
          const font=appearance?.fonts[library.font]?library.font:'default';
          base.classList.add('library-font--'+font);
          const oldIcon=base.querySelector('.nav-icon');
          if(oldIcon)oldIcon.replaceWith(libraryGlyph(appearance,library,true));
          if(library.sidebar_hidden)base.classList.add('sidebar-hidden');
        }
        continue;
      }
      const link=document.createElement('a');
      link.href=(library.kind==='tv'?'/tv':'/movies')+'?'+new URLSearchParams({library_id:String(library.id)});
      link.title=name;link.setAttribute('aria-label',name+' library');
      link.className='nav-link library-nav-link library-font--'+
        (appearance?.fonts[library.font]?library.font:'default');
      link.dataset.navId='library:'+library.id;
      if(library.sidebar_hidden)link.classList.add('sidebar-hidden');
      if(selected===String(library.id) &&
         ((page==='movies'||page==='tv') || ['/movie','/tv/show','/tv/season','/tv/episode'].includes(location.pathname))) {
        link.setAttribute('aria-current','page');
        nav.querySelector('a[data-nav-id="'+library.kind+'"]')?.removeAttribute('aria-current');
      }
      const icon=libraryGlyph(appearance,library);
      icon.classList.add('library-custom-icon');
      link.append(icon);
      const caption=document.createElement('span');caption.className='nav-text';caption.textContent=name;
      link.append(caption);
      nav.append(link);
    }
    // Only actual custom library entries are appended; standard collections
    // share the existing Movies and TV Shows menu destinations.
    const links=new Map([...nav.querySelectorAll('a[data-nav-id]')].map(a=>[a.dataset.navId,a]));
    if(layout&&Array.isArray(layout.order)){
      const hidden=new Set(Array.isArray(layout.hidden)?layout.hidden:[]);
      for(const id of layout.order){
        const link=links.get(id);
        if(!link)continue;
        if(hidden.has(id)&&id!=='home'&&id!=='settings')link.classList.add('sidebar-hidden');
        nav.append(link);
      }
      for(const [id,link] of links){if(!layout.order.includes(id))nav.append(link)}
    }else{
      const settingsLink=links.get('settings');
      for(const [id,link] of links){
        if(id.startsWith('library:')){
          if(libraries.find(x=>'library:'+x.id===id)?.sidebar_hidden)link.classList.add('sidebar-hidden');
          nav.insertBefore(link,settingsLink);
        }
      }
    }
  }).catch(()=>{});
  // Update the sidebar immediately after saving icon changes in Library Settings
  // without requiring the user to navigate away or reload the entire page.
  document.addEventListener('willie:library-icon-updated',event=>{
    const lib=event.detail;
    if(!lib||!Number.isInteger(lib.id)||!['movies','tv'].includes(lib.kind))return;
    const name=String(lib.name||'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const standard=(lib.kind==='movies'&&name==='movies')||
      (lib.kind==='tv'&&(name==='tv'||name==='tvshows'));
    const navId=standard?lib.kind:'library:'+lib.id;
    const link=nav.querySelector('a[data-nav-id="'+navId+'"]');
    if(!link)return;
    const old=link.querySelector('.nav-icon');
    if(old)old.replaceWith(libraryGlyph(window.WillieLibraryAppearance,lib));
  });
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
  const onLibraryToolbar=target=>
    ['movies','tv'].includes(document.body.dataset.page) &&
    target instanceof Element &&
    Boolean(target.closest('#library-masthead .library-head-actions'));
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
      else if(!document.activeElement?.closest?.('#app-nav') &&
              !onLibraryToolbar(document.activeElement))select(null);
    },130);
  });
  document.addEventListener('focusin',event=>{
    // Moving from a poster to the sidebar should retain the last backdrop.
    if(event.target?.closest?.('#app-nav'))return;
    const element=locate(event.target);
    if(element)select(element);
  });
  document.addEventListener('focusout',event=>{
    const element=locate(event.target);
    if(!element||active!==element)return;
    hideTimer=setTimeout(()=>{
      const focused=locate(document.activeElement);
      if(focused&&focused.isConnected)select(focused);
      else if(!document.activeElement?.closest?.('#app-nav') &&
              !onLibraryToolbar(document.activeElement))select(null);
    },140);
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)select(null)});
});

// Media pages load the shared context menu as a versioned deferred script.
