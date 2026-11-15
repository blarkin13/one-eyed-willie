/* Shared navigation for every One-Eyed Willie page. */
document.addEventListener('DOMContentLoaded', () => {
  const target = document.getElementById('app-nav');
  if (!target) return;
  const page = document.body.dataset.page || 'home';
  const active = ['libraries', 'remote', 'metadata', 'connections'].includes(page) ? 'settings' : page;
  const navItems = [
    ['home', '/', '⌂', 'Home'],
    ['movies', '/movies', '▣', 'Movies'],
    ['tv', '/tv', '▤', 'TV Shows'],
    ['explore', '/explore', '⌕', 'Explore More'],
    ['settings', '/settings/libraries', '⚙', 'Settings'],
  ];
  const brand = document.createElement('a');
  brand.className = 'brand';
  brand.href = '/';
  brand.innerHTML = '<span class="brand-mark" aria-hidden="true">W</span>One-Eyed Willie';
  target.appendChild(brand);

  const label = document.createElement('div');
  label.className = 'nav-label';
  label.textContent = 'Your library';
  target.appendChild(label);

  const nav = document.createElement('nav');
  nav.className = 'side-nav';
  nav.setAttribute('aria-label', 'Main navigation');
  navItems.forEach(([id, href, glyph, title]) => {
    const link = document.createElement('a');
    link.href = href;
    link.className = 'nav-link';
    if (id === active) link.setAttribute('aria-current', 'page');
    const icon = document.createElement('span');
    icon.className = 'nav-glyph';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = glyph;
    link.append(icon, document.createTextNode(title));
    nav.appendChild(link);
  });
  target.appendChild(nav);

  if (active === 'settings') {
    const sublabel = document.createElement('div');
    sublabel.className = 'nav-label';
    sublabel.textContent = 'Settings';
    sublabel.style.marginTop = '18px';
    target.appendChild(sublabel);
    const subs = document.createElement('nav');
    subs.className = 'side-nav';
    subs.setAttribute('aria-label', 'Settings navigation');
    [['libraries','/settings/libraries','Libraries'],['remote','/settings/remote','Remote Access'],['metadata','/settings/metadata','Metadata'],['connections','/settings/connections','Connections']].forEach(([id,href,title])=>{
      const link=document.createElement('a');
      link.className='nav-link';
      link.href=href;
      link.textContent=title;
      if(page===id)link.setAttribute('aria-current','page');
      subs.appendChild(link);
    });
    target.appendChild(subs);
  }

  const foot = document.createElement('div');
  foot.className = 'sidebar-foot';
  foot.textContent = 'Personal media server';
  target.appendChild(foot);

  const breadcrumb = document.getElementById('breadcrumbs');
  if (breadcrumb) {
    const labels={home:'Home',movies:'Movies',tv:'TV Shows',libraries:'Settings / Libraries',remote:'Settings / Remote Access',metadata:'Settings / Metadata',connections:'Settings / Connections',explore:'Explore More'};
    breadcrumb.textContent = 'One-Eyed Willie / ';
    const strong=document.createElement('strong');
    strong.textContent=labels[page]||'Home';
    breadcrumb.appendChild(strong);
  }
});
