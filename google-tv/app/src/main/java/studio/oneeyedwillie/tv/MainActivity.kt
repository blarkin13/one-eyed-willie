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
                  grid-template-columns:repeat(4,minmax(0,1fr))!important
                }
                                /* TV mode is cinematic and uses 4 roomy posters across. */
                .workspace{margin-left:0!important;position:relative;z-index:1}
                .workspace>.content,body[data-page="tv"] .workspace>.content,
                body[data-page="home"] .workspace>.content {
                  max-width:none!important;
                  padding-left:clamp(36px,5vw,95px)!important;
                  padding-right:clamp(36px,5vw,95px)!important
                }
                #items{grid-template-columns:repeat(4,minmax(0,1fr))!important;
                  gap:38px 30px!important}
                .shelf-track{grid-auto-columns:clamp(210px,21vw,285px)!important;gap:26px!important}
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
                *{scroll-margin:26px}
                @media(max-width:1100px){
                  #items{grid-template-columns:repeat(3,minmax(0,1fr))!important}
                }
                @media(max-width:720px){
                  #items{grid-template-columns:repeat(2,minmax(0,1fr))!important}
                }
              `;
              document.head.appendChild(style);

              // The server's shell.js owns the cinematic backdrop on Home,
              // Movies, TV and Explore. It resolves actual widescreen backdrop_url
              // from metadata, handles focus and hover, and fades between images.
              // Do not add a second WebView backdrop based on poster images.
              const selector='a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]';
              const visible=node=>{
                if (!node.isConnected || node.closest('[hidden],[inert],[aria-hidden="true"]')) return false;
                const style=getComputedStyle(node);
                if(style.display==='none'||style.visibility==='hidden'||style.pointerEvents==='none')return false;
                const r=node.getBoundingClientRect();
                return r.width>3&&r.height>3;
              };
              const focusables=()=>[...document.querySelectorAll(selector)].filter(visible);
              const move=direction=>{
                const nodes=focusables();
                if(!nodes.length)return false;
                const active=document.activeElement;
                if(!nodes.includes(active)){
                  const first=nodes.find(node=>node.matches('.tile-button,.nav-link[aria-current="page"]'))||nodes[0];
                  first.focus({preventScroll:true});
                  first.scrollIntoView({block:'nearest',inline:'nearest'});
                  return true;
                }
                const from=active.getBoundingClientRect();
                const centerX=from.left+from.width/2,centerY=from.top+from.height/2;
                const horizontal=direction==='left'||direction==='right';
                let winner=null,best=Infinity;
                for(const node of nodes){
                  if(node===active)continue;
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
