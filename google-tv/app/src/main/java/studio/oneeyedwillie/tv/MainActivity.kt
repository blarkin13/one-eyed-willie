package studio.oneeyedwillie.tv

import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.media.MediaPlayer
import android.view.inputmethod.InputMethodManager
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.JsPromptResult
import android.net.Uri
import org.json.JSONObject
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import java.net.URI
import android.util.Log
import android.webkit.JavascriptInterface

/**
 * The same One-Eyed Willie UI served to desktop browsers is the TV UI.
 * It is deliberately NOT a second independently maintained Compose screen set.
 * Native Media3 playback handles codecs that Android WebView cannot reliably play.
 */
class MainActivity : ComponentActivity() {
    private val prefs by lazy { getSharedPreferences("server", MODE_PRIVATE) }
    private var browser: WebView? = null
    private var origin = ""
    private val pendingProgressPrefs by lazy { getSharedPreferences("oew_tv_pending_progress", MODE_PRIVATE) }
    // D-pad focus must not turn a text field into an editing session.
    private var tvTextEditing = false

    private var loadingOverlay: FrameLayout? = null
    private var loadingCaption: TextView? = null
    private var loadingErrorPanel: LinearLayout? = null
    private var loadingActions: LinearLayout? = null
    private var loadingRetry: Button? = null
    private val startupSounds = mutableListOf<MediaPlayer>()
    private var loadingFailed = false
    private var pageLoadSerial = 0
    private var initialPageLoaded = false
    private var playedStartupSound = false

    private fun dp(value: Int) = (value * resources.displayMetrics.density + .5f).toInt()

