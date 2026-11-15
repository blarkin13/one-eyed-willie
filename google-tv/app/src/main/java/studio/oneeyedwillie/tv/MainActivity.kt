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
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            setPadding(64, 48, 64, 48)
        }
        val brand = ImageView(this).apply {
            setImageResource(R.drawable.tv_ship_icon)
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            layoutParams = LinearLayout.LayoutParams(192, 192)
        }
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
        listOf(brand, title, help, input, connect, status).forEach {
            val p = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = 20 }
            root.addView(it, p)
        }
        setContentView(root)
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
                window.WilliePlayer.open = (id) => {
                  if (Number.isInteger(Number(id)) && Number(id) > 0)
                    location.href = 'oewtv://play/' + Number(id);
                };
                window.WilliePlayer.__androidTv = true;
              }
              if (document.getElementById('oew-tv-remote-style')) return;
              const style = document.createElement('style');
              style.id = 'oew-tv-remote-style';
              style.textContent = ':focus-visible{outline:3px solid #fff!important;outline-offset:4px!important;scroll-margin:90px} .tile:focus-within{transform:scale(1.035);z-index:2}';
              document.head.appendChild(style);
              let last = null;
              document.addEventListener('focusin', e => {
                if (e.target !== last) {
                  e.target.scrollIntoView?.({block:'nearest',inline:'nearest',behavior:'smooth'});
                  last=e.target;
                }
              }, true);
              document.addEventListener('keydown', event => {
                if (!['ArrowDown','ArrowUp','ArrowLeft','ArrowRight'].includes(event.key)) return;
                const active = document.activeElement;
                if (active?.matches('input, textarea, select, [contenteditable=true]')) return;
                const candidates = [...document.querySelectorAll('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]')]
                  .filter(node => {
                    const r=node.getBoundingClientRect(), css=getComputedStyle(node);
                    return r.width>0 && r.height>0 && css.visibility!=='hidden' && css.display!=='none';
                  });
                if (!candidates.length) return;
                if (!candidates.includes(active)) { candidates[0].focus(); event.preventDefault(); return }
                const r = active.getBoundingClientRect(), cx=r.left+r.width/2,cy=r.top+r.height/2;
                let winner=null, best=Infinity;
                for (const node of candidates) {
                  if(node===active) continue;
                  const b=node.getBoundingClientRect(), dx=b.left+b.width/2-cx,dy=b.top+b.height/2-cy;
                  const forward=event.key==='ArrowRight'?dx>3:event.key==='ArrowLeft'?dx< -3:event.key==='ArrowDown'?dy>3:dy< -3;
                  if(!forward)continue;
                  const primary=event.key==='ArrowRight'||event.key==='ArrowLeft'?Math.abs(dx):Math.abs(dy);
                  const secondary=event.key==='ArrowRight'||event.key==='ArrowLeft'?Math.abs(dy):Math.abs(dx);
                  const score=primary+secondary*2;
                  if(score<best){best=score;winner=node}
                }
                if(winner){event.preventDefault();winner.focus()}
              },true);
            })();
        """.trimIndent()
    }
}
