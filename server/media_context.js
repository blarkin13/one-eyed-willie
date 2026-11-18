/* Shared, remote-first media context actions.
 * Only local, uniquely identified media can be deleted through Radarr/Sonarr.
 * Long OK works on Home and all local library/season poster tiles.
 */
(() => {
  if (window.__oewMediaContextInstalled) return;
  window.__oewMediaContextInstalled = true;
  const style = document.createElement('style');
  style.textContent = `
.oew-context{position:fixed;max-width:min(340px,calc(100vw - 24px));width:306px;
padding:9px;margin:0;border:1px solid #3a4f69;border-radius:12px;
background:#101b2cf8;color:#f1f6ff;box-shadow:0 22px 60px #000d;z-index:10000}
.oew-context::backdrop{background:#0008}
.oew-context h3{font-size:1rem;margin:6px 10px 10px;line-height:1.35}
.oew-context p{font-size:.82rem;line-height:1.45;color:#b7cce0;margin:8px 11px}
.oew-context button{width:100%;min-height:44px;display:flex;align-items:center;
padding:10px 12px;text-align:left;color:inherit;background:transparent;border:0;
border-radius:8px;font:inherit;cursor:pointer;gap:10px}
.oew-context button:focus,.oew-context button:focus-visible,
.oew-context button:hover{outline:2px solid var(--oew-tv-select-color,#8b5cf6);
outline-offset:-2px;background:#26364d}
.oew-context button:disabled{opacity:.38}
.oew-context .oew-danger{color:#ffb6b6}
.oew-context label{display:flex;align-items:flex-start;gap:10px;padding:9px 11px;
font-size:.86rem;line-height:1.35}
.oew-context input{width:22px;height:22px;min-width:22px;accent-color:#8b5cf6}
.oew-context .oew-status{color:#ffc3c3}
@media(prefers-reduced-motion:no-preference){
.oew-context[open]{animation:oew-context-in .14s ease-out}
@keyframes oew-context-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
}`;
  document.head.append(style);

  const onHome = () => location.pathname === '/';
  const movieQuery = q => q.get('library_id') && q.get('key');
  const titleOf = node => node?._homeItem?.title ||
    node.closest('.tile,.season-card')?.querySelector('h3')?.textContent ||
    node.title || document.title.split(' · ')[0] || 'Media';
  const valid = data => Number.isInteger(data.library_id) &&
    data.library_id > 0 && typeof data.key === 'string' && data.key.length > 0;

  function resolve(node) {
    const item = node?.closest?.(
      '.tile-button,.season-episode-tile,.person-credit-link,.detail-trigger'
    );
    if (!item) return null;
    const href = item.getAttribute('href') || '';
    const url = new URL(href || location.href, location.href);
    const path = url.pathname;
    const q = url.searchParams;
    const data = {
      library_id: Number(item.dataset.hoverLibraryId || item.dataset.libraryId ||
        q.get('library_id') || new URLSearchParams(location.search).get('library_id')),
      key: item.dataset.hoverKey || item.dataset.mediaKey || q.get('key') ||
        new URLSearchParams(location.search).get('key'),
      title: titleOf(item),
      href,
      node: item,
      media_id: Number(item.dataset.mediaId || item.dataset.continueMediaId ||
        item._homeItem?.media_id || q.get('media_id')) || null,
      kind: item.dataset.hoverKind || item.dataset.mediaKind ||
        (path.startsWith('/movie') ? 'movies' : 'tv'),
      season_number: q.has('season_number') ? Number(q.get('season_number')) :
        item.dataset.seasonNumber !== undefined
          ? Number(item.dataset.seasonNumber) : null,
      source: path
    };
    if (!['movies','tv'].includes(data.kind)) return null;
    if (data.kind === 'tv') data.scope =
      item.matches('.season-episode-tile') ? 'episode' :
      path === '/tv/season' ? 'season' : 'series';
    else data.scope = 'movie';
    // Episode season tiles must have an actual local episode id.
    if (data.scope === 'episode' && !data.media_id) return null;
    if (!valid(data)) return null;
    return data;
  }

  let active = null;
  function closeCurrent() {
    if (active?.open) active.close();
    active = null;
  }
  function dialog(title, origin, width=306) {
    closeCurrent();
    const modal = document.createElement('dialog');
    modal.className = 'oew-context';
    modal.style.width = width+'px';
    const heading = document.createElement('h3');
    heading.textContent = title;
    modal.append(heading);
    modal.addEventListener('close', () => {
      modal.remove();
      if (active === modal) active = null;
      origin?.isConnected && origin.focus({preventScroll:true});
    }, {once:true});
    document.body.append(modal);
    modal.showModal();
    active = modal;
    const bounds = origin?.getBoundingClientRect();
    const box = modal.getBoundingClientRect();
    modal.style.left = Math.max(8, Math.min(innerWidth-box.width-8,
      (bounds ? bounds.left : innerWidth/2)))+'px';
    modal.style.top = Math.max(8, Math.min(innerHeight-box.height-8,
      (bounds ? bounds.bottom+6 : innerHeight/3)))+'px';
    modal.addEventListener('click', event => {
      if (event.target === modal) modal.close();
    });
    return modal;
  }
  const option = (menu, label, run, danger=false) => {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = label;
    if (danger) button.className = 'oew-danger';
    button.onclick = () => Promise.resolve().then(run).catch(error => {
      const message = menu.querySelector('.oew-status') ||
        document.createElement('p');
      message.className = 'oew-status';
      message.textContent = error.message || 'Action failed';
      menu.append(message);
      button.disabled = false;
    });
    menu.append(button);
    return button;
  };
  const request = async (url, config) => {
    const response = await fetch(url, {cache:'no-store',...config});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(data.detail || 'Request failed');
    return data;
  };
  const params = data => {
    const p = new URLSearchParams({
      kind:data.kind, library_id:String(data.library_id),
      key:data.key, scope:data.scope
    });
    if (data.media_id) p.set('media_id',data.media_id);
    if (data.season_number !== null) p.set('season_number',data.season_number);
    return p;
  };
  const playerName = data => data.kind === 'movies' ? 'Radarr' : 'Sonarr';

  function confirmDelete(data) {
    const origin = data.node;
    const modal = dialog('Checking '+playerName(data)+'…',origin,326);
    const status = document.createElement('p');
    status.textContent = 'Matching the exact local title with your media manager.';
    modal.append(status);
    request('/api/media/actions?'+params(data)).then(info => {
      if (!modal.open) return;
      modal.querySelector('h3').textContent = 'Delete '+info.name+'?';
      status.textContent = info.explanation;
      if (!info.connected || !info.manager_id) {
        const p = document.createElement('p');
        p.className='oew-status';
        p.textContent = info.connected
          ? 'No unique match exists in '+playerName(data)+'. Nothing can be deleted here.'
          : 'Connect '+playerName(data)+' in Settings before deleting managed media.';
        modal.append(p);
        option(modal,'Cancel',()=>modal.close()).focus();
        return;
      }
      const showCheckbox = (label, checked=false) => {
        const row = document.createElement('label');
        const check = document.createElement('input');
        check.type='checkbox';check.checked=checked;
        row.append(check,document.createTextNode(label));
        modal.append(row);
        return check;
      };
      const narrow = data.scope === 'episode' || data.scope === 'season';
      const files = showCheckbox(narrow
        ? 'Delete downloaded file(s) through Sonarr'
        : 'Delete downloaded files through '+playerName(data));
      const manager = narrow ? null : showCheckbox('Remove title from '+playerName(data));
      if (narrow) {
        const p = document.createElement('p');
        p.textContent='Sonarr will keep the series entry. Only downloaded episode files in the selected scope are targeted.';
        modal.append(p);
      }
      const confirm = option(modal,'Confirm deletion',async () => {
        if (!files.checked && !(manager?.checked)) {
          throw Error('Select what should be deleted first');
        }
        if (data.scope === 'series' && files.checked && !manager?.checked) {
          throw Error('Deleting all series files requires removing the series from Sonarr');
        }
        confirm.disabled=true;
        const payload = {
          kind:data.kind, library_id:data.library_id, key:data.key,
          scope:data.scope, media_id:data.media_id,
          season_number:data.season_number, manager_id:info.manager_id,
          confirm_title:info.name, delete_files:files.checked,
          remove_from_manager:manager?.checked || false
        };
        const result=await request('/api/media/actions/delete',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(payload)
        });
        modal.close();
        if (result.rescan_required) {
          // Catalog indexing catches actual filesystem changes, rather than
          // pretending manager deletion instantly removed a local file.
          fetch('/api/libraries/'+data.library_id+'/scan',{method:'POST'})
            .catch(()=>{});
        }
        alert('Action submitted to '+playerName(data)+'. '+
          (result.rescan_required
            ?'Library scan requested to update available media.'
            :'Files were not deleted; the media manager entry was removed.'));
      },true);
      option(modal,'Cancel',()=>modal.close());
      confirm.focus({preventScroll:true});
      const pos=modal.getBoundingClientRect();
      modal.style.top=Math.max(8,Math.min(innerHeight-pos.height-8,
        (origin.getBoundingClientRect().top)))+'px';
    }).catch(error=>{
      if (!modal.open) return;
      status.textContent=error.message;
      status.className='oew-status';
      option(modal,'Cancel',()=>modal.close()).focus();
    });
  }

  function watchedAction(data, watched) {
    let url;
    if (data.kind==='movies' || data.scope==='episode') {
      if (!data.media_id) return Promise.reject(Error('No local media ID available'));
      url='/api/watch/'+data.media_id+'/watched';
    } else {
      const q=new URLSearchParams({library_id:data.library_id,key:data.key});
      if (data.scope==='season') q.set('season_number',data.season_number);
      url='/api/tv/'+(data.scope==='season'?'season':'show')+'/watched?'+q;
    }
    return request(url,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({watched})}).then(()=>{
        closeCurrent();
        document.dispatchEvent(new Event('willie:watch-updated'));
      });
  }
  async function playback(data) {
    let id=data.media_id;
    let restart=false;
    if (!id && data.kind==='movies') {
      const q=new URLSearchParams({library_id:data.library_id,key:data.key});
      const info=await request('/api/movies/details?'+q);
      id=info.media_id; restart=!(info.position_seconds>0);
    } else if (!id) {
      const q=new URLSearchParams({library_id:data.library_id,key:data.key});
      const info=await request('/api/tv/show?'+q);
      id=info.next_episode?.media_id;restart=!info.next_episode?.resume;
    }
    if (!id) throw Error('No playable local media was found');
    closeCurrent();
    if (!window.WilliePlayer?.open) throw Error('The player is unavailable');
    window.WilliePlayer.open(id,data.title,{restart});
  }
  function detailHref(data) {
    if (data.href && ['/movie','/tv/show','/tv/season'].some(prefix =>
      data.href.startsWith(prefix))) return data.href;
    const q=new URLSearchParams({library_id:data.library_id,key:data.key});
    if (data.kind==='movies') return '/movie?'+q;
    if (data.scope==='episode' && data.season_number!==null) {
      q.set('season_number',data.season_number);
      if (data.media_id) q.set('media_id',data.media_id);
      return '/tv/season?'+q;
    }
    if (data.scope==='season' && data.season_number!==null) {
      q.set('season_number',data.season_number);
      return '/tv/season?'+q;
    }
    return '/tv/show?'+q;
  }
  function deleteScopeMenu(data) {
    const modal=dialog('Delete '+data.title, data.node);
    if (data.kind==='movies') {
      option(modal,'Delete movie…',()=>confirmDelete(data),true);
    } else {
      if (data.media_id && data.scope==='episode')
        option(modal,'Delete episode…',()=>confirmDelete({...data,scope:'episode'}),true);
      if (data.season_number!==null && Number.isInteger(data.season_number))
        option(modal,'Delete season…',()=>confirmDelete({...data,scope:'season'}),true);
      option(modal,'Delete entire series…',()=>confirmDelete({...data,scope:'series'}),true);
    }
    option(modal,'Cancel',()=>modal.close());
    modal.querySelector('button')?.focus({preventScroll:true});
  }
  function show(data) {
    const modal=dialog(data.title,data.node);
    option(modal,'Details',()=>{location.href=detailHref(data)});
    option(modal,'Play / Resume',()=>playback(data));
    option(modal,'Mark as watched',()=>watchedAction(data,true));
    option(modal,'Mark as unwatched',()=>watchedAction(data,false));
    option(modal,'Delete…',()=>deleteScopeMenu(data),true);
    option(modal,'Cancel',()=>modal.close());
    modal.querySelector('button')?.focus({preventScroll:true});
    return true;
  }

  window.__willieMediaLongSelect = () => {
    const data=resolve(document.activeElement);
    return data ? show(data) : false;
  };
  window.__willieMediaOpenDelete = node => {
    const data=resolve(node);
    if (!data) return false;
    deleteScopeMenu(data);
    return true;
  };
  const previousLongSelect = window.__willieTvLongSelect;
  window.__willieTvLongSelect = () => {
    const node=document.activeElement;
    if (node?.closest?.('#continue-watching .tile-button') &&
        typeof window.openContinueMenu==='function') {
      return window.openContinueMenu(node.closest('.tile-button'));
    }
    const data=resolve(node);
    if(data) return show(data);
    return typeof previousLongSelect==='function' ? previousLongSelect() : false;
  };
  document.addEventListener('contextmenu',event=>{
    const data=resolve(event.target);
    if(!data || data.node.closest('#continue-watching'))return;
    event.preventDefault();show(data);
  });
  let hold=null,heldNode=null,suppressClick=null;
  document.addEventListener('pointerdown',event=>{
    const data=resolve(event.target);
    if(!data || data.node.closest('#continue-watching') ||
       event.pointerType==='mouse')return;
    heldNode=data.node;
    hold=setTimeout(()=>{
      suppressClick=heldNode;
      show(data);
    },570);
  });
  for(const type of ['pointerup','pointercancel','pointerleave','pointermove']){
    document.addEventListener(type,()=>{clearTimeout(hold);hold=null;});
  }
  document.addEventListener('click',event=>{
    if(suppressClick && suppressClick.contains(event.target)){
      event.preventDefault();event.stopImmediatePropagation();
      suppressClick=null;
    }
  },true);
})();