    // The actual 1920x1080 user-supplied artwork covers the TV at its
    // natural aspect ratio. No enlarged launcher icon, drawn waves or rocking.
    private fun createLoadingOverlay(): FrameLayout {
        val overlay = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
            isClickable = true
            isFocusable = true
        }
        val art = ImageView(this).apply {
            setImageResource(R.drawable.tv_loading_screen)
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "One-Eyed Willie loading artwork"
        }
        overlay.addView(art, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        loadingCaption = TextView(this).apply {
            visibility = View.GONE
            textSize = 19f
            gravity = Gravity.CENTER
            setTextColor(0xFFF0EBE5.toInt())
        }
        val errorControls = LinearLayout(this).apply {
            visibility = View.GONE
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(18), dp(14), dp(18), dp(14))
            setBackgroundColor(0xE6000000.toInt())
        }
        errorControls.addView(loadingCaption, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        loadingRetry = Button(this).apply {
            text = "Retry"
            setTextColor(Color.BLACK)
            backgroundTintList = ColorStateList.valueOf(0xFFF0EBE5.toInt())
            setOnClickListener { browser?.reload() }
        }
        val settings = Button(this).apply {
            text = "Server settings"
            setTextColor(Color.WHITE)
            backgroundTintList = ColorStateList.valueOf(0xFF263348.toInt())
            setOnClickListener { showSetup() }
        }
        loadingActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            visibility = View.GONE
            addView(loadingRetry)
            addView(settings, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { leftMargin = dp(12) })
        }
        errorControls.addView(loadingActions, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = dp(12) })
        loadingErrorPanel = errorControls
        overlay.addView(errorControls, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER
        ))
        return overlay
    }

    // Play the two uploaded real-world recordings once on cold startup.
    // The clips are quiet and layered, never restarted during navigation.
    private fun playStartupSoundOnce() {
        if (playedStartupSound) return
        playedStartupSound = true
        intArrayOf(R.raw.loading_boat_creak, R.raw.loading_wood_creak)
            .forEachIndexed { index, resource ->
                try {
                    val sound = MediaPlayer.create(this, resource) ?: return@forEachIndexed
                    startupSounds.add(sound)
                    val volume = if (index == 0) 0.20f else 0.14f
                    sound.setVolume(volume, volume)
                    sound.setOnCompletionListener { completed ->
                        startupSounds.remove(completed)
                        completed.release()
                    }
                    sound.start()
                } catch (_: Exception) {
                    // Audio is optional. Playback/connection must never fail
                    // because a sound effect cannot be decoded.
                }
            }
    }

    private fun showLoading() {
        // The ship splash belongs to cold startup and initial connection,
        // not every internal document navigation.
        if (initialPageLoaded) return
        loadingFailed = false
        loadingCaption?.visibility = View.GONE
        loadingActions?.visibility = View.GONE
        loadingErrorPanel?.visibility = View.GONE
        loadingOverlay?.apply {
            animate().cancel()
            alpha = 1f
            visibility = View.VISIBLE
        }
        playStartupSoundOnce()
    }

    private fun showLoadingFailure(message: String) {
        if (initialPageLoaded) {
            // Keep ordinary page navigation visible rather than restarting the
            // ship splash. Report failures without hiding the previous page.
            android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show()
            return
        }
        loadingFailed = true
        loadingCaption?.text = message
        loadingCaption?.visibility = View.VISIBLE
        loadingActions?.visibility = View.VISIBLE
        loadingErrorPanel?.visibility = View.VISIBLE
        loadingOverlay?.apply {
            animate().cancel()
            alpha = 1f
            visibility = View.VISIBLE
        }
        loadingRetry?.requestFocus()
    }

    private fun finishLoading(web: WebView, serial: Int) {
        if (browser !== web || loadingFailed || serial != pageLoadSerial) return
        if (initialPageLoaded) return
        initialPageLoaded = true
        loadingOverlay?.animate()?.alpha(0f)?.setDuration(180L)?.withEndAction {
            if (browser === web && serial == pageLoadSerial && !loadingFailed) {
                loadingOverlay?.visibility = View.GONE
                web.requestFocus()
            }
        }?.start()
    }

    private fun finishTvTextEditing(web: WebView) {
        tvTextEditing = false
        web.evaluateJavascript("window.__willieTvEndTextEdit?.()", null)
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
            .hideSoftInputFromWindow(web.windowToken, 0)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val web = browser
                if (web == null) { showSetup(); return }
                if (tvTextEditing) {
                    finishTvTextEditing(web)
                    return
                }
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
        initialPageLoaded = false
        tvTextEditing = false
        loadingOverlay?.animate()?.cancel()
        loadingOverlay = null
        loadingErrorPanel = null
        loadingCaption = null
        loadingActions = null
        loadingRetry = null
        browser?.keepScreenOn = false
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
            // A highlighted server-address field should not summon the IME.
            showSoftInputOnFocus = false
            setOnFocusChangeListener { _, focused ->
                if (!focused) showSoftInputOnFocus = false
            }
            setOnClickListener {
                showSoftInputOnFocus = true
                (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
                    .showSoftInput(this, InputMethodManager.SHOW_IMPLICIT)
            }
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
        initialPageLoaded = false
        tvTextEditing = false
        origin = server.trimEnd('/')
        val view = WebView(this)
        browser = view
        // Only acknowledges the exact persisted checkpoint after same-origin
        // JavaScript fetch received HTTP 2xx. It cannot modify other app data.
        view.addJavascriptInterface(object {
            @JavascriptInterface
            fun confirmed(key: String, serialized: String) {
                runOnUiThread {
                    if (browser !== view || !sameOrigin(view.url.orEmpty())) return@runOnUiThread
                    if (!key.startsWith("progress:$origin:")) return@runOnUiThread
                    if (pendingProgressPrefs.getString(key, null) != serialized) return@runOnUiThread
                    pendingProgressPrefs.edit().remove(key).apply()
                    view.evaluateJavascript(
                        "document.dispatchEvent(new Event('willie:watch-updated'))", null
                    )
                }
            }
        }, "OneEyedWillieProgress")
        view.setBackgroundColor(Color.BLACK)
        view.isFocusable = true
        view.isFocusableInTouchMode = true
        view.settings.apply {
            // The server sends TV-only first-paint CSS for this WebView.
            // Without it, the desktop sidebar flashes before onPageFinished
            // injects the remote-navigation styling.
            if (!userAgentString.contains("OneEyedWillieTV/1"))
                userAgentString = userAgentString + " OneEyedWillieTV/1"
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
                // Never leak internal TV IPC messages into JavaScript prompt
                // dialogs. Ignore untrusted/stale WebView frames instead.
                if ((message.startsWith("oewtv:") || message.startsWith("oewtv.")) &&
                    (!sameOrigin(url) || browser !== web)) {
                    result.cancel()
                    return true
                }
                if (sameOrigin(url) && browser === web &&
                    (message == "oewtv:awake:1" || message == "oewtv:awake:0")) {
                    // Restrict the playback-only stay-awake signal to our
                    // trusted server origin. Do not disable system-wide sleep.
                    val awake = message == "oewtv:awake:1"
                    result.confirm("ACK")
                    web.post { if (browser === web && !isFinishing) web.keepScreenOn = awake }
                    return true
                }
                if (sameOrigin(url) && browser === web &&
                    (message == "oewtv:edit:begin" || message == "oewtv:edit:end")) {
                    val begin = message == "oewtv:edit:begin"
                    tvTextEditing = begin
                    result.confirm("ACK")
                    if (begin) {
                        // Let WebView recreate its input connection after the
                        // selected field has been made editable and refocused.
                        web.postDelayed({
                            if (browser === web && tvTextEditing && !isFinishing) {
                                web.requestFocus()
                                (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
                                    .showSoftInput(web, InputMethodManager.SHOW_IMPLICIT)
                            }
                        }, 80L)
                    }
                    return true
                }
                if (!message.startsWith("oewtv:play:")) {
                    // Unknown internal protocol messages are not UI prompts.
                    if (message.startsWith("oewtv:") || message.startsWith("oewtv.")) {
                        result.cancel()
                        return true
                    }
                    return super.onJsPrompt(web, url, message, defaultValue, result)
                }
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
            override fun onPageStarted(web: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                tvTextEditing = false
                web.keepScreenOn = false
                pageLoadSerial++
                if (browser === web && sameOrigin(url.orEmpty()) && !initialPageLoaded)
                    showLoading()
                super.onPageStarted(web, url, favicon)
            }
            override fun onReceivedError(
                web: WebView, request: WebResourceRequest, error: WebResourceError
            ) {
                if (browser === web && request.isForMainFrame)
                    showLoadingFailure("Unable to reach your server")
                super.onReceivedError(web, request, error)
            }
            override fun onReceivedHttpError(
                web: WebView, request: WebResourceRequest, response: WebResourceResponse
            ) {
                if (browser === web && request.isForMainFrame && response.statusCode >= 400)
                    showLoadingFailure("Server error ${response.statusCode}")
                super.onReceivedHttpError(web, request, response)
            }
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
                if (browser === web && sameOrigin(url.orEmpty())) {
                    val completedSerial = pageLoadSerial
                    installRemoteNavigation(web)
                    // A page with autofocus must not leave the keyboard open
                    // before its inputs receive the TV read-only focus guard.
                    if (!tvTextEditing)
                        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
                            .hideSoftInputFromWindow(web.windowToken, 0)
                    web.postDelayed({ finishLoading(web, completedSerial) }, 110L)
                    // Returning from the native player can precede the page's
                    // JavaScript readiness. Retry pending playback checkpoints
                    // after every successful same-origin page load as well.
                    web.postDelayed({
                        if (browser === web && sameOrigin(web.url.orEmpty()))
                            syncPendingPlaybackProgress()
                    }, 450L)
                }
            }
        }
        val screen = FrameLayout(this)
        screen.addView(view, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        loadingOverlay = createLoadingOverlay()
        screen.addView(loadingOverlay, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        setContentView(screen)
        showLoading()
        view.loadUrl("$origin/")
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
        if (loadingOverlay?.visibility == View.VISIBLE && direction != null) {
            // An error screen uses native focusable Retry / Settings buttons.
            return if (loadingFailed) super.dispatchKeyEvent(event) else true
        }
        if (event.keyCode == KeyEvent.KEYCODE_BACK && web != null) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
                if (tvTextEditing) {
                    finishTvTextEditing(web)
                    return true
                }
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
            // Cursor/IME arrows belong to the editor after OK, but otherwise
            // navigate normally between fields and the rest of the page.
            if (tvTextEditing) return super.dispatchKeyEvent(event)
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

    /**
     * Native HttpURLConnection writes can fail independently of ExoPlayer's
     * ongoing video stream. The foreground WebView already has a working
     * same-origin connection; use that path to flush any saved checkpoints
     * whenever the viewer returns from PlayerActivity. Never clear a pending
     * checkpoint without a real HTTP 2xx response from the server.
     */
    private fun syncPendingPlaybackProgress() {
        val web = browser ?: return
        if (!sameOrigin(web.url.orEmpty()) || origin.isBlank()) return
        val store = pendingProgressPrefs
        val prefix = "progress:$origin:"
        for ((key, saved) in store.all) {
            if (!key.startsWith(prefix) || saved !is String) continue
            val mediaId = key.removePrefix(prefix).toIntOrNull() ?: continue
            if (mediaId <= 0) continue
            val checkpoint = try { JSONObject(saved) } catch (_: Exception) { continue }
            if (checkpoint.optInt("media_id") != mediaId) continue
            val seconds = checkpoint.optDouble("position_seconds", Double.NaN)
            if (!seconds.isFinite() || seconds < 0.0) continue
            // Escape JSON as a JS string, not as JavaScript source code.
            val payload = JSONObject.quote(saved)
            val keyArg = JSONObject.quote(key)
            val script = """
                (async () => {
                  try {
                    const response = await fetch('/api/playback/progress', {
                      method: 'POST',
                      headers: {'Content-Type': 'application/json'},
                      body: $payload,
                      cache: 'no-store'
                    });
                    if (response.ok) {
                      window.OneEyedWillieProgress?.confirmed($keyArg, $payload);
                      // The server must finish writing progress before the
                      // home shelf and detail pages read Continue Watching.
                      document.dispatchEvent(new Event('willie:watch-updated'));
                    }
                    return response.ok;
                  } catch (error) {
                    console.warn('TV playback progress retry failed', error);
                    return false;
                  }
                })()
            """.trimIndent()
            // Android evaluateJavascript does not await a returned Promise.
            // The JS bridge above acknowledges only after fetch reports HTTP
            // success; failed requests remain on disk for the next retry.
            web.evaluateJavascript(script, null)
        }
    }

    override fun onResume() {
        super.onResume()
        // Read the player state via the JavaScript evaluation callback.
        // Never use JS prompt() here: after a second launch/resume it can
        // surface oewtv:awake:0 as a visible browser dialog.
        val activeWeb = browser
        if (activeWeb != null && sameOrigin(activeWeb.url.orEmpty())) {
            activeWeb.evaluateJavascript(
                """(() => {
                  const v = document.querySelector('.willie-player video');
                  return Boolean(v && !v.paused && !v.ended);
                })()""".trimIndent()
            ) { state ->
                if (browser === activeWeb && !isFinishing &&
                    sameOrigin(activeWeb.url.orEmpty()))
                    activeWeb.keepScreenOn = state == "true"
            }
        }
        // Native Media3 playback runs in another Activity. Refresh the
        // underlying season page's watched flags and resume positions when
        // returning to its WebView, without navigating away from the show.
        // Refresh immediately for checkpoints already committed by the
        // native player. Pending checkpoints trigger another refresh only
        // after their HTTP POST succeeds (see syncPendingPlaybackProgress).
        browser?.evaluateJavascript(
            "document.dispatchEvent(new Event('willie:watch-updated'))", null
        )
        syncPendingPlaybackProgress()
        // A checkpoint can be written as PlayerActivity finishes *after*
        // MainActivity.onResume. Retry it on the main WebView rather than
        // assuming the single onResume attempt caught the last position.
        browser?.postDelayed({
            if (!isFinishing && browser != null) syncPendingPlaybackProgress()
        }, 1300L)
    }

    override fun onPause() {
        // Never hold the display awake when browsing or watching is backgrounded.
        browser?.keepScreenOn = false
        // Google TV's keyboard may be a full-screen IME activity. Opening it
        // pauses this Activity; ending editing here would instantly close it.
        // Keep text editing alive until Back, another field, or page change.
        super.onPause()
    }

    override fun onDestroy() {
        startupSounds.toList().forEach { it.release() }
        startupSounds.clear()
        loadingOverlay?.animate()?.cancel()
        tvTextEditing = false
        browser?.keepScreenOn = false
        browser?.destroy()
        browser = null
        super.onDestroy()
    }

    companion object {
        private val TV_REMOTE_SCRIPT = """
            (() => {
              // Google TV remote navigation may focus a search box while the
              // viewer is just moving through the interface. A focused text
              // input remains read-only until OK/Select or a real click.
              // The fields remain focusable and keep their existing values.
              if(!window.__oewTvInputGateInstalled){
                window.__oewTvInputGateInstalled=true;
                const protectedFields=new WeakSet();
                let editingField=null;
                let refocusing=false;
                const isTextField=node=>node instanceof HTMLTextAreaElement ||
                  (node instanceof HTMLInputElement &&
                    ['text','search','email','password','tel','url','number'].includes(node.type));
                const protect=node=>{
                  if(!isTextField(node)||node.disabled||node===editingField||node.readOnly)return;
                  node.readOnly=true;
                  protectedFields.add(node);
                };
                const scan=root=>{
                  if(root.nodeType!==1&&root.nodeType!==9&&root.nodeType!==11)return;
                  protect(root);
                  root.querySelectorAll?.('input,textarea').forEach(protect);
                };
                scan(document);
                new MutationObserver(records=>{
                  for(const record of records)
                    for(const node of record.addedNodes)scan(node);
                }).observe(document.documentElement,{childList:true,subtree:true});
                const notify=mode=>{
                  try{prompt('oewtv:edit:'+mode,'')}catch(_){}
                };
                const endEditing=()=>{
                  if(!editingField)return false;
                  const field=editingField;
                  editingField=null;
                  if(field.isConnected)field.readOnly=true;
                  notify('end');
                  return true;
                };
                window.__willieTvEndTextEdit=endEditing;
                const beginEditing=field=>{
                  if(!protectedFields.has(field)||field.disabled)return false;
                  if(editingField===field)return true;
                  if(editingField)endEditing();
                  editingField=field;
                  field.readOnly=false;
                  // WebView may have focused the field in read-only mode.
                  // Recreate its input connection only after explicit Select.
                  refocusing=true;
                  field.blur();
                  field.focus({preventScroll:true});
                  refocusing=false;
                  notify('begin');
                  return true;
                };
                document.addEventListener('focusin',event=>{
                  protect(event.target);
                  // The system keyboard can temporarily blur WebView. Close
                  // editing only when the user focuses a different control.
                  if(editingField && event.target!==editingField &&
                     !refocusing && event.target instanceof Element)
                    endEditing();
                },true);
                // Do NOT end editing on focusout: opening Android's IME
                // moves WebView focus and used to close it immediately.
                document.addEventListener('pointerdown',event=>{
                  if(editingField && event.target!==editingField &&
                     !(event.target instanceof Element && event.target.closest('.keyboard-container')))
                    endEditing();
                },true);
                document.addEventListener('keydown',event=>{
                  if(!['Enter',' '].includes(event.key)||!isTextField(event.target))return;
                  if(!protectedFields.has(event.target)||editingField===event.target)return;
                  event.preventDefault();
                  event.stopImmediatePropagation();
                  beginEditing(event.target);
                },true);
                document.addEventListener('click',event=>{
                  if(isTextField(event.target)&&protectedFields.has(event.target))
                    beginEditing(event.target);
                },true);
              }
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
              // Fallback HTML5 playback must prevent Android TV inactivity
              // sleep as well. A capturing listener handles non-bubbling media
              // events without needing to modify the server's player script.
              if(!window.__oewTvVideoAwakeHook){
                window.__oewTvVideoAwakeHook=true;
                const notifyAwake=(enabled)=>{
                  try{prompt('oewtv:awake:'+(enabled?'1':'0'),'')}catch(_){}
                };
                document.addEventListener('playing',event=>{
                  const video=event.target;
                  if(video?.matches?.('.willie-player video'))notifyAwake(true);
                },true);
                for(const eventName of ['pause','ended','emptied']){
                  document.addEventListener(eventName,event=>{
                    const video=event.target;
                    if(video?.matches?.('.willie-player video'))notifyAwake(false);
                  },true);
                }
              }
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
                  outline:0!important;box-shadow:none!important;
                  border-color:transparent!important;
                  transform:scale(1.07)!important;filter:brightness(1.16)!important
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
                  outline:0!important;box-shadow:none!important;border-color:transparent!important;
                  transform:scale(1.07)!important;filter:brightness(1.16)!important
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
                  outline:0!important;box-shadow:none!important;border-color:transparent!important;
                  transform:scale(1.07)!important;filter:brightness(1.16)!important
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
                  position:absolute!important;top:4px!important;right:4px!important;
                  z-index:5!important;display:grid!important;place-items:center!important;
                  width:15px!important;height:15px!important;
                  padding:0!important;border-radius:50%!important;
                  background:#091929e8!important;border:1px solid #7faec4!important;
                  color:#d7edf8!important;pointer-events:none!important
                }
                body[data-page="home"] .watched-badge svg{
                  display:block!important;width:10px!important;height:10px!important
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
                  outline:0!important;box-shadow:none!important;
                  background:transparent!important;
                  transform:scale(1.16)!important;filter:brightness(1.25)!important
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
                  outline:0!important;box-shadow:none!important;
                  transform:scale(1.07)!important;filter:brightness(1.16)!important
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
                /* Purple is an icon-only remote focus cue, never a box or fill.
                   Service-brand icons retain their original Radarr/Sonarr art. */
                body[data-page] :is(.media-icon-action,.icon-only-control,
                  .watch-icon-control,.tv-trailer-launch):is(:focus,:focus-visible){
                  color:#8B5CF6!important;background:transparent!important;
                  outline:0!important;box-shadow:none!important
                }
                body[data-page] :is(.media-icon-action,.icon-only-control,
                  .watch-icon-control,.tv-trailer-launch):is(:focus,:focus-visible) svg,
                body[data-page] :is(.willie-controls,.willie-toolbar)
                  button:is(:focus,:focus-visible){
                  color:#8B5CF6!important
                }
                /* The sidebar has no selected background, outline, side marker,
                   border or shadow. Only the focused/current icon changes color. */
                body[data-page] .sidebar .nav-link,
                body[data-page] .sidebar .nav-link:is(:hover,:focus,:focus-visible),
                body[data-page] .sidebar .nav-link[aria-current="page"]{
                  background:transparent!important;border:0!important;
                  outline:0!important;box-shadow:none!important
                }
                body[data-page] .sidebar .nav-link[aria-current="page"]::before{
                  display:none!important;content:none!important
                }
                body[data-page] .sidebar .nav-link:not([data-service-nav="radarr"]):not(
                  [data-service-nav="sonarr"]):is(:focus,:focus-visible) .nav-icon,
                body[data-page] .sidebar .nav-link[aria-current="page"]:not(
                  [data-service-nav="radarr"]):not([data-service-nav="sonarr"]) .nav-icon{
                  color:#8B5CF6!important
                }
                /* Strong icon-only purple focus on all detail pages, including
                   dynamic movie/TV/season actions and navigation popovers. */
                body[data-page] :is(.movie-detail-actions,.tv-show-hero,
                  .season-actions-row,.episode-actions,.episode-detail-actions,
                  .season-hero-actions,.season-overflow-dialog,.tv-match-head,
                  .movie-match-head) :is(.media-icon-action,.watch-icon-control,
                  .icon-only-control,.season-more-button,.season-rail-arrow)
                  :is(:focus,:focus-visible),
                body[data-page] :is(.media-icon-action,.watch-icon-control,
                  .icon-only-control,.season-more-button,.season-rail-arrow,
                  .tv-trailer-launch,.catalog-tool-icon,.explore-icon-link)
                  :is(:focus,:focus-visible) {
                  color:#8B5CF6!important;
                  background:transparent!important;
                  border-color:transparent!important;
                  outline:0!important;box-shadow:none!important
                }
                body[data-page] :is(.movie-detail-actions,.tv-show-hero,
                  .season-actions-row,.episode-actions,.episode-detail-actions,
                  .season-hero-actions,.tv-match-head,.movie-match-head)
                  :is(.media-icon-action,.watch-icon-control,.icon-only-control,
                  .season-more-button,.tv-trailer-launch):is(:focus,:focus-visible)
                  :is(svg,i,.fa,.nav-icon),
                body[data-page] :is(.media-icon-action,.watch-icon-control,
                  .icon-only-control,.season-more-button,.tv-trailer-launch,
                  .catalog-tool-icon,.explore-icon-link):is(:focus,:focus-visible)
                  :is(svg,i,.fa) { color:#8B5CF6!important }
                body[data-page] [data-service-nav="radarr"] :is(svg,img,i),
                body[data-page] [data-service-nav="sonarr"] :is(svg,img,i) {
                  filter:none!important
                }
                /* The current sidebar destination stays purple even when
                   remote focus is on the page instead of the sidebar.
                   Color the actual glyph (including async library SVG icons)
                   and never recolor branded Radarr/Sonarr/SABnzbd logos. */
                body[data-page] .sidebar .nav-link[aria-current="page"]
                  :is(.nav-icon,.nav-icon svg,.nav-icon i,.nav-icon .fa-fallback,
                      .nav-icon .library-symbol,.library-custom-icon):not(img),
                body[data-page] .sidebar .nav-link[aria-current="page"]
                  :is(.nav-icon svg path,.nav-icon svg circle,.nav-icon svg rect,
                      .nav-icon svg polygon,.nav-icon svg polyline,.nav-icon svg line){
                  color:#8B5CF6!important
                }
                body[data-page] .sidebar .nav-link[aria-current="page"]
                  :is(.nav-icon,.nav-icon svg,.nav-icon i,.nav-icon .fa-fallback,
                      .nav-icon .library-symbol,.library-custom-icon):not(img){
                  color:#8B5CF6!important
                }
                body[data-page] .sidebar
                  .nav-link:is([data-service-nav="radarr"],[data-service-nav="sonarr"],
                    [data-service-nav="sabnzbd"]) .nav-icon,
                body[data-page] .sidebar
                  .nav-link:is([data-service-nav="radarr"],[data-service-nav="sonarr"],
                    [data-service-nav="sabnzbd"]) .nav-icon *{
                  color:inherit!important
                }
                /* Avoid competing browser snap while the D-pad animation runs. */
                html,body{scroll-behavior:auto!important;scroll-padding:0!important}
                .shelf-track,.discovery-row{scroll-snap-type:none!important}
                /* Focus movement is animated on artwork, icons and controls. */
                body[data-page] :is(.cover,.person-credit-poster,.season-episode-tile,
                  .cast-person img,.cast-blank,.nav-link,.media-icon-action,
                  .icon-only-control,dialog button,dialog a,dialog input,.season-tabs a){
                  transition:transform 190ms ease-out,filter 190ms ease-out,
                    box-shadow 190ms ease-out,background-color 190ms ease-out,
                    border-color 190ms ease-out,color 190ms ease-out!important
                }
                /* Retain the original borderless poster scale animation.
                   No extra blue/white rings or selected-control backgrounds. */
                @media(prefers-reduced-motion:reduce){
                  body[data-page] :is(.cover,.person-credit-poster,.season-episode-tile,
                    .cast-person img,.cast-blank,.nav-link,.media-icon-action,
                    .icon-only-control,dialog button,dialog a,dialog input,.season-tabs a){
                    transition:none!important
                  }
                }
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
              // Closed TV rail uses pointer-events:none. Such links are
              // deliberately omitted by isVisible(), but D-pad Left must
              // still be able to enter and reveal the closed rail. Filter
              // actual hidden navigation destinations, not hit-testing state.
              const allMenu=()=>[...document.querySelectorAll('#app-nav .side-nav .nav-link')]
                .filter(node=>node.isConnected &&
                  !node.closest('[hidden],[inert],[aria-hidden="true"]') &&
                  getComputedStyle(node).display!=='none' &&
                  getComputedStyle(node).visibility!=='hidden');
              const isMenu=node=>Boolean(node?.closest?.('#app-nav'));
              const contentSelector='.tile-button,.explore-card .detail-trigger,.episode-card a[href],.season-card a[href],.person-credit-link,.season-episode-tile';
              const allPosters=()=>[...document.querySelectorAll(contentSelector)].filter(isVisible);
              const firstPoster=()=>allPosters()[0]||null;
              // A new remote press interrupts the previous animation cleanly.
              const scrollAnimations=new WeakMap();
              const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
              const glideTo=(element,axis,destination)=>{
                const vertical=axis==='top',key=vertical?'scrollTop':'scrollLeft';
                const limit=vertical
                  ?Math.max(0,element.scrollHeight-element.clientHeight)
                  :Math.max(0,element.scrollWidth-element.clientWidth);
                const to=Math.max(0,Math.min(limit,destination));
                const previous=scrollAnimations.get(element);
                if(previous)cancelAnimationFrame(previous);
                scrollAnimations.delete(element);
                const start=element[key],delta=to-start;
                if(Math.abs(delta)<1)return;
                if(reducedMotion()){element[key]=to;return}
                const begun=performance.now(),duration=210;
                const tick=now=>{
                  const t=Math.min(1,(now-begun)/duration);
                  element[key]=start+delta*(1-Math.pow(1-t,3));
                  if(t<1)scrollAnimations.set(element,requestAnimationFrame(tick));
                  else scrollAnimations.delete(element);
                };
                scrollAnimations.set(element,requestAnimationFrame(tick));
              };
              const focusNode=node=>{
                if(!node)return false;
                // The sidebar opens only when the remote deliberately moves
                // focus into it; normal page-load autofocus cannot reveal it.
                document.body.classList.toggle('oew-tv-rail-open',isMenu(node));
                node.focus({preventScroll:true});
                let r=rect(node);
                const padding=44;
                // Dialogs have their own scrolling content. Keep the focused
                // Match result visible inside that content, without scrolling
                // the page behind the modal.
                const modal=node.closest('dialog[open],.season-more-popover');
                if(modal){
                  let scroller=node.parentElement;
                  while(scroller && scroller!==modal){
                    const style=getComputedStyle(scroller);
                    if(/auto|scroll/.test(style.overflowY) &&
                       scroller.scrollHeight>scroller.clientHeight+1)break;
                    scroller=scroller.parentElement;
                  }
                  if(!scroller)scroller=modal;
                  const bounds=rect(scroller);
                  const edge=12;
                  if(r.top<bounds.top+edge)
                    glideTo(scroller,'top',scroller.scrollTop-(bounds.top+edge-r.top));
                  else if(r.bottom>bounds.bottom-edge)
                    glideTo(scroller,'top',scroller.scrollTop+(r.bottom-bounds.bottom+edge));
                  return true;
                }
                // Only scroll enough to reveal a genuinely clipped selection.
                // scrollIntoView() caused entire shelves to snap/jump by a row.
                if(isMenu(node)){
                  const scroller=node.closest('.side-nav');
                  if(scroller){
                    const outer=rect(scroller);
                    if(r.top<outer.top+8)glideTo(scroller,'top',scroller.scrollTop-(outer.top+8-r.top));
                    else if(r.bottom>outer.bottom-8)glideTo(scroller,'top',scroller.scrollTop+(r.bottom-outer.bottom+8));
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
                      glideTo(shelf,'left',shelf.scrollLeft+deltaX);
                    }
                    r=rect(node);
                    // Home poster Left/Right is horizontal navigation only.
                    // The dedicated Up/Down shelf handler animates vertical
                    // movement; this instant scroll used to fight it and
                    // make the first focus on a newly loaded shelf jump.
                    if(document.body.dataset.page==='home' &&
                      shelf.matches('.shelf-track'))return true;
                  }
                  const delta=r.top<padding?r.top-padding:
                    r.bottom>innerHeight-padding?r.bottom-(innerHeight-padding):0;
                  if(Math.abs(delta)>1)glideTo(document.scrollingElement||document.documentElement,'top',
                      (document.scrollingElement||document.documentElement).scrollTop+delta);
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
                if(Math.abs(target-before)>1)glideTo(root,'top',target);
                return Math.abs(target-before)>1;
              };
              // Detail pages use vertical *sections*, not a search for the
              // nearest item under the currently focused column. Libraries
              // and poster grids retain spatial navigation.
              // Comma-separated selectors express priority, not DOM order.
              // Season 1 must win over Specials; the selected episode must win
              // over Episode 1 when moving back into a horizontal episode rail.
              const firstPreferred=(selectors)=>{
                for(const raw of selectors.split(',')){
                  const choice=[...document.querySelectorAll(raw.trim())].find(isVisible);
                  if(choice)return choice;
                }
                return null;
              };
              const primaryDetailAction=()=>{
                const path=location.pathname;
                if(path==='/tv/show')
                  return firstPreferred('#series-play-button,.series-controls button:not(:disabled)');
                if(path==='/tv/season')
                  return firstPreferred('.season-episode-tile.is-selected,.season-episode-tile');
                if(path==='/movie')
                  return document.querySelector('#play-movie');
                if(path==='/credit')
                  return document.querySelector('.credit-actions button:not(:disabled)');
                if(path==='/person')
                  return document.querySelector('.person-credits .person-credit-link');
                return null;
              };
              // On wrapped season/filmography grids, Down/Up takes the
              // leftmost card of the next/previous row. No season becomes
              // inaccessible simply because its row is below the first row.
              const firstOfAdjacentGridRow=(active,direction,rootSelector,itemSelector)=>{
                const root=active?.closest?.(rootSelector);
                if(!root||!['up','down'].includes(direction))return null;
                const entries=[...root.querySelectorAll(itemSelector)].filter(isVisible);
                const top=rect(active).top;
                const next=entries.filter(node=>{
                  const difference=rect(node).top-top;
                  return direction==='down'?difference>15:difference< -15;
                });
                if(!next.length)return null;
                const rowTop=direction==='down'
                  ?Math.min(...next.map(node=>rect(node).top))
                  :Math.max(...next.map(node=>rect(node).top));
                const row=next.filter(node=>Math.abs(rect(node).top-rowTop)<15)
                  .sort((a,b)=>rect(a).left-rect(b).left);
                return row[0]||null;
              };
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
                  const item=firstPreferred(lanes[i].first);
                  if(item){readingScroll=false;return focusNode(item)}
                }
                if(scrollRead(direction))readingScroll=true;
                return true;
              };
              // Movie and TV libraries keep spatial poster navigation.
              // Animate ONLY cross-row scrolling; the old focusNode() used
              // instant scrollBy here, causing an abrupt jump on every row.
              let libraryScrollFrame=0;
              const scrollLibraryRowTo=(node)=>{
                if(libraryScrollFrame){
                  cancelAnimationFrame(libraryScrollFrame);
                  libraryScrollFrame=0;
                }
                const root=document.scrollingElement||document.documentElement;
                const r=rect(node);
                const upper=Math.max(36,innerHeight*.13);
                const lower=innerHeight-Math.max(44,innerHeight*.1);
                if(r.top>=upper&&r.bottom<=lower)return;
                const max=Math.max(0,root.scrollHeight-root.clientHeight);
                const from=root.scrollTop;
                const to=Math.max(0,Math.min(max,from+r.top-upper));
                if(Math.abs(to-from)<2)return;
                if(reducedMotion()){
                  root.scrollTop=to;return;
                }
                const started=performance.now(),duration=285;
                const tick=now=>{
                  const amount=Math.min(1,(now-started)/duration);
                  const ease=1-Math.pow(1-amount,3);
                  root.scrollTop=from+(to-from)*ease;
                  if(amount<1)libraryScrollFrame=requestAnimationFrame(tick);
                  else libraryScrollFrame=0;
                };
                libraryScrollFrame=requestAnimationFrame(tick);
              };
              const moveLibraryGridRow=(active,direction)=>{
                if(!['up','down'].includes(direction)||
                   !['/movies','/tv'].includes(location.pathname)||
                   !active?.matches?.('#items .tile-button'))return false;
                const cards=[...document.querySelectorAll('#items .tile-button')].filter(isVisible);
                const target=findAdjacent(active,direction,cards);
                if(!target)return false;
                readingScroll=false;
                target.focus({preventScroll:true});
                scrollLibraryRowTo(target);
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
                if(moveLibraryGridRow(active,direction))return true;
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
                    const preferred=primaryDetailAction();
                    const target=(preferred&&isVisible(preferred)?preferred:null)||
                      findAdjacent(active,'right',posters)||posters[0]||
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
                if(direction==='up'||direction==='down'){
                  const rowTarget=firstOfAdjacentGridRow(
                    active,direction,'.season-grid','.tile-button')||
                    firstOfAdjacentGridRow(
                      active,direction,'.person-credits','.person-credit-link');
                  if(rowTarget){readingScroll=false;return focusNode(rowTarget)}
                }
                // Home is cinematic row-by-row navigation, not spatial
                // navigation between whichever posters happen to line up.
                // Scroll each *whole shelf* (details + posters) into view;
                // the previous shelf and its details leave the viewport.
                if(document.body.dataset.page==='home' &&
                  (direction==='up'||direction==='down')){
                  const shelf=active?.closest?.('.shelf');
                  if(shelf && active.closest('.shelf-track,.section-heading')){
                    const rows=[...document.querySelectorAll('.content > .shelf')]
                      .filter(row=>[...row.querySelectorAll('.shelf-track .tile-button')]
                        .some(isVisible));
                    const index=rows.indexOf(shelf);
                    const next=index+(direction==='down'?1:-1);
                    if(index>=0&&next>=0&&next<rows.length){
                      const first=[...rows[next].querySelectorAll('.shelf-track .tile-button')]
                        .find(isVisible);
                      if(first){
                        readingScroll=false;
                        first.focus({preventScroll:true});
                        const row=rows[next];
                        const root=document.scrollingElement||document.documentElement;
                        const top=Math.max(0,root.scrollTop+
                          row.getBoundingClientRect().top-10);
                        glideTo(root,'top',top);
                        return true;
                      }
                    }
                    return true;
                  }
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
                if(!nodes.includes(active)){
                  const preferred=primaryDetailAction();
                  return focusNode((preferred&&isVisible(preferred)?preferred:null)||
                    posters[0]||nodes.find(n=>!isMenu(n)));
                }
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
                // Give Left a reliable escape into navigation even on a
                // details/search page without poster cards.
                if(direction==='left'){
                  const menu=allMenu();
                  if(menu.length)return focusNode(
                    menu.find(n=>n.getAttribute('aria-current')==='page')||menu[0]);
                }
                if(direction==='up'||direction==='down'){
                  if(scrollRead(direction)){
                    readingScroll=true;
                    return true;
                  }
                }
                return true;
              };
              document.body.classList.remove('oew-tv-rail-open');
              // New documents must not show the rail just because WebView
              // transferred focus from the old page's selected nav link.
              // Begin on content; the rail opens only after remote Left.
              const settleInitialFocus=()=>{
                if(document.querySelector('dialog[open]'))return true;
                const active=document.activeElement;
                if(active && !isMenu(active) && active!==document.body &&
                   active!==document.documentElement)return true;
                const preferred=primaryDetailAction();
                const field=document.querySelector('.content input[type="search"],.content input[type="text"]');
                const destination=(preferred&&isVisible(preferred)?preferred:null)||
                  firstPoster()||
                  [...document.querySelectorAll('.content button,.content a[href]')].find(isVisible)||
                  (field&&isVisible(field)?field:null);
                if(!destination)return false;
                destination.focus({preventScroll:true});
                return true;
              };
              if(!settleInitialFocus()){
                let attempts=0;
                const focusTimer=setInterval(()=>{
                  if(settleInitialFocus()||++attempts>=12)clearInterval(focusTimer);
                },100);
              }
              window.__willieTvMove=move;
            })();
        """.trimIndent()
    }
}
