/* Shared compact navigation and branding for every One-Eyed Willie page. */
document.addEventListener('DOMContentLoaded', () => {
  const target=document.getElementById('app-nav');
  if(!target)return;
  const page=document.body.dataset.page||'home';
  const inSettings=['libraries','remote','metadata','connections'].includes(page);
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
  // The logo is the supplied logo.png, not favicon.png. Its square canvas
  // includes a tiny line of lettering below the skull; frame the skull here
  // so it doesn't appear as a second, unreadable wordmark beside the title.
  const logoFrame=document.createElement('span');logoFrame.className='brand-logo-frame';
  logoFrame.setAttribute('aria-hidden','true');
  const image=document.createElement('img');image.className='brand-logo';image.src='/assets/logo.png';
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
  if(inSettings){
    const subnav=document.createElement('nav');subnav.className='settings-shortcuts';
    subnav.setAttribute('aria-label','Settings sections');
    [['libraries','/settings/libraries','Libraries'],['remote','/settings/remote','Remote Access'],['metadata','/settings/metadata','Metadata'],['connections','/settings/connections','Connections']].forEach(([id,href,name])=>{
      const a=document.createElement('a');a.href=href;a.title=name;a.textContent=name;
      if(page===id)a.setAttribute('aria-current','page');
      subnav.append(a);
    });target.append(subnav);
  }
  const favicon=document.createElement('link');
  favicon.rel='icon';
  favicon.type='image/png';
  favicon.href='/assets/favicon.png?v=3';
  document.head.append(favicon);
  // Use Font Awesome Free when loaded; keep local SVGs when offline.
  if(document.fonts&&document.fonts.load){
    document.fonts.load('900 16px "Font Awesome 6 Free"').then(faces=>{
      if(faces.length&&faces.some(face=>face.status==='loaded')){
        document.documentElement.classList.add('fontawesome-ready');
      }
    }).catch(()=>{});
  }
  // Make the hover-expanded icon rail keyboard-accessible too.
  target.querySelectorAll('.nav-link').forEach(link=>{
    link.addEventListener('focus',()=>target.classList.add('nav-focused'));
    link.addEventListener('blur',()=>target.classList.remove('nav-focused'));
  });
});
