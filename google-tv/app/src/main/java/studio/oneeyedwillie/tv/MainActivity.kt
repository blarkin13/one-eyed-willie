package studio.oneeyedwillie.tv

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.JsPromptResult
import android.net.Uri
import org.json.JSONObject
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
                if (web == null) { showSetup(); return }
                // Closing the tiny episode menu must never navigate away from
                // the season page. Evaluation is asynchronous on the UI thread.
                web.evaluateJavascript("Boolean(window.__willieCloseSeasonMenu?.())") { result ->
                    if (result == "true") return@evaluateJavascript
                    if (web.canGoBack()) web.goBack()
                    else if (web.url != origin + "/") web.loadUrl(origin + "/")
                    else showSetup()
                }
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
        view.webChromeClient = object : WebChromeClient() {
            override fun onJsPrompt(
                web: WebView, url: String, message: String,
                defaultValue: String?, result: JsPromptResult
            ): Boolean {
                if (!sameOrigin(url) || !message.startsWith("oewtv:play:"))
                    return super.onJsPrompt(web, url, message, defaultValue, result)
                try {
                    val payload = JSONObject(Uri.decode(message.removePrefix("oewtv:play:")))
                    val id = payload.optInt("id")
                    if (id <= 0) throw IllegalArgumentException("Invalid media ID")
                    result.confirm("ACK")
                    web.post {
                        if (browser === web)
                            play(id, payload.optBoolean("restart", false),
                                payload.optString("title", "Now Playing"),
                                payload.optJSONArray("shuffle_queue")?.toString())
                    }
                } catch (_: Exception) {
                    result.confirm("INVALID")
                }
                return true
            }
        }
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(web: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (uri.scheme == "oewtv" && uri.host == "play") {
                    uri.path?.trim('/')?.toIntOrNull()?.takeIf { it > 0 }?.let {
                        play(it, uri.getQueryParameter("restart") == "1",
                            uri.getQueryParameter("title").orEmpty())
                    }
                    return true
                }
                if (uri.path?.matches(Regex("/watch/[0-9]+")) == true && sameOrigin(uri.toString())) {
                    uri.lastPathSegment?.toIntOrNull()?.let {
                        play(it, uri.getQueryParameter("restart") == "1", "Now Playing")
                    }
                    return true
                }
                // Only open approved HTTPS metadata destinations outside our
                // embedded server WebView. Rotten Tomatoes review links must be
                // usable on Google TV instead of silently being blocked.
                if (!sameOrigin(uri.toString())) {
                    val host = uri.host?.lowercase().orEmpty()
                    if (uri.scheme == "https" && host in setOf(
                            "www.rottentomatoes.com", "rottentomatoes.com",
                            "www.imdb.com", "www.youtube.com", "youtube.com"
                        )) {
                        try {
                            startActivity(Intent(Intent.ACTION_VIEW, uri)
                                .addCategory(Intent.CATEGORY_BROWSABLE))
                        } catch (_: android.content.ActivityNotFoundException) {
                            android.widget.Toast.makeText(this@MainActivity,
                                "No browser is installed to open this link",
                                android.widget.Toast.LENGTH_LONG).show()
                        }
                    }
                    return true
                }
                return false
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

    private fun play(mediaId: Int, restart: Boolean = false, title: String = "",
                     shuffleQueue: String? = null) {
        if (mediaId <= 0) return
        startActivity(Intent(this, PlayerActivity::class.java)
            .putExtra("url", "$origin/api/playback/$mediaId/stream")
            .putExtra("media_id", mediaId)
            .putExtra("restart", restart)
            .putExtra("title", title.take(160))
            .putExtra("server", origin)
            .apply { if (shuffleQueue != null) putExtra("shuffle_queue", shuffleQueue) })
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
        if (event.keyCode == KeyEvent.KEYCODE_BACK && web != null) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
                // Explore More opens its details within the same WebView
                // document. Close that view before leaving the whole page.
                web.evaluateJavascript(
                    """(() => {
                        const panel = document.getElementById('explore-detail');
                        if (panel && !panel.hidden && typeof window.restoreExplore === 'function') {
                            window.restoreExplore();
                            return true;
                        }
                        return false;
                    })()""".trimIndent()
                ) { result ->
                    if (browser === web && result != "true") {
                        if (web.canGoBack()) web.goBack() else finish()
                    }
                }
            }
            return true
        }
        if (direction != null && web != null) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
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

    override fun onResume() {
        super.onResume()
        // Native Media3 playback runs in another Activity. Refresh the
        // underlying season page's watched flags and resume positions when
        // returning to its WebView, without navigating away from the show.
        browser?.evaluateJavascript(
            "document.dispatchEvent(new Event('willie:watch-updated'))", null
        )
    }

    override fun onDestroy() {
        browser?.destroy()
        browser = null
        super.onDestroy()
    }

    companion object {
        private val TV_REMOTE_SCRIPT = """
            (() => {
              // Intercept every existing Play/Resume entry point even if the
              // deferred server player.js loads after this WebView callback.
              const nativeOpen=(id,title,options={})=>{
                const mediaId=Number(id);
                if(!Number.isInteger(mediaId)||mediaId<=0)return;
                const query=new URLSearchParams();
                if(options?.restart)query.set('restart','1');
                if(title)query.set('title',String(title).slice(0,160));
                // Synchronous WebChromeClient handoff is reliable for WebView
                // JS click handlers; keep the URL route as a fallback.
                const payload={id:mediaId,restart:Boolean(options?.restart),
                               title:String(title||'Now Playing').slice(0,160)};
                if(Array.isArray(options?.shuffleQueue))
                  payload.shuffle_queue=options.shuffleQueue.slice(0,500);
                let ack=null;
                try{ack=prompt('oewtv:play:'+encodeURIComponent(JSON.stringify(payload)),'')}
                catch(_){}
                if(ack!=='ACK')location.href='oewtv://play/'+mediaId+'?'+query.toString();
              };
              const nativeShuffle=(episodes)=>{
                if(!Array.isArray(episodes))return;
                const list=episodes.slice(0,500)
                  .filter(item=>Number.isInteger(item?.id)&&item.id>0)
                  .map(item=>({media_id:item.id,title:String(item.title||'Episode').slice(0,160),
                    restart:!item.resume}));
                for(let i=list.length-1;i>0;i--){
                  const j=Math.floor(Math.random()*(i+1));
                  [list[i],list[j]]=[list[j],list[i]];
                }
                if(!list.length)return;
                const first=list[0];
                nativeOpen(first.media_id,first.title,
                  {restart:first.restart,shuffleQueue:list.slice(1)});
              };
              const installPlayerHook=()=>{
                if(!window.WilliePlayer)window.WilliePlayer={open:nativeOpen,close:()=>{}};
                else window.WilliePlayer.open=nativeOpen;
                window.WilliePlayer.shuffleSeason=nativeShuffle;
                window.WilliePlayer.__androidTv=true;
              };
              installPlayerHook();
              let hookRetries=0;
              const hookTimer=setInterval(()=>{
                installPlayerHook();
                if(++hookRetries>=24)clearInterval(hookTimer);
              },250);
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
                /* Cast filmography credit links wrap the title and role as well.
                   Focus only the poster, not the full text/card rectangle. */
                body[data-page="movies"] .person-credits .person-credit-link:is(:focus,:focus-visible,:hover){
                  outline:0!important;outline-offset:0!important;
                  box-shadow:none!important;background:transparent!important;
                  border:0!important
                }
                body[data-page="movies"] .person-credits .person-credit-link:is(:focus,:focus-visible) .person-credit-poster{
                  outline:2px solid #ccdae6!important;outline-offset:3px!important;
                  border-color:#a1b6c7!important;box-shadow:0 9px 28px #0008!important
                }
                body[data-page="movies"] .person-credits .person-credit-link:is(:focus,:focus-visible) :is(strong,small){
                  outline:0!important;box-shadow:none!important;
                  text-decoration:none!important
                }
                /* Episode cards are also selectable art: no text block or
                   other card chrome is included in D-pad focus. */
                body[data-page="tv"] .season-episode-tile:is(:focus,:focus-visible){
                  outline:3px solid #d5eaff!important;outline-offset:3px!important;
                  box-shadow:none!important
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
                /* Home-only trial: 60% of the current poster dimensions,
                   preserving the original 2:3 artwork ratio. */
                body[data-page="home"] .shelf-track{
                  grid-auto-columns:clamp(87px,10.8vw,130.8px)!important;
                  grid-template-rows:max-content!important;
                  grid-auto-rows:0!important;
                  align-items:start!important;align-content:start!important;
                  gap:14px!important;
                  padding:11px 11px 9px!important;
                  width:calc(100% + 22px)!important;
                  margin:0 -11px!important;
                  overflow-y:hidden!important;
                  min-height:0!important;
                  scroll-padding-inline:11px!important
                }
                /* Shorter Home shelves: no reserved height from the old
                   large-card layout and adequate room for D-pad focus rings. */
                body[data-page="home"] .shelf{
                  margin-top:13px!important;min-height:0!important
                }
                body[data-page="home"] .shelf:first-of-type{
                  margin-top:0!important
                }
                body[data-page="home"] .shelf .section-heading{
                  margin-bottom:5px!important
                }
                body[data-page="home"] .shelf-track .tile{
                  min-height:0!important;align-self:start!important
                }
                body[data-page="home"] .shelf-track .tile h3{
                  margin:5px 0 2px!important;line-height:1.17!important
                }
                /* The server supplies the same anchor-based watched flag on
                   Google TV as in the browser, without a checkmark overlay. */
                body[data-page="home"] .watched-badge{
                  position:absolute!important;top:6px!important;right:6px!important;
                  z-index:5!important;display:grid!important;place-items:center!important;
                  width:24px!important;height:24px!important;
                  padding:0!important;border-radius:50%!important;
                  background:#091929e8!important;border:1px solid #7faec4!important;
                  color:#d7edf8!important;pointer-events:none!important
                }
                body[data-page="home"] .watched-badge svg{
                  display:block!important;width:17px!important;height:17px!important
                }
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
                /* The server switches navigation into a fixed bottom tab bar
                   at <=700 CSS px. TVs can report that width despite a large
                   physical display. Force the vertical rail on Android TV. */
                .sidebar,.sidebar:hover,.sidebar:focus-within{
                  display:flex!important;flex-direction:column!important;
                  position:fixed!important;inset:0 auto 0 0!important;
                  width:85px!important;height:100vh!important;
                  padding:18px 7px!important;border:0!important;
                  overflow:visible!important;align-items:stretch!important;
                  background:#0d1520f5!important;z-index:50!important
                }
                .sidebar .side-nav,.sidebar:hover .side-nav,
                .sidebar:focus-within .side-nav{
                  display:flex!important;flex-direction:column!important;
                  align-items:center!important;justify-content:flex-start!important;
                  position:relative!important;inset:auto!important;
                  width:100%!important;height:auto!important;
                  max-height:calc(100vh - 116px)!important;
                  overflow-x:hidden!important;overflow-y:auto!important;
                  flex:1 1 auto!important;min-height:0!important;
                  padding:8px 0!important;margin:0!important;
                  gap:7px!important;border:0!important;
                  background:transparent!important;backdrop-filter:none!important
                }
                .sidebar .side-nav .nav-link,
                .sidebar:hover .side-nav .nav-link,
                .sidebar:focus-within .side-nav .nav-link{
                  display:flex!important;position:relative!important;
                  flex:0 0 49px!important;height:49px!important;
                  width:61px!important;min-width:61px!important;
                  max-width:61px!important;min-height:49px!important;
                  padding:0!important;margin:0!important;
                  align-items:center!important;justify-content:center!important
                }
                .sidebar .nav-link[data-service-nav="radarr"],
                .sidebar .nav-link[data-service-nav="sonarr"],
                .sidebar .nav-link[data-service-nav="sabnzbd"]{
                  display:flex!important
                }
                .sidebar .nav-link[data-service-nav="services"]{
                  display:none!important
                }
                .mobile-settings-sheet{display:none!important}
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
                /* Android TV has a Back key. Don't add browser-only links
                   to the cinematic movie page or the D-pad focus sequence. */
                body[data-page="movies"] .movie-back,
                body[data-page="movies"] #imdb-link,
                body[data-page="movies"] .movie-detail-data>p:has(#imdb-link){
                  display:none!important
                }
                                /* Cinematic TV movie details: one glance shows artwork,
                   title, playback actions and the opening cast row. */
                body[data-page="movies"] .workspace>.content:has(.movie-detail-hero){
                  padding:0 0 42px!important;max-width:none!important
                }
                body[data-page="movies"] .movie-back{
                  position:relative!important;z-index:5!important;
                  margin:10px clamp(26px,5.2vw,84px) 0!important;
                  font-size:.88rem!important
                }
                body[data-page="movies"] #movie-status{
                  margin:0 clamp(26px,5.2vw,84px)!important
                }
                body[data-page="movies"] #movie-status:empty{display:none!important}
                body[data-page="movies"] .movie-detail-hero{
                  display:flex!important;flex-direction:row!important;
                  align-items:flex-end!important;justify-content:flex-start!important;
                  box-sizing:border-box!important;
                  width:100%!important;height:auto!important;
                  min-height:clamp(275px,49vh,500px)!important;
                  padding:12px clamp(26px,5.2vw,84px) 23px!important;
                  margin:0!important;border:0!important;border-radius:0!important;
                  background:transparent!important;gap:0!important;
                  isolation:isolate!important;overflow:hidden!important
                }
                body[data-page="movies"] .movie-detail-hero[hidden]{display:none!important}
                body[data-page="movies"] .movie-detail-hero::after{
                  background:
                    linear-gradient(90deg,#080d16f2 0%,#080d16cf 35%,#080d165a 67%,#080d1619 100%),
                    linear-gradient(0deg,#080d16f8 0%,#080d1600 65%)!important
                }
                body[data-page="movies"] .movie-detail-backdrop{
                  display:block!important;position:absolute!important;
                  inset:0!important;width:100%!important;height:100%!important;
                  object-fit:cover!important;object-position:center 28%!important;
                  opacity:.90!important;filter:none!important
                }
                body[data-page="movies"] .movie-detail-backdrop[hidden]{display:none!important}
                /* The cinematic backdrop is already the artwork. Don't use
                   a second oversized portrait taking room from the actions. */
                body[data-page="movies"] .movie-detail-hero>.movie-detail-poster{
                  display:none!important
                }
                body[data-page="movies"] .movie-detail-data{
                  display:flex!important;flex-direction:column!important;
                  align-items:flex-start!important;
                  width:min(64%,760px)!important;max-width:100%!important;
                  min-width:0!important;gap:0!important;
                  margin:0!important;padding:0!important;
                  position:relative!important;z-index:1!important
                }
                body[data-page="movies"] .movie-detail-data .eyebrow{display:none!important}
                body[data-page="movies"] .movie-detail-data h1{
                  order:1!important;font-size:clamp(2rem,4.3vw,4rem)!important;
                  line-height:1.02!important;letter-spacing:-.055em!important;
                  margin:0 0 8px!important;font-weight:770!important
                }
                body[data-page="movies"] .movie-detail-data .movie-meta{
                  order:2!important;display:flex!important;flex-wrap:wrap!important;
                  font-size:.89rem!important;line-height:1.25!important;
                  letter-spacing:-.012em!important;margin:0 0 6px!important
                }
                body[data-page="movies"] .movie-detail-data .movie-ratings{
                  order:3!important;display:flex!important;flex-wrap:wrap!important;
                  gap:5px 16px!important;max-width:100%!important;
                  margin:1px 0 8px!important
                }
                body[data-page="movies"] .movie-detail-data .rating-item{
                  display:inline-flex!important;align-items:baseline!important;
                  gap:5px!important;font-size:.84rem!important;
                  line-height:1.2!important;letter-spacing:-.012em!important
                }
                body[data-page="movies"] .movie-detail-data .rating-item strong{
                  font-size:.72rem!important
                }
                body[data-page="movies"] .movie-detail-genres{
                  order:4!important;font-size:.86rem!important;
                  margin:0 0 6px!important;line-height:1.24!important
                }
                body[data-page="movies"] .movie-detail-data .movie-description{
                  order:5!important;font-size:clamp(.88rem,1.35vw,1rem)!important;
                  line-height:1.31!important;letter-spacing:-.012em!important;
                  margin:0 0 7px!important;max-width:650px!important;
                  display:-webkit-box!important;-webkit-box-orient:vertical!important;
                  -webkit-line-clamp:3!important;overflow:hidden!important
                }
                body[data-page="movies"] .movie-detail-credit{
                  order:6!important;font-size:.78rem!important;
                  margin:0 0 6px!important;line-height:1.2!important
                }
                body[data-page="movies"] .movie-detail-actions{
                  order:7!important;display:flex!important;flex-wrap:wrap!important;
                  align-items:center!important;gap:11px!important;
                  margin:3px 0 3px!important
                }
                body[data-page="movies"] .movie-detail-actions .media-icon-action{
                  width:48px!important;height:48px!important;min-height:48px!important;
                  background:transparent!important;border:0!important;
                  border-radius:50%!important;padding:10px!important
                }
                body[data-page="movies"] .movie-detail-actions .media-icon-action:focus-visible{
                  outline:2px solid #d3e8fc!important;outline-offset:2px!important;
                  background:#2b46648f!important
                }
                body[data-page="movies"] .movie-detail-progress{
                  order:8!important;margin:5px 0 0!important;height:4px!important
                }
                body[data-page="movies"] #progress-label{
                  order:9!important;font-size:.76rem!important;
                  margin:3px 0 0!important;line-height:1.2!important
                }
                body[data-page="movies"] .movie-detail-data>p:has(#imdb-link){
                  order:10!important;margin:5px 0 0!important;font-size:.77rem!important
                }
                /* Cast immediately follows the cinematic hero rather than
                   waiting behind the ratings, studios and technical facts. */
                body[data-page="movies"] .movie-expanded{
                  display:flex!important;flex-direction:column!important;
                  padding:0 clamp(26px,5.2vw,84px) 42px!important;
                  max-width:none!important;gap:0!important
                }
                body[data-page="movies"] .movie-expanded[hidden]{display:none!important}
                body[data-page="movies"] #cast-section{
                  order:1!important;border:0!important;
                  padding:6px 0 23px!important;margin:0!important
                }
                body[data-page="movies"] #cast-section h2{
                  font-size:1.15rem!important;margin:0 0 11px!important
                }
                body[data-page="movies"] .movie-facts{
                  order:2!important;gap:10px!important;
                  margin:13px 0 24px!important;padding-top:18px!important;
                  border-top:1px solid #27364a!important
                }
                body[data-page="movies"] #reviews-section{order:3!important}
                body[data-page="movies"] .movie-block{
                  padding:20px 0 30px!important
                }
                body[data-page="movies"] .movie-block h2{
                  margin-bottom:13px!important
                }
                body[data-page="movies"] .movie-fact-list{
                  gap:5px 16px!important;line-height:1.26!important;
                  letter-spacing:-.012em!important
                }
                body[data-page="movies"] .movie-cast{
                  display:grid!important;grid-auto-flow:column!important;
                  grid-auto-columns:clamp(92px,10vw,122px)!important;
                  gap:clamp(13px,1.8vw,22px)!important;overflow-x:auto!important;
                  overflow-y:hidden!important;padding:5px 5px 12px!important;
                  scroll-snap-type:none!important
                }
                body[data-page="movies"] .cast-person{
                  display:flex!important;flex-direction:column!important;
                  min-width:0!important;gap:3px!important;
                  text-decoration:none!important;color:inherit!important
                }
                body[data-page="movies"] .cast-person img,
                body[data-page="movies"] .cast-person .cast-blank{
                  box-sizing:border-box!important;
                  width:100%!important;aspect-ratio:1/1!important;
                  height:auto!important;object-fit:cover!important;
                  border-radius:50%!important
                }
                body[data-page="movies"] .cast-person:focus,
                body[data-page="movies"] .cast-person:focus-visible{
                  outline:0!important;box-shadow:none!important
                }
                body[data-page="movies"] .cast-person:focus img,
                body[data-page="movies"] .cast-person:focus .cast-blank,
                body[data-page="movies"] .cast-person:focus-visible img,
                body[data-page="movies"] .cast-person:focus-visible .cast-blank{
                  outline:2px solid #d4e8fb!important;outline-offset:3px!important;
                  box-shadow:0 6px 20px #0008!important
                }
                body[data-page="movies"] .cast-person strong,
                body[data-page="movies"] .cast-person span{
                  display:-webkit-box!important;-webkit-box-orient:vertical!important;
                  -webkit-line-clamp:1!important;overflow:hidden!important;
                  line-height:1.22!important;letter-spacing:-.012em!important;
                  font-size:.78rem!important
                }
                body[data-page="movies"] .cast-person strong{
                  margin-top:5px!important;font-size:.84rem!important
                }
                @media(max-width:650px){
                  body[data-page="movies"] .movie-detail-data{width:80%!important}
                  body[data-page="movies"] .movie-detail-hero{
                    min-height:clamp(275px,56vh,420px)!important
                  }
                  body[data-page="movies"] .movie-detail-data h1{
                    font-size:clamp(1.6rem,4.5vw,2.7rem)!important
                  }
                }
                /* Shared scale selection on all TV screens: the artwork/icon
                   grows, without either a card border or a second white box. */
                body[data-page] :is(a,button,select,[tabindex="0"]):is(:focus,:focus-visible){
                  outline:0!important;outline-offset:0!important;
                  box-shadow:none!important;filter:brightness(1.16)
                }
                body[data-page] .tile-button:is(:focus,:focus-visible) .cover,
                body[data-page] .detail-trigger:is(:focus,:focus-visible) .cover,
                body[data-page] .person-credit-link:is(:focus,:focus-visible) .person-credit-poster{
                  outline:0!important;border-color:transparent!important;
                  box-shadow:none!important;transform:scale(1.07)!important;
                  filter:brightness(1.16)!important;position:relative;z-index:3
                }
                body[data-page] .season-episode-tile:is(:focus,:focus-visible){
                  outline:0!important;border-color:transparent!important;
                  box-shadow:none!important;transform:scale(1.07)!important;
                  filter:brightness(1.16)!important;z-index:3
                }
                body[data-page] .season-episode-tile.is-selected{
                  border-color:transparent!important;box-shadow:none!important
                }
                body[data-page] :is(.media-icon-action,.icon-only-control,.nav-link,
                  .season-tabs a):is(:focus,:focus-visible){
                  outline:0!important;box-shadow:none!important;
                  transform:scale(1.16)!important;filter:brightness(1.24)!important;
                  background:transparent!important;color:#fff!important
                }
                body[data-page] :is(.cast-person,.tv-cast-person,.credit-cast a)
                  :is(:focus,:focus-visible) :is(img,.cast-blank,.tv-actor-image,.credit-empty-photo){
                  outline:0!important;box-shadow:none!important;
                  transform:scale(1.07)!important;filter:brightness(1.15)!important
                }
                body[data-page] .explore-card:focus-within,
                body[data-page] .person-credit-link:is(:focus,:focus-visible){
                  outline:0!important;box-shadow:none!important;border-color:transparent!important
                }
                /* No smooth page scrolling or shelf snap while using D-pad. */
                html,body{scroll-behavior:auto!important;scroll-padding:0!important}
                .shelf-track,.discovery-row{
                  scroll-snap-type:none!important;scroll-behavior:auto!important;
                }
                *{scroll-margin:0!important;scroll-behavior:auto!important}
                @media(max-width:750px){
                  #items{grid-template-columns:repeat(4,minmax(0,1fr))!important}
                }
                @media(max-width:520px){
                  #items{grid-template-columns:repeat(3,minmax(0,1fr))!important}
                }
              `;
              document.head.appendChild(style);

              // Move the existing ratings strip into the TV hero. The server
              // continues updating the same #rating-list node when metadata loads.
              if(document.getElementById('movie-detail')){
                const ratings=document.getElementById('rating-list');
                const details=document.querySelector('.movie-detail-data');
                if(ratings&&details&&ratings.parentElement!==details)
                  details.appendChild(ratings);
              }

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
              // Dedicated remote navigation: menu items are a vertical list,
              // while content posters are traversed by adjacent row/column.
              const selector='a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]';
              const isVisible=node=>{
                if(!node?.isConnected || node.closest('[hidden],[inert],[aria-hidden="true"]'))return false;
                const style=getComputedStyle(node);
                if(style.display==='none'||style.visibility==='hidden'||style.pointerEvents==='none')return false;
                const r=node.getBoundingClientRect();
                return r.width>3&&r.height>3;
              };
              // Cast links contain long role descriptions. For directional
              // navigation use the portrait's geometry, not the whole card.
              const rect=node=>{
                if(node?.matches?.('.cast-person,.person-credit-link')){
                  const portrait=node.querySelector(
                    node.matches('.person-credit-link')
                      ?'.person-credit-poster'
                      :'img,.cast-blank'
                  );
                  if(portrait)return portrait.getBoundingClientRect();
                }
                return node.getBoundingClientRect();
              };
              const centerX=r=>r.left+r.width/2;
              const centerY=r=>r.top+r.height/2;
              const candidates=()=>[...document.querySelectorAll(selector)].filter(isVisible)
                .filter(node=>!node.matches('[data-season-scroll-arrow]'));
              const allMenu=()=>[...document.querySelectorAll('#app-nav .side-nav .nav-link')].filter(isVisible);
              const isMenu=node=>Boolean(node?.closest?.('#app-nav'));
              const contentSelector='.tile-button,.explore-card .detail-trigger,.episode-card a[href],.season-card a[href],.person-credit-link,.season-episode-tile';
              const allPosters=()=>[...document.querySelectorAll(contentSelector)].filter(isVisible);
              const firstPoster=()=>allPosters()[0]||null;
              const focusNode=node=>{
                if(!node)return false;
                node.focus({preventScroll:true});
                let r=rect(node);
                const padding=44;
                // Only scroll enough to reveal a genuinely clipped selection.
                // scrollIntoView() caused entire shelves to snap/jump by a row.
                if(isMenu(node)){
                  const scroller=node.closest('.side-nav');
                  if(scroller){
                    const outer=rect(scroller);
                    if(r.top<outer.top+8)scroller.scrollTop-=outer.top+8-r.top;
                    else if(r.bottom>outer.bottom-8)scroller.scrollTop+=r.bottom-outer.bottom+8;
                  }
                }else{
                  const shelf=node.closest('.shelf-track,.discovery-row,.movie-cast,.season-episode-track,.season-tabs');
                  if(shelf){
                    // Reveal the target in its own horizontal row before moving
                    // the page. Hidden rail items still have valid DOM geometry.
                    const bounds=rect(shelf);
                    const deltaX=r.left<bounds.left+16?r.left-bounds.left-16:
                      r.right>bounds.right-16?r.right-bounds.right+16:0;
                    if(Math.abs(deltaX)>1){
                      shelf.scrollLeft=Math.max(0,Math.min(
                        shelf.scrollWidth-shelf.clientWidth,shelf.scrollLeft+deltaX));
                    }
                    r=rect(node);
                  }
                  const delta=r.top<padding?r.top-padding:
                    r.bottom>innerHeight-padding?r.bottom-(innerHeight-padding):0;
                  if(Math.abs(delta)>1)window.scrollBy({top:delta,left:0,behavior:'instant'});
                }
                return true;
              };
              const findAdjacent= (active, direction, pool)=>{
                const from=rect(active), x=centerX(from), y=centerY(from);
                const horizontal=direction==='left'||direction==='right';
                const forwardSign=(direction==='right'||direction==='down')?1:-1;
                let best=null,score=Infinity;
                for(const node of pool){
                  if(node===active)continue;
                  const r=rect(node), dx=centerX(r)-x,dy=centerY(r)-y;
                  const along=(horizontal?dx:dy)*forwardSign;
                  if(along<=3)continue;
                  const side=Math.abs(horizontal?dy:dx);
                  const overlap=horizontal?
                    Math.min(from.bottom,r.bottom)-Math.max(from.top,r.top):
                    Math.min(from.right,r.right)-Math.max(from.left,r.left);
                  // Prefer the immediate adjacent card in the current
                  // row/column instead of a distant diagonal control.
                  const penalty=overlap>0?0:1000+side*4;
                  const value=along+side*2.5+penalty;
                  if(value<score){score=value;best=node}
                }
                return best;
              };
              // Text sections (reviews, technical facts, long descriptions)
              // don't have focusable children. The remote must still scroll
              // through them after the last selectable item.
              let readingScroll=false;
              const scrollRead=direction=>{
                const root=document.scrollingElement||document.documentElement;
                const amount=Math.round(Math.min(240,Math.max(115,innerHeight*.29)));
                const before=root.scrollTop;
                const max=Math.max(0,root.scrollHeight-root.clientHeight);
                const target=Math.max(0,Math.min(max,before+
                  (direction==='down'?amount:-amount)));
                root.scrollTop=target;
                return Math.abs(root.scrollTop-before)>1;
              };
              // Detail pages use vertical *sections*, not a search for the
              // nearest item under the currently focused column. Libraries
              // and poster grids retain spatial navigation.
              const detailSections=()=>{
                const path=location.pathname;
                if(path==='/tv/show')return [
                  {scope:'.series-controls', first:'#series-play-button,.series-controls button:not(:disabled)'},
                  {scope:'.season-grid', first:'#series-first-season,.season-grid .tile-button'},
                  {scope:'.tv-extras .tv-cast', first:'.tv-extras .tv-cast .tv-cast-person'},
                  {scope:'.tv-extras .tv-reviews', first:'.tv-extras .tv-reviews button'}
                ];
                if(path==='/tv/season')return [
                  {scope:'.season-tabs', first:'.season-tabs a[aria-current="page"],.season-tabs a[href]'},
                  {scope:'.season-episode-track', first:'.season-episode-tile.is-selected,.season-episode-tile'},
                  {scope:'.season-actions-row', first:'#season-play-button'},
                  {scope:'.season-support .tv-cast', first:'.season-support .tv-cast .tv-cast-person'},
                  {scope:'.season-support .tv-reviews', first:'.season-support .tv-reviews button'}
                ];
                if(path==='/movie')return [
                  {scope:'.movie-detail-actions', first:'#play-movie'},
                  {scope:'.movie-cast', first:'.movie-cast .cast-person'},
                  {scope:'.movie-reviews', first:'.movie-reviews button'}
                ];
                if(path==='/credit')return [
                  {scope:'.credit-actions', first:'.credit-actions button:not(:disabled)'},
                  {scope:'.credit-cast', first:'.credit-cast a[href]'},
                  {scope:'.credit-reviews', first:'.credit-reviews button'}
                ];
                if(path==='/person')return [
                  {scope:'.person-sources', first:'.person-sources a[href]'},
                  {scope:'.person-credits', first:'.person-credits .person-credit-link'}
                ];
                return [];
              };
              const moveThroughSections=(active,direction)=>{
                if(direction!=='up'&&direction!=='down')return false;
                const lanes=detailSections();
                const index=lanes.findIndex(lane=>active?.closest?.(lane.scope));
                if(index<0)return false;
                const delta=direction==='down'?1:-1;
                for(let i=index+delta;i>=0&&i<lanes.length;i+=delta){
                  const item=[...document.querySelectorAll(lanes[i].first)].find(isVisible);
                  if(item){readingScroll=false;return focusNode(item)}
                }
                if(scrollRead(direction))readingScroll=true;
                return true;
              };
              const move=direction=>{
                // Native D-pad must stay inside modal dialogs, including
                // episode actions and the subsequent Fix Match results dialog.
                const menu=document.querySelector('dialog[open],.season-more-popover');
                if(menu){
                  const options=[...menu.querySelectorAll(
                    'button:not(:disabled),input:not(:disabled),a[href],select:not(:disabled)'
                  )].filter(isVisible);
                  const index=options.indexOf(document.activeElement);
                  if(direction==='up'||direction==='down'){
                    const step=direction==='down'?1:-1;
                    const next=Math.max(0,Math.min(options.length-1,index+step));
                    return focusNode(options[next]||options[0]);
                  }
                  return true;
                }
                const nodes=candidates();
                if(!nodes.length)return false;
                const active=document.activeElement;
                // Intentional TV navigation: every episode tile leads DOWN to
                // the current Play action, even when the tile is scrolled
                // horizontally beyond the location of the action row.
                if(direction==='down'&&active?.matches?.('.season-episode-tile')){
                  const play=document.getElementById('season-play-button');
                  if(play&&isVisible(play)){readingScroll=false;return focusNode(play)}
                }
                if(direction==='up'&&active?.id==='season-play-button'){
                  const episode=document.querySelector('.season-episode-tile.is-selected');
                  if(episode&&isVisible(episode)){readingScroll=false;return focusNode(episode)}
                }
                if(isMenu(active)){
                  if(direction==='right'){
                    // Leave the rail at the content item closest to the
                    // current selection, never trap focus inside the menu.
                    const posters=allPosters();
                    const target=findAdjacent(active,'right',posters)||posters[0]||
                      nodes.find(node=>!isMenu(node));
                    return focusNode(target);
                  }
                  if(direction==='left')return true;
                  const menu=allMenu();
                  const index=menu.indexOf(active);
                  if(index<0)return focusNode(menu[0]);
                  const next=index+(direction==='down'?1:-1);
                  return focusNode(menu[Math.max(0,Math.min(menu.length-1,next))]);
                }
                // Page-level vertical navigation moves to the first item of the
                // next logical section, including Series actions -> Season 1.
                if(moveThroughSections(active,direction))return true;
                // Horizontal season/episode rails must follow DOM order rather
                // than global spatial search. D-pad focus must scroll each rail
                // to reveal its next item, including items initially offscreen.
                if((direction==='left'||direction==='right')&&active?.closest){
                  const rail=active.closest('.season-tabs,.season-episode-track');
                  if(rail){
                    const entries=[...rail.querySelectorAll(
                      rail.matches('.season-tabs')?'a[href]':'.season-episode-tile'
                    )].filter(isVisible);
                    const index=entries.indexOf(active);
                    if(index>=0){
                      readingScroll=false;
                      const next=index+(direction==='right'?1:-1);
                      if(next>=0&&next<entries.length)return focusNode(entries[next]);
                      if(direction==='left'&&index===0){
                        const menu=allMenu();
                        return focusNode(menu.find(n=>n.getAttribute('aria-current')==='page')||menu[0]);
                      }
                      return true;
                    }
                  }
                }
                // While reading below the last selectable element, move the
                // document by a modest distance per press instead of snapping
                // focus back to a cast portrait or to the hero.
                if(readingScroll && (direction==='up'||direction==='down')){
                  scrollRead(direction);
                  if(direction==='up'){
                    const r=rect(active);
                    if(r.bottom>30 && r.top<innerHeight*.76)readingScroll=false;
                  }
                  return true;
                }
                if(direction==='left'||direction==='right')readingScroll=false;
                const posters=allPosters();
                if(!nodes.includes(active))return focusNode(posters[0]||nodes.find(n=>!isMenu(n)));
                const from=rect(active);
                const sameRowLeft=posters.some(node=>{
                  if(node===active)return false;
                  const r=rect(node);
                  return r.right<=from.left+3 &&
                    Math.min(r.bottom,from.bottom)>Math.max(r.top,from.top);
                });
                if(direction==='left' && posters.includes(active) && !sameRowLeft){
                  const menu=allMenu();
                  return focusNode(menu.find(n=>n.getAttribute('aria-current')==='page')||menu[0]);
                }
                // If currently on a poster, choose the immediately adjacent
                // poster in its row or column before any unrelated controls.
                if(posters.includes(active)){
                  const adjacent=findAdjacent(active,direction,posters);
                  if(adjacent)return focusNode(adjacent);
                }
                const other=nodes.filter(node=>!isMenu(node));
                const next=findAdjacent(active,direction,other);
                if(next)return focusNode(next);
                if(direction==='up'||direction==='down'){
                  if(scrollRead(direction)){
                    readingScroll=true;
                    return true;
                  }
                }
                return true;
              };
              window.__willieTvMove=move;
            })();
        """.trimIndent()
    }
}
