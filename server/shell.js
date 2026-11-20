/* Shared compact navigation and branding for every Yarr Media page. */
document.addEventListener('DOMContentLoaded', () => {
  // Installable Android/iOS homescreen web app metadata. No offline media caching.
  if(!document.querySelector('link[rel="manifest"]')){
    const manifest=document.createElement('link');manifest.rel='manifest';manifest.href='/app.webmanifest';
    document.head.append(manifest);
  }
  if(!document.querySelector('meta[name="theme-color"]')){
    const theme=document.createElement('meta');theme.name='theme-color';theme.content='#000000';document.head.append(theme);
  }
  if(!document.querySelector('meta[name="apple-mobile-web-app-capable"]')){
    const capable=document.createElement('meta');capable.name='apple-mobile-web-app-capable';capable.content='yes';document.head.append(capable);
  }
  if(!document.querySelector('meta[name="apple-mobile-web-app-title"]')){
    const title=document.createElement('meta');title.name='apple-mobile-web-app-title';title.content='Yarr Media';document.head.append(title);
  }
  if(!document.querySelector('link[rel="apple-touch-icon"]')){
    const icon=document.createElement('link');icon.rel='apple-touch-icon';icon.href='/assets/touch-icon.png?v=moon-sail-v1';document.head.append(icon);
  }
  // Keep server dropdowns and connection cards in sync with the configured TV
  // highlight color, rather than carrying a hard-coded purple focus accent.
  fetch('/api/settings/tv-appearance',{cache:'no-store'}).then(r=>r.ok?r.json():null)
    .then(value=>{
      const color=value?.selection_color;
      if(/^#[0-9a-fA-F]{6}$/.test(color||''))
        document.documentElement.style.setProperty('--oew-tv-select-color',color);
    }).catch(()=>{});
  // Shared first-party widgets for Home, paused browser playback and idle TV/browser.
  // No third-party scripts are loaded on customer devices.
  if(!document.querySelector('script[data-yarr-glance]')){
    const glance=document.createElement('script');
    glance.dataset.yarrGlance='1';
    glance.src='/assets/glance.js?v=1';
    document.head.append(glance);
  }
  const target=document.getElementById('app-nav');
  if(!target)return;
  const page=document.body.dataset.page||'home';
  const inSettings=['settings','general','appearance','libraries','remote','metadata','connections','maintenance','playback'].includes(page);
  // Integration dashboards live under Integrations, including on TV.
  const active=['connectionshub','services','radarr','sonarr','sabnzbd'].includes(page)
    ?'connections':inSettings?'settings':page;
  // The public Workers site uses / for its website and /app for the media home.
  // The locally hosted server continues to use / for its home screen.
  const homeHref=window.location.hostname==='yarr.larki-brian.workers.dev'?'/app':'/';
  const navItems=[
    {id:'home',href:homeHref,name:'Home',fa:'fa-house',fallback:'home'},
    {id:'movies',href:'/movies',name:'Movies',fa:'fa-film',fallback:'film'},
    {id:'tv',href:'/tv',name:'TV Shows',fa:'fa-tv',fallback:'tv'},
    {id:'music',href:'/music',name:'Music',fa:'fa-music',fallback:'music'},
    {id:'connections',href:'/integrations',name:'Integrations',fa:'fa-plug',fallback:'connections'},
    {id:'settings',href:'/settings',name:'Settings',fa:'fa-gear',fallback:'settings'}
  ];
  // Inline SVG fallbacks make every control usable without an external font.
  const paths={
    music:'<path d="M9 18V5l11-2v13M9 9l11-2" stroke="currentColor" fill="none" stroke-width="1.7"/><ellipse cx="6" cy="18.5" rx="3" ry="2" fill="currentColor"/><ellipse cx="17" cy="16.5" rx="3" ry="2" fill="currentColor"/>',
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
      home:['fa-house','home'],movies:['fa-film','film'],tv:['fa-tv','tv'],music:['fa-music','music'],
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
  // Clean remains default; the theme setting is local to each device.
  const ICON_THEME_KEY='willie-icon-theme';
  const iconTheme=()=>{
    try{
      const v=localStorage.getItem(ICON_THEME_KEY);
      return v==='pirate'||v==='adventure'?v:'clean';
    }catch(_){return 'clean';}
  };
  window.WillieActionIcons={
    names:{home:'home',movies:'movies',tv:'tv-shows',music:'music',
      connections:'connections',sabnzbd:'connections',settings:'settings'},
    create(name,size=24){
      const asset=this.names[name]||this.names.movies;
      const wrap=document.createElement('span');
      wrap.className='nav-icon nav-action-icon';
      wrap.setAttribute('aria-hidden','true');
      wrap.style.width=size+'px';wrap.style.height=size+'px';
      // Real SVG image instead of a CSS mask: works with cached stylesheets,
      // WebKit and the TV browser, and never leaves an empty icon on 404.
      const image=document.createElement('img');
      image.className='adventure-icon-image';
      image.alt='';image.width=size;image.height=size;
      image.style.cssText='display:block;width:100%;height:100%;object-fit:contain;max-width:100%;max-height:100%';
      image.addEventListener('error',()=>{
        const fallback=window.WillieCleanIcons.create(name,size);
        wrap.replaceWith(fallback);
      },{once:true});
      image.src='/assets/themes/action-adventure/'+asset+'.svg?v=2';
      wrap.append(image);
      return wrap;
    }
  };
  function defaultIcon(kind){
    const safe=['home','movies','tv','music','connections','settings'].includes(kind)?kind:'movies';
    if(iconTheme()==='pirate'){
      if(safe==='music')return window.WillieCleanIcons.create('music',24);
      return coloredIcon('/assets/sidebar-icon-'+(safe==='connections'?'sabnzbd':safe)+'.png?v=pirate-v3');
    }
    if(iconTheme()==='adventure')return window.WillieActionIcons.create(safe,26);
    return window.WillieCleanIcons.create(safe,24);
  }
  document.documentElement.dataset.iconTheme=iconTheme();
  // Logo anchors the upper-left corner on desktop and mobile.
  const brand=document.createElement('a');brand.href=homeHref;brand.className='brand';brand.setAttribute('aria-label','Yarr Media — Home');
  brand.title='Yarr Media';
  // Moon and tattered-sail Yarr Media logo, sized as a square alongside icon-set glyphs.
  const logoFrame=document.createElement('span');logoFrame.className='brand-logo-frame';
  logoFrame.setAttribute('aria-hidden','true');
  const image=document.createElement('img');image.className='brand-logo';image.src='/assets/logo.svg?v=moon-sail-v1';
  image.alt='';image.width=90;image.height=90;
  logoFrame.append(image);
  // Match the public site: editable text, not the legacy decorative image.
  const wordmark=document.createElement('span');
  wordmark.className='brand-wordmark';
  wordmark.setAttribute('aria-hidden','true');
  const name=document.createElement('span');name.className='brand-wordmark-yarr';name.textContent='YARR';
  const dot=document.createElement('span');dot.className='brand-wordmark-dot';dot.textContent='.';
  const media=document.createElement('span');media.className='brand-wordmark-media';media.textContent='MEDIA';
  wordmark.append(name,dot,media);
  brand.append(logoFrame,wordmark);target.append(brand);

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
  // Do not show unconfigured library types, including during initial paint.
  // The successful /api/libraries result below decides which to reveal.
  for(const kind of ['movies','tv','music']){
    const link=nav.querySelector('a[data-nav-id="'+kind+'"]');
    if(link){link.hidden=true;link.classList.add('sidebar-hidden');}
  }
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
  // General, Library, Metadata and integration configuration live on /settings only.
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
    const kind=library.kind==='music'?'music':library.kind==='tv'?'tv':'movies';
    // Theme selection takes precedence for the main Movies and TV Shows links.
    // Their library image uploads and Pirate presets are used only by Pirate.
    // Custom named libraries keep their individually selected artwork.
    if(iconTheme()==='clean'||iconTheme()==='adventure'){
      if(isStandard)return defaultIcon(kind);
      // The pack covers the six main destinations; named libraries keep
      // their individual icon selections in the Font Awesome fallback set.
      return window.WillieCleanIcons.createLibrary(library.icon,appearance,24);
    }
    if(library.icon_image_url && /^\/api\/libraries\/[0-9]+\/icon\.png\?v=[0-9]+$/.test(library.icon_image_url))
      return coloredIcon(library.icon_image_url);
    // Pirate mode preserves the existing library appearance choices.
    if(isStandard && ['film','tv','folder','music'].includes(library.icon))
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
    const configured = new Set(libraries.map(item=>item.kind));
    for(const kind of ['movies','tv','music']){
      const link=nav.querySelector('a[data-nav-id="'+kind+'"]');
      if(!link)continue;
      if(!configured.has(kind)){
        // Never reorder an unavailable standard library after Settings.
        // Remove it from the DOM rather than relying on hidden CSS alone.
        link.remove();
        continue;
      }
      link.hidden=false;
      link.classList.remove('sidebar-hidden');
    }
    const selected=new URLSearchParams(location.search).get('library_id');
    for(const library of libraries){
      if(!Number.isInteger(library.id)||!['movies','tv','music'].includes(library.kind))continue;
      const name=String(library.name||'').trim().slice(0,80);
      if(!name)continue;
      // A standard Movies/TV entry already exists, but a custom appearance
      // makes that library an intentional named entry.
      const normalized=name.toLocaleLowerCase().replace(/[^a-z0-9]/g,'');
      const isDefault=(library.kind==='movies'&&normalized==='movies')||
        (library.kind==='tv'&&(normalized==='tvshows'||normalized==='tv'))||
        (library.kind==='music'&&normalized==='music');
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
      link.href=(library.kind==='music'?'/music':library.kind==='tv'?'/tv':'/movies')+'?'+new URLSearchParams({library_id:String(library.id)});
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
  }).catch(()=>{
    // On network failure never reveal library links that may not exist.
  });
  // Update the sidebar immediately after saving icon changes in Library Settings
  // without requiring the user to navigate away or reload the entire page.
  document.addEventListener('willie:library-icon-updated',event=>{
    const lib=event.detail;
    if(!lib||!Number.isInteger(lib.id)||!['movies','tv','music'].includes(lib.kind))return;
    const name=String(lib.name||'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const standard=(lib.kind==='movies'&&name==='movies')||
      (lib.kind==='tv'&&(name==='tv'||name==='tvshows'))||
      (lib.kind==='music'&&name==='music');
    const navId=standard?lib.kind:'library:'+lib.id;
    const link=nav.querySelector('a[data-nav-id="'+navId+'"]');
    if(!link)return;
    const old=link.querySelector('.nav-icon');
    if(old)old.replaceWith(libraryGlyph(window.WillieLibraryAppearance,lib));
  });
  if(!document.querySelector('link[rel~="icon"]')){
    const favicon=document.createElement('link');
    favicon.rel='icon';favicon.type='image/png';favicon.href='/assets/favicon.png?v=moon-sail-v1';
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
  if(!['home','movies','tv','explore','music'].includes(document.body.dataset.page))return;
  const backdrop=document.createElement('div');
  backdrop.className='willie-hover-backdrop';
  backdrop.setAttribute('aria-hidden','true');
  const layers=[document.createElement('div'),document.createElement('div')];
  for(const layer of layers){layer.className='willie-hover-backdrop-layer';backdrop.append(layer)}
  document.body.prepend(backdrop);
  const cache=new Map();
  let active=null,showTimer=null,hideTimer=null,generation=0,visible=-1,currentUrl='';
  const valid=url=>typeof url==='string'&&(
    url.startsWith('/api/artwork/')||url.startsWith('https://image.tmdb.org/t/p/')||
    /^\/api\/(music\/tracks\/\d+\/art|lidarr\/artist\/\d+\/image\/(fanart|poster))$/.test(url));
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
  let soft=false;
  function apply(url,serial){
    if(serial!==generation)return;
    if(!valid(url)){clear();return}
    if(currentUrl===url)return;
    const img=new Image();
    img.onload=()=>{
      if(serial!==generation)return;
      const index=visible===0?1:0;
      layers[index].style.backgroundImage='url("'+url+'")';
      layers[index].classList.toggle('is-soft',soft);
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
      soft=element.dataset.hoverSoft==='1';
      if(serial!==generation)return;
      apply(url,serial);
    },180);
  }
  const onLibraryToolbar=target=>
    ['movies','tv','music'].includes(document.body.dataset.page) &&
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
