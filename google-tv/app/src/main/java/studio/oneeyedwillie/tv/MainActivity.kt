package studio.oneeyedwillie.tv

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import java.net.URI

/**
 * The same One-Eyed Willie UI served to desktop browsers is the TV UI.
 * It is deliberately NOT a second independently maintained Compose screen set.
 * Native Media3 playback handles codecs that Android WebView cannot reliably play.
 */
class MainActivity : ComponentActivity() {
    private val prefs by lazy { getSharedPreferences("server", MODE_PRIVATE) }
    private var browser: WebView? = null
    private var origin = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val web = browser
                if (web != null && web.canGoBack()) web.goBack()
                else if (web != null && web.url != origin + "/") web.loadUrl(origin + "/")
                else showSetup()
            }
        })
        val saved = prefs.getString("url", "")?.trim()?.trimEnd('/').orEmpty()
        if (validOrigin(saved)) showServer(saved) else showSetup()
    }

    private fun validOrigin(value: String): Boolean = try {
        val u = URI(value)
        (u.scheme == "http" || u.scheme == "https") &&
            !u.host.isNullOrEmpty() && u.userInfo == null &&
            (u.path.isNullOrEmpty() || u.path == "/") &&
            u.query == null && u.fragment == null
    } catch (_: Exception) { false }

    private fun showSetup(error: String = "") {
        browser?.destroy()
        browser = null
        fun dp(value: Int) = (value * resources.displayMetrics.density + .5f).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            setPadding(dp(28), dp(20), dp(28), dp(20))
        }
        // Do not let the icon expand to match_parent or wrap its intrinsic size:
        // that previously pushed the Connect button completely off the TV.
        val brand = ImageView(this).apply {
            setImageResource(R.drawable.tv_ship_icon)
            adjustViewBounds = false
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "One-Eyed Willie pirate ship"
        }
        root.addView(brand, LinearLayout.LayoutParams(dp(144), dp(144)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(12)
        })
        val title = TextView(this).apply {
            text = "One-eyed Willie"
            textSize = 33f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        val help = TextView(this).apply {
            text = "Connect to your One-Eyed Willie server. The app will remember it."
            textSize = 18f
            setTextColor(0xFFBDBDBDL.toInt())
            gravity = Gravity.CENTER
        }
        val input = EditText(this).apply {
            setSingleLine(true)
            setText(prefs.getString("url", "http://192.168.86.29:8787"))
            hint = "http://your-server:8787"
            textSize = 20f
            setTextColor(Color.WHITE)
            setHintTextColor(0xFF999999L.toInt())
            setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.WHITE))
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        val status = TextView(this).apply {
            text = error
            textSize = 16f
            setTextColor(0xFFE3CCCCL.toInt())
        }
        val connect = Button(this).apply {
            text = "Connect"
            setTextColor(Color.BLACK)
            setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.WHITE))
            setOnClickListener {
                val entered = input.text.toString().trim().trimEnd('/')
                if (!validOrigin(entered)) status.text = "Enter a valid http:// or https:// server address."
                else {
                    prefs.edit().putString("url", entered).apply()
                    showServer(entered)
                }
            }
        }
        listOf(title, help, input, connect, status).forEach {
            val p = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(12) }
            root.addView(it, p)
        }
        // Allow access to the address and Connect button even on low-resolution
        // TVs with overscan or large system font sizes.
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(Color.BLACK)
            addView(root)
        }
        setContentView(scroll)
        connect.requestFocus()
    }

    private fun showServer(server: String) {
        if (!validOrigin(server)) { showSetup("Invalid server URL"); return }
        origin = server.trimEnd('/')
        val view = WebView(this)
        browser = view
        view.setBackgroundColor(Color.BLACK)
        view.isFocusable = true
        view.isFocusableInTouchMode = true
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            useWideViewPort = true
            loadWithOverviewMode = true
            builtInZoomControls = false
            displayZoomControls = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        view.webChromeClient = WebChromeClient()
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(web: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (uri.scheme == "oewtv" && uri.host == "play") {
                    uri.path?.trim('/')?.toIntOrNull()?.takeIf { it > 0 }?.let { play(it) }
                    return true
                }
                if (uri.path?.matches(Regex("/watch/[0-9]+")) == true && sameOrigin(uri.toString())) {
                    uri.lastPathSegment?.toIntOrNull()?.let { play(it) }
                    return true
                }
                // External metadata links may not navigate the embedded trusted browser.
                return !sameOrigin(uri.toString())
            }
            override fun onPageFinished(web: WebView, url: String?) {
                super.onPageFinished(web, url)
                if (sameOrigin(url.orEmpty())) installRemoteNavigation(web)
            }
        }
        setContentView(view)
        view.loadUrl("$origin/")
        view.requestFocus()
    }

    private fun sameOrigin(url: String): Boolean = try {
        val actual = URI(url)
        val saved = URI(origin)
        actual.scheme == saved.scheme && actual.host.equals(saved.host, true) &&
            actual.port == saved.port && actual.userInfo == null
    } catch (_: Exception) { false }

    private fun play(mediaId: Int) {
        if (mediaId <= 0) return
        startActivity(Intent(this, PlayerActivity::class.java)
            .putExtra("url", "$origin/api/playback/$mediaId/stream")
            .putExtra("media_id", mediaId)
            .putExtra("server", origin))
    }

    /**
     * WebView's native spatial navigation and page-level JavaScript navigation
     * must never both process one D-pad key. Dispatch exactly one focus move
     * on ACTION_DOWN; consume ACTION_UP as well so WebView cannot jump twice.
     */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val direction = when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT -> "left"
            KeyEvent.KEYCODE_DPAD_RIGHT -> "right"
            KeyEvent.KEYCODE_DPAD_UP -> "up"
            KeyEvent.KEYCODE_DPAD_DOWN -> "down"
            else -> null
        }
        val web = browser
        if (direction != null && web != null) {
            if (event.action == KeyEvent.ACTION_DOWN) {
                web.evaluateJavascript(
                    "window.__willieTvMove && window.__willieTvMove('$direction')",
                    null
                )
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun installRemoteNavigation(view: WebView) {
        // These are TV-specific focus affordances; the page/layout itself stays
        // 100% the live server version, including all future server updates.
        view.evaluateJavascript(TV_REMOTE_SCRIPT, null)
    }

    override fun onDestroy() {
        browser?.destroy()
        browser = null
        super.onDestroy()
    }

    companion object {
        private val TV_REMOTE_SCRIPT = """
            (() => {
              if (window.WilliePlayer && !window.WilliePlayer.__androidTv) {
                window.WilliePlayer.open = id => {
                  const mediaId=Number(id);
                  if (Number.isInteger(mediaId) && mediaId > 0)
                    location.href='oewtv://play/' + mediaId;
                };
                window.WilliePlayer.__androidTv=true;
              }
              if (document.getElementById('oew-tv-remote-style')) return;
              const style=document.createElement('style');
              style.id='oew-tv-remote-style';
              style.textContent=`
                /* Only the poster is highlighted; never outline the title/meta. */
                .tile-button:focus-visible,.tile-button:focus,
                .tile-button:hover {outline:none!important;box-shadow:none!important}
                /* Library page rules use !important on every focused link;
                   override those too so only the poster has a border. */
                body[data-page="movies"] .tile-button:focus-visible,
                body[data-page="tv"] .tile-button:focus-visible,
                body[data-page="home"] .tile-button:focus-visible{
                  outline:0!important;outline-offset:0!important;
                  box-shadow:none!important
                }
                .tile-button:focus-visible h3,.tile-button:focus h3,
                .tile-button:focus-visible .tile-meta,.tile-button:focus .tile-meta{
                  outline:0!important;box-shadow:none!important
                }
                .tile-button:focus-visible .cover,.tile-button:focus .cover {
                  outline:2px solid #ccdae6!important;outline-offset:4px!important;
                  border-color:#a1b6c7!important;
                  transform:none!important;box-shadow:0 9px 28px #0008!important;
                }
                .tile-button:hover .cover{transform:none!important}
                .tile:focus-within{transform:none!important}
                a:not(.tile-button):focus-visible,button:focus-visible,
                input:focus-visible,select:focus-visible,[tabindex="0"]:focus-visible{
                  outline:2px solid #b7c7d6!important;outline-offset:2px!important
                }
                /* Explore uses a full-card button. Focus ONLY its poster. */
                body[data-page="explore"] .explore-card .detail-trigger:focus-visible,
                body[data-page="explore"] .explore-card .detail-trigger:focus,
                body[data-page="explore"] .explore-card .detail-trigger:hover{
                  outline:none!important;box-shadow:none!important;border:0!important
                }
                body[data-page="explore"] .explore-card .detail-trigger:focus-visible .cover,
                body[data-page="explore"] .explore-card .detail-trigger:focus .cover{
                  outline:2px solid #ccdae6!important;outline-offset:3px!important;
                  border-color:#a1b6c7!important;box-shadow:0 9px 28px #0008!important
                }
                body[data-page="explore"] .explore-card:focus-within{
                  outline:none!important;box-shadow:none!important
                }
                body[data-page="explore"] .discovery-row .explore-card{
                  border-color:transparent!important;background:transparent!important;
                  padding:7px!important
                }
                body[data-page="explore"] .explore-results{
                  grid-template-columns:repeat(5,minmax(0,1fr))!important
                }
                                /* TV mode is cinematic and uses 4 roomy posters across. */
                .workspace{margin-left:0!important;position:relative;z-index:1}
                .workspace>.content,body[data-page="tv"] .workspace>.content,
                body[data-page="home"] .workspace>.content {
                  max-width:none!important;
                  padding-left:clamp(36px,5vw,95px)!important;
                  padding-right:clamp(36px,5vw,95px)!important
                }
                #items{grid-template-columns:repeat(5,minmax(0,1fr))!important;
                  gap:32px 20px!important}
                /* Fit five comfortable posters across TV WebView's CSS viewport.
                   Android TV often reports ~960 CSS px even on a 1080p set. */
                .shelf-track{grid-auto-columns:clamp(145px,18vw,218px)!important;
                  gap:19px!important}
                .discovery-row{grid-auto-columns:clamp(145px,18vw,218px)!important;
                  gap:19px!important}
                /* Hide navigation completely until remote focus enters the rail. */
                .sidebar,.sidebar:hover{
                  position:fixed!important;inset:0 auto 0 0!important;
                  width:85px!important;height:100vh!important;
                  transform:translateX(-110%)!important;
                  transition:transform .16s ease!important;
                  background:#0d1520f5!important;z-index:50!important;
                  box-shadow:none!important
                }
                .sidebar:focus-within{transform:translateX(0)!important;
                  width:85px!important;box-shadow:12px 0 35px #0009!important}
                .sidebar .brand,.sidebar:hover .brand,.sidebar:focus-within .brand{
                  width:100%!important;min-width:0!important}
                .sidebar .side-nav,.sidebar:hover .side-nav,
                .sidebar:focus-within .side-nav{align-items:center!important}
                .sidebar .nav-link,.sidebar:hover .nav-link,
                .sidebar:focus-within .nav-link{width:54px!important;
                  min-width:54px!important;justify-content:center!important;
                  padding:0!important}
                .sidebar .nav-text,.sidebar:focus-within .nav-text{display:none!important}
                .sidebar .settings-shortcuts{display:none!important}
                .workspace,.topbar,.content{background:transparent!important}
                body{background:#080d16!important}
                /* Match the server: the skull disappears with a real backdrop. */
                body:has(.willie-hover-backdrop-layer.is-visible) #items::before,
                body:has(.willie-hover-backdrop-layer.is-visible) .shelf-track::before,
                body:has(.willie-hover-backdrop-layer.is-visible) .explore-grid::before,
                body:has(.willie-hover-backdrop-layer.is-visible) .movie-grid::before,
                body:has(.willie-hover-backdrop-layer.is-visible) .tv-grid::before{
                  display:none!important
                }
                /* Android TV resolves genuine metadata backdrops independently,
                   so it also works before a server-side shell update deploys. */
                /* Keep the server's own working backdrop visible. */
                .willie-hover-backdrop{display:block!important}
                body:has(.willie-hover-backdrop-layer.is-visible) .oew-tv-cinematic-backdrop{opacity:0!important}
                .oew-tv-cinematic-backdrop{position:fixed;inset:0;z-index:1;
                  overflow:hidden;pointer-events:none;background:#080d16}
                .oew-tv-cinematic-image{position:absolute;inset:-3%;
                  background-position:center 28%;background-size:cover;
                  background-repeat:no-repeat;opacity:0;transform:scale(1.045);
                  transition:opacity .6s ease,transform 1.4s ease}
                .oew-tv-cinematic-image.is-visible{opacity:.92;transform:scale(1)}
                .oew-tv-cinematic-backdrop::after{content:"";position:absolute;
                  inset:0;background:
                  linear-gradient(90deg,#080d16aa 0%,#080d163d 45%,#080d1645 100%),
                  linear-gradient(0deg,#080d16cc 0%,#080d1638 45%,#080d1654 100%)}
                body>.app-shell{position:relative;z-index:2;background:transparent!important}
                body.oew-tv-backdrop-active #items::before,
                body.oew-tv-backdrop-active .shelf-track::before,
                body.oew-tv-backdrop-active .explore-grid::before,
                body.oew-tv-backdrop-active .movie-grid::before,
                body.oew-tv-backdrop-active .tv-grid::before{display:none!important}
                *{scroll-margin:26px}
                @media(max-width:750px){
                  #items{grid-template-columns:repeat(4,minmax(0,1fr))!important}
                }
                @media(max-width:520px){
                  #items{grid-template-columns:repeat(3,minmax(0,1fr))!important}
                }
              `;
              document.head.appendChild(style);

              // Exactly the server's widescreen metadata endpoints and visual
              // treatment, but driven by Android TV focus even on older servers.
              const backdrop=document.createElement('div');
              backdrop.className='oew-tv-cinematic-backdrop';
              backdrop.setAttribute('aria-hidden','true');
              const layers=[document.createElement('div'),document.createElement('div')];
              layers.forEach(layer=>{
                layer.className='oew-tv-cinematic-image';
                backdrop.appendChild(layer);
              });
              document.body.prepend(backdrop);
              const backdropCache=new Map();
              let backdropSerial=0,backdropCurrent='',backdropVisible=-1,backdropTarget=null;
              const validBackdrop=url=>typeof url==='string'&&(
                url.startsWith('/api/artwork/') ||
                url.startsWith('https://image.tmdb.org/t/p/'));
              const lookupBackdrop=async element=>{
                const direct=element.dataset.hoverBackdrop;
                if(validBackdrop(direct))return direct;
                let kind=element.dataset.hoverKind;
                let id=element.dataset.hoverLibraryId;
                let key=element.dataset.hoverKey;
                // Older deployed server pages may lack the data-hover fields.
                // Recover the same metadata identity from the card detail URL.
                if(!kind||!id||!key){
                  const link=element.matches('a[href]')?element:
                    element.querySelector('a[href*="library_id="]');
                  if(link){
                    const href=new URL(link.getAttribute('href'),location.href);
                    if(href.pathname==='/movie'||href.pathname==='/tv/show'){
                      kind=href.pathname==='/movie'?'movies':'tv';
                      id=href.searchParams.get('library_id');
                      key=href.searchParams.get('key');
                    }
                  }
                }
                if(!['movies','tv'].includes(kind)||!/^[0-9]+$/.test(id||'')||!key)
                  return null;
                const identity=kind+'|'+id+'|'+key;
                if(!backdropCache.has(identity)){
                  const query=new URLSearchParams({library_id:id,key});
                  const url=kind==='tv'?'/api/tv/show?'+query:'/api/movies/details?'+query;
                  const pending=fetch(url).then(response=>{
                    if(!response.ok)throw Error('Backdrop unavailable');
                    return response.json();
                  }).then(data=>validBackdrop(data.backdrop_url)?data.backdrop_url:null)
                    .catch(()=>null);
                  backdropCache.set(identity,pending);
                  if(backdropCache.size>90)backdropCache.delete(backdropCache.keys().next().value);
                }
                return backdropCache.get(identity);
              };
              const clearBackdrop=()=>{
                backdropSerial++;backdropCurrent='';backdropVisible=-1;
                layers.forEach(layer=>layer.classList.remove('is-visible'));
                document.body.classList.remove('oew-tv-backdrop-active');
              };
              const setBackdropTarget=async target=>{
                if(target===backdropTarget)return;
                backdropTarget=target;
                if(!target){clearBackdrop();return}
                const serial=++backdropSerial;
                const url=await lookupBackdrop(target);
                if(serial!==backdropSerial)return;
                if(!validBackdrop(url)){clearBackdrop();return}
                if(url===backdropCurrent)return;
                const image=new Image();
                image.onload=()=>{
                  if(serial!==backdropSerial)return;
                  const next=backdropVisible===0?1:0;
                  layers[next].style.backgroundImage='url("'+url.replaceAll('"','%22')+'")';
                  layers[next].classList.add('is-visible');
                  layers[1-next].classList.remove('is-visible');
                  backdropVisible=next;backdropCurrent=url;
                  document.body.classList.add('oew-tv-backdrop-active');
                };
                image.onerror=()=>{if(serial===backdropSerial)clearBackdrop()};
                image.src=url;
              };
              const locateBackdrop=target=>{
                if(!(target instanceof Element))return null;
                return target.closest('[data-hover-kind],[data-hover-backdrop]')||
                  target.closest('.tile-button,.detail-trigger');
              };
              document.addEventListener('focusin',event=>{
                setBackdropTarget(locateBackdrop(event.target));
              },true);
              document.addEventListener('mouseover',event=>{
                const target=locateBackdrop(event.target);
                if(target)setBackdropTarget(target);
              },{passive:true});
              document.addEventListener('mouseout',event=>{
                const target=locateBackdrop(event.target);
                if(target!==backdropTarget)return;
                if(event.relatedTarget instanceof Node&&target.contains(event.relatedTarget))return;
                const focused=locateBackdrop(document.activeElement);
                setBackdropTarget(focused);
              });
              document.addEventListener('visibilitychange',()=>{
                if(document.hidden){backdropTarget=null;clearBackdrop()}
              });
              if(locateBackdrop(document.activeElement))
                setBackdropTarget(locateBackdrop(document.activeElement));
              const selector='a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]';
              const visible=node=>{
                if (!node.isConnected || node.closest('[hidden],[inert],[aria-hidden="true"]')) return false;
                const style=getComputedStyle(node);
                if(style.display==='none'||style.visibility==='hidden'||style.pointerEvents==='none')return false;
                const r=node.getBoundingClientRect();
                return r.width>3&&r.height>3;
              };
              const focusables=()=>[...document.querySelectorAll(selector)].filter(visible);
              const contentSelector='.tile-button,.explore-card .detail-trigger,.episode-card a[href],.season-card a[href]';
              const firstContent=()=>[...document.querySelectorAll(contentSelector)].find(visible);
              const menuLinks=()=>[...document.querySelectorAll('#app-nav .nav-link')].filter(node=>node.isConnected);
              const focusItem=node=>{
                if(!node)return false;
                node.focus({preventScroll:true});
                node.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
                return true;
              };
              // Loading shelves populate asynchronously. Once the first real
              // poster exists, focus it instead of leaving focus in the rail.
              let initialFocusFinished=false,remoteUsed=false;
              const tryInitialFocus=()=>{
                if(initialFocusFinished||remoteUsed)return;
                const first=firstContent();
                if(!first)return;
                initialFocusFinished=focusItem(first);
                initialObserver.disconnect();
              };
              const initialObserver=new MutationObserver(tryInitialFocus);
              initialObserver.observe(document.body,{childList:true,subtree:true});
              requestAnimationFrame(tryInitialFocus);
              setTimeout(tryInitialFocus,350);
              setTimeout(()=>initialObserver.disconnect(),10000);
              const move=direction=>{
                remoteUsed=true;
                const nodes=focusables();
                if(!nodes.length)return false;
                const active=document.activeElement;
                const inMenu=active?.closest?.('#app-nav');
                const first=firstContent();
                if(inMenu && direction==='right'){
                  return focusItem(first||nodes.find(node=>!node.closest('#app-nav')));
                }
                if(inMenu && direction==='left')return true;
                if(!nodes.includes(active)){
                  return focusItem(first||nodes.find(node=>!node.closest('#app-nav'))||nodes[0]);
                }
                if(direction==='left' && first && !inMenu){
                  // A collapsed rail is off-screen. Give it a deliberate
                  // directional entry only at the left edge of the content.
                  const rect=active.getBoundingClientRect();
                  const peers=[...document.querySelectorAll(contentSelector)].filter(visible);
                  const sameRowLeft=peers.some(node=>{
                    if(node===active)return false;
                    const r=node.getBoundingClientRect();
                    return r.right<=rect.left+3 &&
                      Math.min(r.bottom,rect.bottom)>Math.max(r.top,rect.top);
                  });
                  if(!sameRowLeft){
                    const activeMenu=menuLinks().find(node=>node.getAttribute('aria-current')==='page')
                      ||menuLinks()[0];
                    return focusItem(activeMenu);
                  }
                }
                const from=active.getBoundingClientRect();
                const centerX=from.left+from.width/2,centerY=from.top+from.height/2;
                const horizontal=direction==='left'||direction==='right';
                let winner=null,best=Infinity;
                for(const node of nodes){
                  if(node===active || node.closest('#app-nav'))continue;
                  const r=node.getBoundingClientRect();
                  const dx=r.left+r.width/2-centerX,dy=r.top+r.height/2-centerY;
                  const forward=direction==='right'?dx>2:direction==='left'?dx< -2:
                                direction==='down'?dy>2:dy< -2;
                  if(!forward)continue;
                  const axis=Math.abs(horizontal?dx:dy);
                  const lateral=Math.abs(horizontal?dy:dx);
                  const overlap=horizontal?
                    Math.min(from.bottom,r.bottom)-Math.max(from.top,r.top):
                    Math.min(from.right,r.right)-Math.max(from.left,r.left);
                  // Stay on the same shelf/column instead of skipping diagonally.
                  const score=axis+lateral*(overlap>0?2:5)+
                    (overlap>0?0:Math.max(from.width,from.height)*0.3);
                  if(score<best){best=score;winner=node}
                }
                if(!winner)return true;
                winner.focus({preventScroll:true});
                winner.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
                return true;
              };
              window.__willieTvMove=move;
              // The Android Activity alone owns directional key handling. Do
              // not also install a document keydown listener: that double-moves.
              document.addEventListener('focusin',event=>{
                if(!visible(event.target))return;
                event.target.scrollIntoView?.({block:'nearest',inline:'nearest'});
              },true);
            })();
        """.trimIndent()
    }
}
