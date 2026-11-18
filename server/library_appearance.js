/* First-party, offline-safe icon + typography choices for library navigation.
   Values must remain in sync with the allowlists in server/library.py. */
(()=>{
'use strict';
const icons={
 film:['Film','Media','<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4m-4 6h4m10-6h4m-4 6h4"/>'],
 tv:['Television','Media','<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M8 21h8m-4-3v3"/>'],
 folder:['Folder','Media','<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'],
 clapperboard:['Clapperboard','Media','<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M3 8 5 3h16v5M8 3l-2 5M14 3l-2 5M20 3l-2 5"/>'],
 play:['Play','Media','<path d="m8 5 12 7-12 7z"/>'],
 reel:['Film reel','Media','<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><circle cx="8" cy="7.5" r="1"/><circle cx="16" cy="7.5" r="1"/><circle cx="8" cy="16.5" r="1"/><circle cx="16" cy="16.5" r="1"/>'],
 popcorn:['Popcorn','Media','<path d="m5 9 2 12h10l2-12M6 9h12M9 9l1 12M15 9l-1 12"/><path d="M7 8a2.5 2.5 0 0 1 2-4 3 3 0 0 1 6 0 2.5 2.5 0 0 1 2 4"/>'],
 ticket:['Ticket','Media','<path d="M4 6h16v4a2 2 0 0 0 0 4v4H4v-4a2 2 0 0 0 0-4zM12 6v2m0 3v2m0 3v2"/>'],
 camera:['Camera','Media','<path d="M3 7h5l2-3h4l2 3h5v13H3z"/><circle cx="12" cy="13" r="4"/>'],
 video:['Video camera','Media','<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/>'],
 headphones:['Headphones','Media','<path d="M3 14v-3a9 9 0 0 1 18 0v3M3 14h4v6H5a2 2 0 0 1-2-2zM17 14h4v4a2 2 0 0 1-2 2h-2z"/>'],
 music:['Music','Media','<path d="M9 18V5l11-2v13M9 9l11-2"/><ellipse cx="6" cy="18.5" rx="3" ry="2"/><ellipse cx="17" cy="16.5" rx="3" ry="2"/>'],
 star:['Star','Genres','<path d="m12 2 3.1 6.6 7.3 1-5.3 5.2 1.2 7.2-6.3-3.4-6.4 3.4 1.2-7.2-5.2-5.2 7.3-1z"/>'],
 heart:['Romance','Genres','<path d="M20.8 8.2c0 5.1-8.8 11.3-8.8 11.3S3.2 13.3 3.2 8.2a4.8 4.8 0 0 1 8.8-2.6 4.8 4.8 0 0 1 8.8 2.6z"/>'],
 ghost:['Ghost','Genres','<path d="M5 21V11a7 7 0 0 1 14 0v10l-3.5-2-3.5 2-3.5-2z"/><path d="M9 11h.01M15 11h.01"/>'],
 skull:['Horror skull','Genres','<path d="M5 15a8 8 0 1 1 14 0l-2 2v4H7v-4z"/><circle cx="9" cy="13" r="1.3"/><circle cx="15" cy="13" r="1.3"/><path d="M12 15v1M10 20v-3m4 3v-3"/>'],
 pumpkin:['Halloween','Genres','<path d="M12 6V3l2-1M12 6c-5-3-10 1-10 7s5 9 10 9 10-3 10-9-5-10-10-7zM8 7c-2 5-2 9 0 13m8-13c2 5 2 9 0 13"/><path d="m6 12 2-1m8 0 2 1m-10 5 4 2 4-2"/>'],
 flame:['Action / Fire','Genres','<path d="M12 22c-5 0-8-3.4-8-8.1 0-4 2.5-6.1 5-9 .4 3.5 2.8 4.8 3.8 5.3 1.2-2 1.9-4 1.4-7.2 4.6 3.6 6.8 7.1 6.8 11A8 8 0 0 1 12 22z"/><path d="M12 21a4 4 0 0 1-4-4c0-2 1-3 3-5 0 2.3 2 3.3 3 5 .5-1 1-1.5 1-2.2 2 3.4 0 6.2-3 6.2z"/>'],
 zap:['Action bolt','Genres','<path d="m13 2-9 11h7l-1 9 10-12h-7z"/>'],
 rocket:['Science fiction','Genres','<path d="M6 15c1-6 6-11 14-12-1 8-6 13-12 14zM6 15l-3 6 6-3M8 11l-5-1 3-4M13 17l1 5 4-3"/><circle cx="14" cy="9" r="2"/>'],
 planet:['Planet','Genres','<circle cx="12" cy="12" r="7"/><ellipse cx="12" cy="12" rx="11" ry="4" transform="rotate(-25 12 12)"/>'],
 robot:['Robot','Genres','<rect x="4" y="8" width="16" height="13" rx="2"/><path d="M12 8V4m-2 0h4M1 12h3m16 0h3M8 15h.01M16 15h.01M9 19h6"/>'],
 alien:['Alien','Genres','<path d="M12 2c-6 0-9 5-9 10 0 6 5 10 9 10s9-4 9-10c0-5-3-10-9-10z"/><path d="M5.5 12c3 0 4 1 4.5 4-3 0-4-1.5-4.5-4zm13 0c-3 0-4 1-4.5 4 3 0 4-1.5 4.5-4z"/>'],
 wand:['Fantasy','Genres','<path d="m4 20 13-13 3 3L7 23zM15 2v3m6 1-2 2m-5-2-2-2M19 15v3m3-1-2 2"/>'],
 sword:['Sword','Genres','<path d="m19 3 2 2-11 11-3-3zM7 13l-4 4m7 0-5-5M6 18l-2 2"/>'],
 crown:['Royalty','Genres','<path d="m3 7 4 5 5-8 5 8 4-5-2 12H5zM5 22h14"/>'],
 shield:['War / Hero','Genres','<path d="M12 2 3 6v6c0 6 4 9 9 10 5-1 9-4 9-10V6z"/><path d="m9 12 2 2 4-4"/>'],
 smile:['Comedy','Genres','<circle cx="12" cy="12" r="10"/><path d="M8 10h.01M16 10h.01M7 15c3.2 4 6.8 4 10 0"/>'],
 drama:['Drama','Genres','<path d="M4 4c1 1 5 1 8 0v8c0 4-4 6-4 6S4 16 4 12zM13 7c2 1 5 1 7 0v9c0 4-4 6-4 6s-3-2-3-6z"/><path d="M6 9h.01m4 0h.01m-4 4 4-1m5 2h.01m3 0h.01m-3 4c1-2 2-2 3 0"/>'],
 eye:['Mystery','Genres','<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'],
 fingerprint:['Crime / Thriller','Genres','<path d="M4 12c0-11 16-11 16 0M7 12c0-7 10-7 10 0m-5-6v0m0 4v8m-4-3c0 3-1 5-2 6m12-6c0 3 1 5 2 6m-12-5c0 4 0 5-1 7m10-7c0 4 0 5 1 7"/>'],
 trophy:['Sports','Genres','<path d="M7 4h10v7a5 5 0 0 1-10 0zM7 6H3v3a4 4 0 0 0 4 4m10-7h4v3a4 4 0 0 1-4 4M12 16v4m-5 2h10"/>'],
 gamepad:['Gaming','Genres','<path d="M7 8h10a5 5 0 0 1 5 5v4a3 3 0 0 1-5 2l-2-2H9l-2 2a3 3 0 0 1-5-2v-4a5 5 0 0 1 5-5zM8 11v5m-2.5-2.5h5M16.5 12.5h.01M19 15h.01"/>'],
 book:['Books / Stories','Collections','<path d="M4 3h14a3 3 0 0 1 3 3v15H7a3 3 0 0 1-3-3zM4 17c0-2 2-3 4-3h13M8 7h9"/>'],
 archive:['Archive','Collections','<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v12h14V9M10 13h4"/>'],
 layers:['Collections','Collections','<path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/>'],
 grid:['Categories','Collections','<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'],
 bookmark:['Favorites','Collections','<path d="M6 3h12v18l-6-4-6 4z"/>'],
 gem:['Gems','Collections','<path d="M6 3h12l5 6-11 13L1 9zM1 9h22M6 3l4 6 2 13 2-13 4-6"/>'],
 award:['Awards','Collections','<circle cx="12" cy="8" r="6"/><path d="m8 13-2 9 6-3 6 3-2-9"/>'],
 clock:['Recently added','Collections','<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>'],
 calendar:['Calendar','Collections','<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M7 14h3m4 0h3M7 18h3"/>'],
 hourglass:['Classics','Collections','<path d="M6 2h12M6 22h12M7 2v5l5 5-5 5v5m10-20v5l-5 5 5 5v5M7 6h10m-10 12h10"/>'],
 search:['Discover','Collections','<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>'],
 map:['Travel map','Themes','<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15m6-12v15"/>'],
 compass:['Adventure','Themes','<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z"/>'],
 globe:['World','Themes','<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 6 5 12 0 18M12 3c-5 6-5 12 0 18M5 7h14M5 17h14"/>'],
 mountain:['Western / Nature','Themes','<path d="m1 21 8-14 5 8 3-4 6 10zM7 11l2 2 2-2"/>'],
 tree:['Nature','Themes','<path d="m12 3 7 8h-3l5 7H3l5-7H5zM12 18v4"/>'],
 leaf:['Nature / Wildlife','Themes','<path d="M21 3C11 3 4 7 4 15a6 6 0 0 0 6 6c8 0 12-8 11-18zM4 21c4-7 8-10 14-12"/>'],
 paw:['Animals','Themes','<path d="M6 14c-3 2-2 7 2 7 2 0 2-1 4-1s2 1 4 1c4 0 5-5 2-7-2-2-4-3-6-3s-4 1-6 3z"/><ellipse cx="5" cy="9" rx="1.5" ry="2"/><ellipse cx="10" cy="6" rx="1.5" ry="2"/><ellipse cx="15" cy="6" rx="1.5" ry="2"/><ellipse cx="20" cy="9" rx="1.5" ry="2"/>'],
 users:['Family','Themes','<circle cx="9" cy="8" r="3"/><circle cx="18" cy="9" r="2"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M16 15a5 5 0 0 1 6 5"/>'],
 sun:['Sun / Summer','Themes','<circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2"/>'],
 moon:['Night','Themes','<path d="M20 16A9 9 0 0 1 8 4a9 9 0 1 0 12 12z"/>'],
 snowflake:['Winter / Holiday','Themes','<path d="M12 2v20M4 6l16 12M20 6 4 18M9 5l3 3 3-3M9 19l3-3 3 3M3 10l4 1-1 4m15-5-4 1 1 4"/>'],
 gift:['Holiday','Themes','<rect x="3" y="9" width="18" height="12" rx="1"/><path d="M2 9h20M12 9v12M12 9C8 1 3 4 6 7c2 2 6 2 6 2zm0 0c4-8 9-5 6-2-2 2-6 2-6 2z"/>'],
 plane:['Airplane','Themes','<path d="M22 2 2 11l8 3 3 8zM10 14l12-12"/>'],
 ship:['Pirate ship','Themes','<path d="M3 17h18l-3 5H6zM12 3v14M12 4 4 12h8M13 5l7 7h-7M2 14l2 1m15 0 3-1"/>'],
 car:['Cars','Themes','<path d="m5 11 2-6h10l2 6M4 11h16v8H4zM7 19v2m10-2v2M7 15h.01M17 15h.01"/>'],
 sparkles:['Magic','Themes','<path d="m12 2 2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4zM19 18l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>']
};
const fonts={
 default:['Default','Clean system sans-serif'],
 modern:['Modern','Contemporary and understated'],
 cinematic:['Cinematic','Wide, screen-inspired lettering'],
 display:['Bold display','Strong, confident headlines'],
 condensed:['Condensed','Tight, compact lettering'],
 rounded:['Rounded','Soft, friendly curves'],
 serif:['Classic serif','Traditional book typography'],
 editorial:['Editorial','Elegant, high-contrast serif'],
 vintage:['Vintage','Old-fashioned print lettering'],
 mono:['Monospace','Equal-width characters'],
 typewriter:['Typewriter','Mechanical, archival style'],
 script:['Script','Handwritten-style lettering']
};
function createIcon(key,size=26){
 const data=icons[key]||icons.folder;
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width',String(size));svg.setAttribute('height',String(size));
 svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');
 svg.setAttribute('stroke-width','1.75');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
 svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
 svg.classList.add('library-icon-svg');
 svg.innerHTML=data[2];
 return svg;
}

// Use the same Font Awesome Free vocabulary for library headers, settings,
// previews and icon selection. The existing SVG remains the offline fallback.
const faIcons={
 film:'fa-film',tv:'fa-tv',folder:'fa-folder',clapperboard:'fa-clapperboard',
 play:'fa-play',reel:'fa-film',popcorn:'fa-bowl-food',ticket:'fa-ticket',
 camera:'fa-camera',video:'fa-video',headphones:'fa-headphones',music:'fa-music',
 star:'fa-star',heart:'fa-heart',ghost:'fa-ghost',skull:'fa-skull',
 pumpkin:'fa-face-grin',flame:'fa-fire',zap:'fa-bolt',rocket:'fa-rocket',
 planet:'fa-earth-americas',robot:'fa-robot',alien:'fa-user-astronaut',
 wand:'fa-wand-magic-sparkles',sword:'fa-shield-halved',crown:'fa-crown',
 shield:'fa-shield',smile:'fa-face-smile',drama:'fa-masks-theater',
 eye:'fa-eye',fingerprint:'fa-fingerprint',trophy:'fa-trophy',gamepad:'fa-gamepad',
 book:'fa-book',archive:'fa-box-archive',layers:'fa-layer-group',grid:'fa-table-cells',
 bookmark:'fa-bookmark',gem:'fa-gem',award:'fa-award',clock:'fa-clock',
 calendar:'fa-calendar',hourglass:'fa-hourglass',search:'fa-magnifying-glass',
 map:'fa-map',compass:'fa-compass',globe:'fa-globe',mountain:'fa-mountain',
 tree:'fa-tree',leaf:'fa-leaf',paw:'fa-paw',users:'fa-users',sun:'fa-sun',
 moon:'fa-moon',snowflake:'fa-snowflake',gift:'fa-gift',plane:'fa-plane',
 ship:'fa-ship',car:'fa-car',sparkles:'fa-wand-magic-sparkles'
};
function iconTheme(){
 try{return localStorage.getItem('willie-icon-theme')==='pirate'?'pirate':'clean'}
 catch{return 'clean'}
}
function createThemeIcon(key,size=26){
 if(iconTheme()==='pirate')return createIcon(key,size);
 const wrap=document.createElement('span');
 wrap.className='library-fa-icon';
 wrap.style.fontSize=size+'px';
 wrap.setAttribute('aria-hidden','true');
 const glyph=document.createElement('i');
 glyph.className='fa-solid '+(faIcons[key]||'fa-folder');
 const fallback=createIcon(key,size);
 fallback.classList.add('library-fa-fallback');
 wrap.append(glyph,fallback);
 return wrap;
}
window.WillieLibraryAppearance=Object.freeze({icons,fonts,createIcon,createThemeIcon,iconTheme});
})();