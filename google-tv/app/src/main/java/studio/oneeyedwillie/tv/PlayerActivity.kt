package studio.oneeyedwillie.tv

import android.media.MediaCodecList
import android.media.MediaFormat
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.ColorDrawable
import android.app.AlertDialog
import android.view.KeyEvent
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.SeekBar
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import androidx.media3.ui.PlayerView
import androidx.media3.ui.CaptionStyleCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.concurrent.Executors
import android.util.Log

/**
 * Native TV playback follows the server player's playback negotiation:
 * /api/watch/{id}/status selects direct or HLS, with HLS fallback on decoder
 * or source errors. The raw playback stream alone cannot decode every file.
 */
class PlayerActivity : ComponentActivity() {
    private companion object {
        const val SEEK_STEP_SECONDS = 10.0
        /** Minimum spacing of repeats while Left/Right is held. */
        const val SEEK_REPEAT_MS = 190L
        /** Pause after the last press before the seek is applied. */
        const val SEEK_DEBOUNCE_MS = 220L
    }
    private var player: ExoPlayer? = null
    private var mediaId = -1
    private var server = ""
    @Volatile private var session: String? = null
    private var hlsMode = false
    private var hlsOffset = 0.0
    private var durationSeconds = 0.0
    private var completed = false
    private var replayingWatchedEpisode = false
    private var shuttingDown = false
    private var visibleForPlayback = false
    private var fallbackStarted = false
    // Playback quality (see Quality). "auto" plays the original when this TV can
    // decode it; the other choices always transcode at that size.
    @Volatile private var quality = Quality.AUTO
    @Volatile private var directCapable = false
    @Volatile private var directUrl = ""
    // Automatic recovery from transient errors; reset after steady playback.
    private var recoveryAttempts = 0
    private var lastRecoveryAt = 0L
    private lateinit var message: TextView
    private lateinit var playerView: PlayerView
    private lateinit var chrome: LinearLayout
    private lateinit var playButton: ImageButton
    private lateinit var thumbnailPreview: PlayerScrubPreview
    private var scrubbing = false
    private var scrubPosition = 0.0
    private val scrubCommit = Runnable {
        if (!scrubbing) seekTo(scrubPosition)
    }
    private lateinit var timeline: SeekBar
    private lateinit var elapsed: TextView
    private lateinit var totalTime: TextView
    private lateinit var titleText: TextView
    private var title = "Now Playing"
    private var selectedCaption: String? = null
    private var captionLanguage = "en"
    private var nextMediaId: Int? = null
    private var nextTitle = ""
    private var seasonShuffle = false
    private var shuffleQueue = JSONArray()
    private var autoPlayNext = false
    // Keep the end-of-playback handoff pending until next-episode/settings
    // requests finish; network timing must not disable autoplay.
    private var endedAwaitingNext = false
    private var nextLookupInFlight = false
    private var advancingToNext = false
    private var selectedColor = 0xFFA61E1E.toInt()
    private val iconControls = mutableListOf<ImageButton>()
    // A Select key-down that toggles playback must consume its paired key-up.
    // Otherwise Android can activate a newly focused Back button and exit.
    private var consumedPlaybackSelect = false
    private var lastRemoteDirection = -1
    private var lastRemoteMoveAt = 0L
    // All remote seeking goes through ONE tracker (see SeekTracker). The
    // SeekBar's own key handling is bypassed for Left/Right, so there is no
    // second, competing position model.
    private val seek = SeekTracker()
    private var seekCommit: Runnable? = null
    private var lastSeekKeyAt = 0L
    // Each HLS start takes a serial number; only the newest start may touch
    // the player. Older ones notice, delete their session and stop.
    private val hlsStarts = LatestWins()
    private val uiRefresh = object : Runnable {
        override fun run() {
            refreshControls()
            handler.postDelayed(this, 500)
        }
    }
    private val hideChrome = Runnable {
        if (player?.isPlaying == true && !scrubbing) {
            chrome.visibility = View.GONE
            if (::thumbnailPreview.isInitialized) thumbnailPreview.hide()
        }
    }
    private val handler = Handler(Looper.getMainLooper())
    // Playback-critical work (open, HLS start/stop, progress saves) runs here in
    // order. It must never queue behind anything slow.
    private val network = Executors.newSingleThreadExecutor()
    // Everything that can wait or hang (selection colour, next episode,
    // subtitle lists and the 45 s OpenSubtitles search) runs here instead, so
    // a slow answer cannot delay the first frame or a seek's HLS restart.
    private val lookups = Executors.newSingleThreadExecutor()
    // Keep an on-device checkpoint until the server confirms it. This also
    // preserves resume when a separate POST connection fails while streaming.
    private val progressStore by lazy {
        getSharedPreferences("oew_tv_pending_progress", MODE_PRIVATE)
    }
    private fun progressKey(): String = "progress:$server:$mediaId"
    private fun pendingProgress(): JSONObject? = try {
        progressStore.getString(progressKey(), null)?.let(::JSONObject)
    } catch (_: Exception) { null }
    private fun rememberProgress(body: String) {
        progressStore.edit().putString(progressKey(), body).apply()
    }
    private fun acknowledgeProgress(body: String) {
        // The next checkpoint may have been queued while this one was sent.
        // Never clear a newer on-device position after an older POST succeeds.
        if (progressStore.getString(progressKey(), null) == body)
            progressStore.edit().remove(progressKey()).apply()
    }

    private val checkpoint = object : Runnable {
        override fun run() {
            saveProgress(false)
            handler.postDelayed(this, 15_000)
        }
    }

    /** Android TV inactivity sleep is not reset by decoding video frames.
     * Keep the display awake only while this visible player is actively
     * intending to play (including short network/decoder buffering).
     * Pausing, finishing, leaving the activity, or errors restore normal sleep.
     */
    private fun updatePlaybackScreenAwake() {
        val active = player
        val shouldStayAwake = visibleForPlayback && !shuttingDown &&
            active != null && active.playWhenReady &&
            (active.playbackState == Player.STATE_READY ||
             active.playbackState == Player.STATE_BUFFERING)
        if (shouldStayAwake)
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NavTrace.init(applicationContext)
        NavTrace.log { "PLAYER_CREATE" }
        mediaId = intent.getIntExtra("media_id", -1)
        server = intent.getStringExtra("server")?.trimEnd('/') ?: ""
        seasonShuffle = intent.hasExtra("shuffle_queue")
        if (seasonShuffle) shuffleQueue = try {
            JSONArray(intent.getStringExtra("shuffle_queue") ?: "[]")
        } catch (_: Exception) { JSONArray() }
        if (mediaId <= 0 || server.isBlank()) { finish(); return }
        // Only a newly opened native player restores a previously dismissed
        // Continue Watching entry; passive progress refreshes never do.
        network.execute {
            try {
                request("/api/home/continue/$mediaId/start", "POST")
            } catch (error: Exception) {
                Log.w("YarrMedia", "Could not restore Continue Watching entry", error)
            }
        }
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY

        title = intent.getStringExtra("title")?.takeIf { it.isNotBlank() } ?: "Now Playing"
        // Letterbox/pillarbox bands are whatever sits behind the video. The stock
        // Material theme's window background is dark grey, so paint every layer black.
        window.setBackgroundDrawable(ColorDrawable(Color.BLACK))
        val surface = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        playerView = PlayerView(this).apply {
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            useController = false
            setBackgroundColor(Color.BLACK)
            setShutterBackgroundColor(Color.BLACK)
        }
        surface.addView(playerView)
        applySubtitleAppearance()
        chrome = createControls()
        surface.addView(chrome, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        thumbnailPreview = PlayerScrubPreview(this, server, mediaId) { currentDuration() }
        surface.addView(thumbnailPreview.view, FrameLayout.LayoutParams(
            dp(280), dp(190), Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
        ).apply { bottomMargin = dp(163) })
        message = TextView(this).apply {
            text = "Preparing video…"
            textSize = 16f
            setTextColor(Color.WHITE)
            setBackgroundColor(0xDD101820.toInt())
            setPadding(24, 15, 24, 15)
            gravity = Gravity.CENTER
        }
        surface.addView(message, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER
        ))
        setContentView(surface)
        // Start on the timeline so Left/Right seek immediately.
        timeline.requestFocus()
        loadPlayerAppearance()
        thumbnailPreview.start()
        // Longer timeouts and more retries than the defaults: a busy Wi-Fi link
        // should cost a pause, not a failed playback.
        val http = DefaultHttpDataSource.Factory()
            .setConnectTimeoutMs(10_000).setReadTimeoutMs(20_000).setAllowCrossProtocolRedirects(true)
        val sources = DefaultMediaSourceFactory(http)
            .setLoadErrorHandlingPolicy(DefaultLoadErrorHandlingPolicy(6))
        player = ExoPlayer.Builder(this).setMediaSourceFactory(sources).build().also { exo ->
            playerView.player = exo
            exo.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    updatePlaybackScreenAwake()
                    if (state == Player.STATE_READY) {
                        message.visibility = View.GONE
                        // Healthy again: forget earlier hiccups once it has held for a while.
                        if (android.os.SystemClock.uptimeMillis() - lastRecoveryAt > 30_000L)
                            recoveryAttempts = 0
                        scheduleHide()
                    } else if (state == Player.STATE_ENDED) {
                        completed = true
                        saveProgress(true)
                        chrome.visibility = View.VISIBLE
                        handler.removeCallbacks(hideChrome)
                        endedAwaitingNext = true
                        if (autoPlayNext && nextMediaId != null) playNextEpisode()
                        else if (!nextLookupInFlight) loadNextEpisode()
                    }
                }
                override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                    updatePlaybackScreenAwake()
                }
                override fun onPlayerError(error: PlaybackException) {
                    updatePlaybackScreenAwake()
                    handlePlayerError(error)
                }
            })
        }
        openMedia()
        applyDefaultSubtitlesForThisTv()
        loadNextEpisode()
        handler.post(uiRefresh)
        handler.postDelayed(checkpoint, 15_000)
    }


    private fun dp(value: Int) = (value * resources.displayMetrics.density + .5f).toInt()

    private fun applyPlayerSelectionColor(color: Int) {
        selectedColor = color
        iconControls.forEach { icon ->
            icon.imageTintList = android.content.res.ColorStateList.valueOf(
                if (icon.hasFocus()) color else 0xFFF4EFE4.toInt()
            )
        }
        if (::timeline.isInitialized) {
            timeline.thumbTintList = android.content.res.ColorStateList.valueOf(color)
            timeline.progressTintList = android.content.res.ColorStateList.valueOf(color)
        }
    }

    private fun loadPlayerAppearance() {
        // Native playback is a separate Activity from the WebView and must
        // load the server-owned selection color independently.
        lookups.execute {
            try {
                val settings = request("/api/settings/tv-appearance")
                val hex = settings.optString("selection_color", "#A61E1E")
                if (!Regex("^#[0-9a-fA-F]{6}$").matches(hex)) return@execute
                val color = Color.parseColor(hex)
                runOnUiThread { if (!isFinishing && !shuttingDown)
                    applyPlayerSelectionColor(color) }
            } catch (_: Exception) {
                // Older or offline servers retain the crimson default.
            }
        }
    }

    private fun iconControl(icon: Int, description: String, large: Boolean = false,
                            action: () -> Unit): ImageButton = ImageButton(this).apply {
        val dimension = dp(if (large) 64 else 54)
        layoutParams = LinearLayout.LayoutParams(dimension, dimension)
        setImageResource(icon)
        imageTintList = android.content.res.ColorStateList.valueOf(0xFFF4EFE4.toInt())
        contentDescription = description
        tooltipText = description
        scaleType = ImageView.ScaleType.CENTER_INSIDE
        setPadding(dp(if (large) 15 else 14), dp(if (large) 15 else 14),
                   dp(if (large) 15 else 14), dp(if (large) 15 else 14))
        isFocusable = true
        isFocusableInTouchMode = true
        background = GradientDrawable().apply {
            cornerRadius = dp(40).toFloat()
            setColor(Color.TRANSPARENT)
        }
        iconControls.add(this)
        setOnFocusChangeListener { button, hasFocus ->
            // Match the server's selected focus color and borderless transition.
            // Keep their normal off-white color when focus leaves.
            (button as ImageButton).imageTintList =
                android.content.res.ColorStateList.valueOf(
                    if (hasFocus) selectedColor else 0xFFF4EFE4.toInt()
                )
            button.animate().scaleX(if (hasFocus) 1.16f else 1f)
                .scaleY(if (hasFocus) 1.16f else 1f)
                .alpha(if (hasFocus) 1f else .88f)
                .setDuration(110).start()
            if (hasFocus) showChrome()
        }
        setOnClickListener {
            action()
            showChrome()
        }
    }

    private fun createControls(): LinearLayout {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            // Background gradients must reach the TV edges. Keep horizontal
            // breathing room on the content rows, not the full-width overlay.
            setPadding(0, dp(18), 0, 0)
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(0x7A000000, 0x00000000, 0x00000000)
            )
        }
        val heading = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(32), 0, dp(32), 0)
        }
        heading.addView(iconControl(R.drawable.ic_player_back, "Back to library") { finish() })
        val titles = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(15), 0, 0, 0)
        }
        titles.addView(TextView(this).apply {
            text = "NOW PLAYING"
            textSize = 11f
            letterSpacing = 0.14f
            setTextColor(0xFFDDD7CA.toInt())
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        })
        titleText = TextView(this).apply {
            text = title
            textSize = 22f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setTextColor(0xFFF7F3EB.toInt())
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        titles.addView(titleText)
        heading.addView(titles, LinearLayout.LayoutParams(0, dp(60), 1f))
        root.addView(heading)
        root.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f))

        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            // Previous 32dp parent + 18dp child inset applied to the
            // background as well, leaving visible video gutters on both sides.
            // Apply the same 50dp spacing inside this full-bleed gradient.
            setPadding(dp(50), dp(64), dp(50), dp(23))
            background = GradientDrawable(
                GradientDrawable.Orientation.BOTTOM_TOP,
                intArrayOf(0xF2000000.toInt(), 0xDB090B10.toInt(), 0x00000000)
            )
        }
        val progressRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        elapsed = TextView(this).apply {
            text = "0:00"
            textSize = 15f
            setTextColor(0xFFF4EFE4.toInt())
            minWidth = dp(74)
            setPadding(0, 0, dp(11), 0)
        }
        totalTime = TextView(this).apply {
            text = "0:00"
            textSize = 15f
            setTextColor(0xFFD2CFCA.toInt())
            setPadding(dp(11), 0, 0, 0)
        }
        timeline = SeekBar(this).apply {
            max = 1000
            keyProgressIncrement = 5
            progressTintList = android.content.res.ColorStateList.valueOf(selectedColor)
            thumbTintList = android.content.res.ColorStateList.valueOf(selectedColor)
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(0x66F4EFE4)
            contentDescription = "Seek through video with left and right remote buttons"
            setOnFocusChangeListener { _, hasFocus ->
                if (hasFocus) showChrome()
                else {
                    handler.removeCallbacks(scrubCommit)
                    if (::thumbnailPreview.isInitialized) thumbnailPreview.hideSoon()
                }
            }
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(bar: SeekBar?) {
                    scrubbing = true
                    handler.removeCallbacks(scrubCommit)
                    showScrubAt(currentDuration() * (bar?.progress ?: 0) / 1000.0)
                }
                override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                    if (!fromUser) return
                    val duration = currentDuration()
                    if (duration <= 0) return
                    showScrubAt(duration * progress / 1000.0)
                    if (!scrubbing) {
                        handler.removeCallbacks(scrubCommit)
                        handler.postDelayed(scrubCommit, 550)
                    }
                }
                override fun onStopTrackingTouch(bar: SeekBar?) {
                    scrubbing = false
                    handler.removeCallbacks(scrubCommit)
                    seekTo(currentDuration() * (bar?.progress ?: 0) / 1000.0)
                }
            })
        }
        progressRow.addView(elapsed)
        progressRow.addView(timeline, LinearLayout.LayoutParams(0, dp(55), 1f))
        progressRow.addView(totalTime)
        bottom.addView(progressRow)

        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        val transport = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        transport.addView(iconControl(R.drawable.ic_player_rewind, "Rewind 10 seconds") {
            seekBy(-10.0)
        })
        playButton = iconControl(R.drawable.ic_player_pause, "Play or pause", large = true) {
            val active = player
            if (active?.isPlaying == true) active.pause() else active?.play()
            refreshControls()
        }
        transport.addView(playButton)
        transport.addView(iconControl(R.drawable.ic_player_forward, "Forward 10 seconds") {
            seekBy(10.0)
        })
        toolbar.addView(transport)
        toolbar.addView(View(this), LinearLayout.LayoutParams(0, dp(1), 1f))
        val extras = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        extras.addView(iconControl(R.drawable.ic_player_captions, "Subtitles") { showCaptions() })
        extras.addView(iconControl(R.drawable.ic_player_next, "Next episode") {
            if (nextMediaId != null) playNextEpisode() else showMessage("No next episode available")
        })
        extras.addView(iconControl(R.drawable.ic_player_more, "More playback options") {
            showPlaybackMenu()
        })
        toolbar.addView(extras)
        bottom.addView(toolbar)
        root.addView(bottom)
        return root
    }

    /** Compact native TV menus shared by playback and closed captions.
     * The focused option is marked by a slim accent, never a large focus box.
     */
    private fun showPlayerMenu(
        heading: String,
        options: List<String> = emptyList(),
        selected: Int = -1,
        description: String? = null,
        secondaryLabel: String? = null,
        secondaryAction: (() -> Unit)? = null,
        onSelect: (Int) -> Unit = {}
    ) {
        lateinit var dialog: AlertDialog
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(17), dp(14), dp(17), dp(11))
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setColor(0xF00B111C.toInt())
                setStroke(dp(1), 0x4D566579)
            }
        }
        panel.addView(TextView(this).apply {
            text = heading
            textSize = 18f
            setTextColor(0xFFF3F5F9.toInt())
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(dp(6), 0, dp(6), dp(8))
        })
        if (!description.isNullOrBlank()) {
            panel.addView(TextView(this).apply {
                text = description
                textSize = 13f
                setTextColor(0xFFB8C5D5.toInt())
                setLineSpacing(dp(2).toFloat(), 1f)
                setPadding(dp(6), 0, dp(6), dp(8))
            })
        }
        fun row(label: String, chosen: Boolean = false, action: () -> Unit): LinearLayout {
            val line = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                isFocusable = true
                isFocusableInTouchMode = true
                isClickable = true
                minimumHeight = dp(45)
                contentDescription = label + if (chosen) ", selected" else ""
            }
            val marker = View(this)
            line.addView(marker, LinearLayout.LayoutParams(dp(2), dp(20)).apply {
                marginEnd = dp(9)
            })
            val title = TextView(this).apply {
                text = label
                textSize = 14.5f
                maxLines = 2
                ellipsize = android.text.TextUtils.TruncateAt.END
                gravity = Gravity.CENTER_VERTICAL
            }
            line.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            if (chosen) {
                line.addView(TextView(this).apply {
                    text = "✓"
                    textSize = 16f
                    setTextColor(selectedColor)
                    gravity = Gravity.CENTER
                    contentDescription = "Selected"
                }, LinearLayout.LayoutParams(dp(27), dp(40)))
            }
            fun updateLook(focused: Boolean) {
                title.setTextColor(if (focused) selectedColor else 0xFFE2E9F3.toInt())
                marker.background = GradientDrawable().apply {
                    cornerRadius = dp(2).toFloat()
                    setColor(if (focused) selectedColor else Color.TRANSPARENT)
                }
                line.background = GradientDrawable().apply {
                    cornerRadius = dp(6).toFloat()
                    setColor(if (focused) 0x24253140 else Color.TRANSPARENT)
                }
            }
            updateLook(false)
            line.setOnFocusChangeListener { _, focused -> updateLook(focused) }
            line.setOnClickListener { dialog.dismiss(); action() }
            return line
        }
        val optionViews = mutableListOf<LinearLayout>()
        if (options.isNotEmpty()) {
            val menu = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, dp(3), 0, dp(2))
            }
            options.forEachIndexed { index, title ->
                row(title, chosen = index == selected) { onSelect(index) }.let {
                    optionViews.add(it)
                    menu.addView(it, LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
                }
            }
            val scroll = ScrollView(this).apply {
                isFillViewport = false
                isVerticalScrollBarEnabled = options.size > 6
                overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
                addView(menu)
            }
            val allowedHeight = minOf(dp(330),
                (resources.displayMetrics.heightPixels * 0.58f).toInt())
            panel.addView(scroll, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                minOf(allowedHeight, options.size * dp(47) + dp(7))))
        }
        val footer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END or Gravity.CENTER_VERTICAL
            setPadding(0, dp(2), 0, 0)
        }
        if (secondaryLabel != null && secondaryAction != null) {
            footer.addView(row(secondaryLabel) { secondaryAction() },
                LinearLayout.LayoutParams(0, dp(43), 1f))
        }
        val close = row("Close") {}
        footer.addView(close, LinearLayout.LayoutParams(dp(86), dp(43)))
        panel.addView(footer)
        dialog = AlertDialog.Builder(this).setView(panel).create()
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setDimAmount(0.43f)
            setLayout(minOf(dp(430), resources.displayMetrics.widthPixels - dp(44)),
                ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        optionViews.getOrNull(selected.takeIf { it in optionViews.indices } ?: 0)
            ?.requestFocus() ?: close.requestFocus()
    }

    private fun showPlaybackMenu() {
        val labels = arrayOf(
            if (completed) "Mark as unwatched" else "Mark as watched",
            "Quality: " + Quality.label(quality),
            "Playback details",
            "Play from beginning"
        )
        showPlayerMenu("Playback options", labels.toList(), onSelect = { choice ->
            when (choice) {
                0 -> toggleWatched()
                1 -> showQualityMenu()
                2 -> showDiagnostics()
                3 -> seekTo(0.0)
            }
            showChrome()
        })
    }

    private fun showQualityMenu() {
        val options = Quality.options
        showPlayerMenu("Playback quality", options.map { it.label },
            selected = options.indexOfFirst { it.id == quality }.coerceAtLeast(0),
            onSelect = { which ->
                applyQuality(options[which].id)
                showChrome()
            })
    }

    /** Remember the choice for this TV and switch the current playback to it. */
    private fun applyQuality(id: String) {
        val chosen = Quality.normalize(id)
        if (chosen == quality) return
        quality = chosen
        progressStore.edit().putString("quality:$server", chosen).apply()
        switchSource(seek.pendingTarget() ?: currentPosition())
    }

    /**
     * Re-opens the video at [position] for the current quality choice: the
     * original file when allowed and playable, otherwise a transcode.
     */
    private fun switchSource(position: Double) {
        if (shuttingDown) return
        if (Quality.allowsDirect(quality) && directCapable && directUrl.isNotBlank()) {
            val previous = session
            session = null
            hlsStarts.next()            // abandon any HLS start still in flight
            hlsMode = false
            hlsOffset = 0.0
            showMessage("Switching to original quality…")
            player?.setMediaItem(MediaItem.fromUri(resolveUrl(directUrl)))
            player?.prepare()
            player?.seekTo((position * 1000).toLong())
            player?.playWhenReady = true
            if (selectedCaption != null) applyCaption()
            previous?.let {
                network.execute {
                    try { request("/api/stream/hls/$it", "DELETE") } catch (_: Exception) {}
                }
            }
        } else {
            showMessage("Switching to " + Quality.transcodeParam(quality) + "…")
            restartHls(position, SeekTracker.NO_GENERATION)
        }
    }

    /**
     * Recovers from a playback error when that is likely to help: a dropped
     * connection retries the same source, an expired transcoding session starts
     * a new one at the current position, and a file this TV cannot decode falls
     * back to a transcode. Attempts are bounded; the final failure says what to try.
     */
    private fun handlePlayerError(error: PlaybackException) {
        if (shuttingDown) return
        val position = currentPosition()
        val action = PlaybackRecovery.decide(error.errorCode, hlsMode, recoveryAttempts, fallbackStarted)
        NavTrace.log { "PLAYER_ERROR code=${error.errorCodeName} hls=$hlsMode attempts=$recoveryAttempts action=$action" }
        Log.w("YarrMedia", "Player error ${error.errorCodeName} (hls=$hlsMode): ${error.message}")
        when (action) {
            RecoveryAction.RETRY_SAME_SOURCE -> {
                val attempt = ++recoveryAttempts
                lastRecoveryAt = android.os.SystemClock.uptimeMillis()
                showMessage("Connection problem. Retrying ($attempt/${PlaybackRecovery.MAX_ATTEMPTS})…")
                handler.postDelayed({
                    val exo = player
                    if (!shuttingDown && exo != null && !hlsMode) {
                        exo.prepare()
                        exo.seekTo((position * 1000).toLong())
                        exo.playWhenReady = true
                    }
                }, PlaybackRecovery.backoffMs(attempt))
            }
            RecoveryAction.RESTART_HLS -> {
                val attempt = ++recoveryAttempts
                lastRecoveryAt = android.os.SystemClock.uptimeMillis()
                showMessage("Reconnecting stream ($attempt/${PlaybackRecovery.MAX_ATTEMPTS})…")
                handler.postDelayed({
                    if (!shuttingDown) restartHls(position, SeekTracker.NO_GENERATION)
                }, if (attempt == 1) 0L else PlaybackRecovery.backoffMs(attempt - 1))
            }
            RecoveryAction.FALLBACK_TO_HLS -> {
                fallbackStarted = true
                showMessage("Direct play unavailable. Preparing compatible stream…")
                startHls(position)
            }
            RecoveryAction.GIVE_UP ->
                showMessage("Playback failed (${error.errorCodeName}). " +
                    "Press Back to retry, or pick a lower quality in More options.")
        }
    }

    private fun showScrubAt(position: Double) {
        val duration = currentDuration()
        scrubPosition = position.coerceIn(0.0, if (duration > 0) duration else 1e7)
        if (::thumbnailPreview.isInitialized) thumbnailPreview.show(scrubPosition)
        showChrome()
    }

    private fun currentDuration(): Double {
        if(durationSeconds>0 && durationSeconds.isFinite())return durationSeconds
        val value = player?.duration ?: C.TIME_UNSET
        return if(value>0 && value!=C.TIME_UNSET)value/1000.0 else 0.0
    }

    private fun currentPosition() = (
        ((player?.currentPosition ?: 0L).coerceAtLeast(0L) / 1000.0) +
        if(hlsMode)hlsOffset else 0.0
    ).coerceAtLeast(0.0)

    private fun fmt(seconds: Double): String {
        val v = seconds.toLong().coerceAtLeast(0)
        val h = v / 3600
        val m = v % 3600 / 60
        val sec = v % 60
        return if(h>0) "%d:%02d:%02d".format(h,m,sec)
               else "%d:%02d".format(m,sec)
    }

    private fun refreshControls() {
        if(!::timeline.isInitialized) return
        val duration = currentDuration()
        val position = currentPosition().coerceAtMost(if(duration>0)duration else Double.MAX_VALUE)
        // While a seek is pending (being requested, debounced, or waiting for
        // an HLS restart) show the REQUESTED position, never the stale one the
        // decoder is still reporting.
        val displayedPosition = seek.displayed(position)
        if(!timeline.isPressed && !scrubbing && duration>0)
            timeline.progress = (displayedPosition/duration*1000).toInt().coerceIn(0,1000)
        elapsed.text = fmt(displayedPosition)
        totalTime.text = fmt(duration)
        playButton.setImageResource(
            if (player?.isPlaying == true) R.drawable.ic_player_pause else R.drawable.ic_player_play
        )
    }

    /** Relative remote seek; accumulates from the pending target while one exists. */
    private fun seekBy(delta: Double) {
        val generation = seek.requestBy(delta, currentPosition(), currentDuration())
        scheduleSeekCommit(generation)
    }

    private fun seekTo(seconds: Double) {
        scheduleSeekCommit(seek.requestTo(seconds, currentDuration()))
    }

    /**
     * Updates the bar immediately and (re)starts the debounce. Only the most
     * recent generation is ever committed, so a held button produces ONE seek.
     */
    private fun scheduleSeekCommit(generation: Long) {
        val target = seek.pendingTarget() ?: return
        showScrubAt(target)
        thumbnailPreview.hideSoon()
        refreshControls()
        seekCommit?.let(handler::removeCallbacks)
        val action = Runnable {
            seekCommit = null
            commitSeek(generation)
        }
        seekCommit = action
        handler.postDelayed(action, SEEK_DEBOUNCE_MS)
    }

    private fun commitSeek(generation: Long) {
        val target = seek.beginCommit(generation) ?: return   // superseded
        val p = player
        NavTrace.log { "SEEK_COMMIT gen=$generation target=$target hls=$hlsMode" }
        if (p == null) { seek.settle(generation); return }
        if (hlsMode) {
            val relative = target - hlsOffset
            val buffered = p.bufferedPosition / 1000.0
            if (relative >= 0 && relative < buffered - 0.3 && p.isCurrentMediaItemSeekable) {
                p.seekTo((relative * 1000).toLong())
                seek.settle(generation)
            } else {
                restartHls(target, generation)
            }
        } else {
            // The player reports the new position as soon as seekTo returns.
            p.seekTo((target * 1000).toLong())
            seek.settle(generation)
        }
        showChrome()
    }

    /** Seeks outside the transcoded range by starting a new session at [target]. */
    private fun restartHls(target: Double, generation: Long) {
        val previous = session
        session = null
        val serial = hlsStarts.next()
        player?.stop()
        network.execute {
            previous?.let {
                try { request("/api/stream/hls/$it", "DELETE") } catch (_: Exception) {}
            }
            startHlsOnNetwork(target, serial, generation)
        }
    }

    /**
     * Left/Right while the timeline is the active control (or the controls are
     * hidden): step the seek target. Held buttons repeat at a fixed cadence.
     */
    private fun handleSeekKey(direction: Int, repeatCount: Int) {
        val now = android.os.SystemClock.uptimeMillis()
        if (repeatCount > 0 && now - lastSeekKeyAt < SEEK_REPEAT_MS) return
        lastSeekKeyAt = now
        val hidden = chrome.visibility != View.VISIBLE
        showChrome()
        // After the controls auto-hide Android has dropped focus; put it back on
        // the timeline so the following presses keep seeking.
        if (hidden || currentFocus == null) timeline.requestFocus()
        NavTrace.log { "SEEK_KEY dir=$direction repeat=$repeatCount pending=${seek.pendingTarget()}" }
        seekBy(direction * SEEK_STEP_SECONDS)
    }

    private fun showChrome() {
        if(::chrome.isInitialized)chrome.visibility=View.VISIBLE
        scheduleHide()
    }
    private fun scheduleHide() {
        handler.removeCallbacks(hideChrome)
        if(player?.isPlaying==true)handler.postDelayed(hideChrome,3500)
    }

    private fun showDiagnostics() {
        val p=player
        val messageText = "Playback: "+(if(hlsMode)"HLS transcoding" else "Direct play")+
            "\nQuality: "+Quality.label(quality)+
            "\nState: "+(p?.playbackState ?: -1)+
            "\nPosition: "+fmt(currentPosition())+
            "\nServer: "+server+
            "\nSession: "+(if(session!=null)"Active" else "None")
        showPlayerMenu("Playback diagnostics", description = messageText)
    }

    private fun toggleWatched() {
        val next = !completed
        network.execute {
            try {
                val url=URL(resolveUrl("/api/watch/$mediaId/watched"))
                val connection=url.openConnection() as HttpURLConnection
                try {
                    connection.requestMethod="PUT"
                    connection.connectTimeout=5000
                    connection.readTimeout=5000
                    connection.doOutput=true
                    connection.setRequestProperty("Content-Type","application/json")
                    connection.outputStream.use {
                        it.write(JSONObject().put("watched",next).toString().toByteArray())
                    }
                    if(connection.responseCode !in 200..299)throw IllegalStateException("HTTP "+connection.responseCode)
                    handler.post {
                        completed = next
                        replayingWatchedEpisode = false
                        showMessage(if(next)"Marked watched" else "Marked unwatched")
                    }
                }finally{connection.disconnect()}
            }catch(error:Exception){
                handler.post {showMessage("Could not update watched status: "+error.message)}
            }
        }
    }

    private val subtitleLanguages = arrayOf(
        "English" to "en", "Spanish" to "es", "French" to "fr",
        "German" to "de", "Italian" to "it", "Portuguese" to "pt",
        "Japanese" to "ja", "Korean" to "ko"
    )

    /** Respect TV-specific subtitle display settings, independent of the chosen track.
     * Embedded cue background/style is disabled so the chosen opacity wins.
     */
    private fun applySubtitleAppearance() {
        if (!::playerView.isInitialized) return
        val prefs = getSharedPreferences("oew_tv_subtitles", MODE_PRIVATE)
        val backgroundAlpha = when (prefs.getString("background", "none")) {
            "25" -> 0x40
            "50" -> 0x80
            "75" -> 0xBF
            "100" -> 0xFF
            else -> 0x00
        }
        val background = (backgroundAlpha shl 24)
        val foreground = if (prefs.getString("color", "white") == "yellow")
            Color.YELLOW else Color.WHITE
        val textSize = when (prefs.getString("size", "normal")) {
            "small" -> 0.042f
            "large" -> 0.068f
            else -> 0.0533f
        }
        playerView.subtitleView?.apply {
            setApplyEmbeddedStyles(false)
            setStyle(CaptionStyleCompat(
                foreground, background, Color.TRANSPARENT,
                if (prefs.getBoolean("outline", true))
                    CaptionStyleCompat.EDGE_TYPE_OUTLINE
                else CaptionStyleCompat.EDGE_TYPE_NONE,
                Color.BLACK, android.graphics.Typeface.DEFAULT
            ))
            setFractionalTextSize(textSize)
        }
    }

    /** Subtitle choices are stored in this TV's app data, never on the server. */
    private fun applyDefaultSubtitlesForThisTv() {
        val local = getSharedPreferences("oew_tv_subtitles", MODE_PRIVATE)
        if (!local.getBoolean("enabled", false)) return
        val preferred = local.getString("language", "en") ?: "en"
        if (subtitleLanguages.none { it.second == preferred }) return
        captionLanguage = preferred
        lookups.execute {
            try {
                val tracks = request("/api/stream/subtitles/$mediaId").optJSONArray("tracks")
                    ?: return@execute
                val aliases = when (preferred) {
                    "en" -> setOf("en", "eng", "english")
                    "es" -> setOf("es", "spa", "spanish", "espanol", "español")
                    "fr" -> setOf("fr", "fra", "fre", "french", "francais", "français")
                    "de" -> setOf("de", "deu", "ger", "german", "deutsch")
                    "it" -> setOf("it", "ita", "italian", "italiano")
                    "pt" -> setOf("pt", "por", "portuguese", "portugues", "português")
                    "ja" -> setOf("ja", "jpn", "japanese")
                    "ko" -> setOf("ko", "kor", "korean")
                    else -> emptySet()
                }
                val tracksFound = mutableListOf<Pair<String, String>>()
                for (index in 0 until tracks.length()) {
                    val item = tracks.optJSONObject(index) ?: continue
                    val id = item.optString("id")
                    if (!Regex("^(external|embedded)-[0-9]{1,3}$|^downloaded-[1-9][0-9]{0,11}-[a-z]{2,3}(-[a-z]{2})?$").matches(id)) continue
                    val label = item.optString("label", "").lowercase(java.util.Locale.ROOT)
                    val language = item.optString("language", "").lowercase(java.util.Locale.ROOT)
                    tracksFound.add(id to "$language $label")
                }
                val chosen = tracksFound.firstOrNull { (_, descriptor) ->
                    descriptor.split(Regex("[^\\p{L}\\p{N}]+")).any { it in aliases }
                } ?: tracksFound.singleOrNull()?.takeIf { (_, descriptor) ->
                    descriptor.trim() in setOf("", "subtitles", "embedded subtitles", "subtitle")
                }
                if (chosen != null) handler.post {
                    if (!shuttingDown && selectedCaption == null) {
                        selectedCaption = chosen.first
                        applyCaption()
                    }
                }
            } catch (_: Exception) {
                // Missing tracks, unsupported formats, or network problems
                // must never block a movie or episode from playing.
            }
        }
    }

    /** Existing tracks plus the same OpenSubtitles workflow as server/player.js. */
    private fun showCaptions() {
        showChrome()
        lookups.execute {
            try {
                val tracks = request("/api/stream/subtitles/$mediaId").optJSONArray("tracks")
                val labels = mutableListOf("Off")
                val ids = mutableListOf<String?>(null)
                if (tracks != null) for (i in 0 until tracks.length()) {
                    val item = tracks.optJSONObject(i) ?: continue
                    val id = item.optString("id")
                    // Track IDs must follow the server's allowed subtitle scheme.
                    if (!Regex("^(external|embedded)-[0-9]{1,3}$|^downloaded-[1-9][0-9]{0,11}-[a-z]{2,3}(-[a-z]{2})?$").matches(id))
                        continue
                    labels.add(item.optString("label", "Subtitles").take(80))
                    ids.add(id)
                }
                labels.add("Search OpenSubtitles…")
                handler.post {
                    if (shuttingDown) return@post
                    showPlayerMenu("Closed Captions", labels,
                        selected = ids.indexOf(selectedCaption).coerceAtLeast(0),
                        onSelect = { index ->
                            if (index == labels.lastIndex) {
                                chooseSubtitleLanguage()
                            } else {
                                selectedCaption = ids[index]
                                applyCaption()
                                showChrome()
                            }
                        })
                }
            } catch (error: Exception) {
                handler.post { if (!shuttingDown) showMessage("Subtitles unavailable: ${error.message}") }
            }
        }
    }

    private fun chooseSubtitleLanguage() {
        showChrome()
        showPlayerMenu("Search subtitle language",
            subtitleLanguages.map { it.first }, onSelect = { index ->
                searchOpenSubtitles(subtitleLanguages[index].second)
            })
    }

    private fun searchOpenSubtitles(language: String) {
        if (shuttingDown || subtitleLanguages.none { it.second == language }) return
        showMessage("Searching OpenSubtitles…")
        lookups.execute {
            try {
                val query = java.net.URLEncoder.encode(language, "UTF-8")
                val results = request("/api/stream/subtitles/$mediaId/search?language=$query")
                    .optJSONArray("results")
                if (results == null || results.length() == 0) {
                    handler.post { if (!shuttingDown) showMessage("No subtitle matches found.") }
                    return@execute
                }
                val options = mutableListOf<Pair<Int, String>>()
                val names = mutableListOf<String>()
                for (i in 0 until results.length()) {
                    val item = results.optJSONObject(i) ?: continue
                    val fileId = item.optInt("file_id")
                    if (fileId <= 0) continue
                    val release = item.optString("release", "Subtitle").take(130)
                    val text = buildString {
                        append(release)
                        append(" · ")
                        append(item.optString("language", language))
                        if (item.optBoolean("hearing_impaired", false)) append(" · SDH")
                        val downloads = item.optInt("downloads", 0)
                        if (downloads > 0) append(" · ").append(downloads).append(" downloads")
                    }
                    names.add(text)
                    options.add(fileId to language)
                }
                handler.post {
                    if (shuttingDown) return@post
                    message.visibility = View.GONE
                    if (options.isEmpty()) {
                        showMessage("No downloadable subtitle matches found.")
                        return@post
                    }
                    showPlayerMenu("OpenSubtitles results", names,
                        secondaryLabel = "Change language",
                        secondaryAction = { chooseSubtitleLanguage() },
                        onSelect = { selected ->
                            val (id, lang) = options[selected]
                            downloadSubtitle(id, lang)
                        })
                }
            } catch (error: Exception) {
                handler.post { if (!shuttingDown) showMessage("Subtitle search failed: ${error.message}") }
            }
        }
    }

    private fun downloadSubtitle(fileId: Int, language: String) {
        if (fileId <= 0 || subtitleLanguages.none { it.second == language } || shuttingDown) return
        showMessage("Downloading subtitle…")
        lookups.execute {
            try {
                val query = java.net.URLEncoder.encode(language, "UTF-8")
                val result = request(
                    "/api/stream/subtitles/$mediaId/download?language=$query",
                    "POST", JSONObject().put("file_id", fileId)
                )
                val trackId = result.optString("track_id")
                if (!Regex("^downloaded-[1-9][0-9]{0,11}-[a-z]{2,3}(-[a-z]{2})?$")
                        .matches(trackId))
                    throw IllegalStateException("Server did not return a valid subtitle track")
                handler.post {
                    if (shuttingDown) return@post
                    selectedCaption = trackId
                    applyCaption()
                    message.visibility = View.GONE
                    showChrome()
                }
            } catch (error: Exception) {
                handler.post { if (!shuttingDown) showMessage("Subtitle download failed: ${error.message}") }
            }
        }
    }

    private fun applyCaption() {
        val current=player?.currentMediaItem ?: return
        val position=player?.currentPosition ?: 0L
        val subtitle=selectedCaption?.let{ id->
            MediaItem.SubtitleConfiguration.Builder(
                android.net.Uri.parse(resolveUrl("/api/stream/subtitles/$mediaId/$id.vtt"+
                    if(hlsMode)"?start=$hlsOffset" else "")))
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(captionLanguage)
                .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                .build()
        }
        val updated=MediaItem.Builder().setUri(current.localConfiguration?.uri ?: return)
            .setMimeType(current.localConfiguration?.mimeType)
            .setSubtitleConfigurations(if(subtitle==null)emptyList() else listOf(subtitle))
            .build()
        player?.setMediaItem(updated)
        player?.prepare()
        player?.seekTo(position)
        player?.playWhenReady=true
    }

    private fun loadNextEpisode() {
        if (nextLookupInFlight || shuttingDown) return
        nextLookupInFlight = true
        lookups.execute {
            // Read independently: a failed settings call must not throw away
            // the next episode, and late responses must still trigger autoplay.
            val enabled = try {
                request("/api/settings/playback").optBoolean("auto_play_next", false)
            } catch (error: Exception) {
                Log.w("OEWPlayer", "Could not load autoplay setting", error)
                null
            }
            val next = try {
                if (seasonShuffle) shuffleQueue.optJSONObject(0)
                else request("/api/tv/next?media_id=$mediaId&include_watched=true")
                    .optJSONObject("next")
            } catch (error: Exception) {
                Log.w("OEWPlayer", "Could not load next episode", error)
                null
            }
            handler.post {
                nextLookupInFlight = false
                if (shuttingDown || isFinishing) return@post
                if (enabled != null) autoPlayNext = enabled || seasonShuffle
                else if (seasonShuffle) autoPlayNext = true
                nextMediaId = next?.optInt("media_id")?.takeIf { it > 0 }
                nextTitle = next?.optString("title", "Next Episode") ?: ""
                if (endedAwaitingNext && autoPlayNext && nextMediaId != null)
                    playNextEpisode()
            }
        }
    }

    private fun playNextEpisode() {
        val next = nextMediaId ?: return
        // The configured auto-play setting means play without a dialog.
        // Guard against duplicate STATE_ENDED callbacks and fast remote presses.
        if (advancingToNext || isFinishing) return
        advancingToNext = true
        endedAwaitingNext = false
        val following = android.content.Intent(this, PlayerActivity::class.java)
            .putExtra("media_id", next).putExtra("title", nextTitle)
            .putExtra("server", server)
            .putExtra("restart",
                if (seasonShuffle)
                    shuffleQueue.optJSONObject(0)?.optBoolean("restart", true) ?: true
                else true)
        if (seasonShuffle) {
            val remaining = JSONArray()
            for (i in 1 until shuffleQueue.length()) remaining.put(shuffleQueue.get(i))
            following.putExtra("shuffle_queue", remaining.toString())
        }
        startActivity(following)
        finish()
    }

    private fun isSeekKey(code: Int) = code == KeyEvent.KEYCODE_DPAD_LEFT ||
        code == KeyEvent.KEYCODE_DPAD_RIGHT || code == KeyEvent.KEYCODE_MEDIA_REWIND ||
        code == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode in intArrayOf(
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN,
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                KeyEvent.KEYCODE_BACK) &&
            (event.repeatCount == 0 || event.repeatCount % 8 == 0 ||
             event.action == KeyEvent.ACTION_UP)) {
            NavTrace.log {
                "PLAYER_KEY code=${event.keyCode} action=${event.action}" +
                    " repeat=${event.repeatCount} focus=${currentFocus?.contentDescription}" +
                    " chrome=${if (::chrome.isInitialized) chrome.visibility else -1}"
            }
        }
        if (event.keyCode == KeyEvent.KEYCODE_BACK) return super.dispatchKeyEvent(event)
        val direction = event.keyCode
        val isDpad = direction in intArrayOf(
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN,
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT
        )
        if (::chrome.isInitialized && isSeekKey(direction)) {
            val mediaKey = direction == KeyEvent.KEYCODE_MEDIA_REWIND ||
                direction == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD
            val focused = currentFocus
            // Left/Right seek unless the viewer has moved down to the toolbar
            // buttons, where they still move between buttons.
            val seeks = mediaKey || chrome.visibility != View.VISIBLE ||
                focused == null || focused === timeline
            if (seeks) {
                // Consume DOWN *and* UP: the SeekBar must never apply its own
                // key increment on top of ours.
                if (event.action == KeyEvent.ACTION_DOWN) {
                    val sign = if (direction == KeyEvent.KEYCODE_DPAD_RIGHT ||
                        direction == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD) 1 else -1
                    handleSeekKey(sign, event.repeatCount)
                }
                return true
            }
        }
        // Consume the paired UP independently of current focus. Focus moves
        // to Play after the DOWN; letting UP through could click a different
        // button (including Back) and immediately close the video.
        val selectKey = direction == KeyEvent.KEYCODE_DPAD_CENTER ||
            direction == KeyEvent.KEYCODE_ENTER ||
            direction == KeyEvent.KEYCODE_NUMPAD_ENTER
        if (selectKey && event.action == KeyEvent.ACTION_UP && consumedPlaybackSelect) {
            consumedPlaybackSelect = false
            return true
        }
        if (isDpad && event.action == KeyEvent.ACTION_UP) {
            if (lastRemoteDirection == direction) lastRemoteDirection = -1
            return true
        }
        if (event.action == KeyEvent.ACTION_DOWN && ::chrome.isInitialized) {
            when (direction) {
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                    if (event.repeatCount == 0) {
                        val active = player
                        if (active?.isPlaying == true) active.pause() else active?.play()
                        showChrome()
                    }
                    return true
                }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                    // OK on visible transport controls respects focus. OK on
                    // the video/timeline, or with hidden chrome, toggles playback
                    // and *always* hands focus to Play so the next OK resumes.
                    val focused = currentFocus
                    val controlsHidden = chrome.visibility != View.VISIBLE
                    val videoSelected = focused == null || focused === timeline ||
                        focused === playerView
                    if (controlsHidden || videoSelected || focused === playButton) {
                        consumedPlaybackSelect = true
                        if (event.repeatCount == 0) {
                            val active = player
                            if (active?.isPlaying == true) active.pause() else active?.play()
                            showChrome()
                            playButton.requestFocus()
                            refreshControls()
                            applyPlayerSelectionColor(selectedColor)
                        }
                        return true
                    }
                }
            }
            if (isDpad) {
                val now = android.os.SystemClock.uptimeMillis()
                val fresh = lastRemoteDirection != direction || event.repeatCount == 0
                if (!fresh && now - lastRemoteMoveAt < 190L) return true
                lastRemoteDirection = direction
                lastRemoteMoveAt = now
                if (chrome.visibility != View.VISIBLE) {
                    showChrome()
                    // First Up/Down press reveals the controls.
                    playButton.requestFocus()
                    return true
                }
                // The native player has three logical focus rows. Do not
                // delegate Up/Down to Android's geometric focusSearch(), which
                // may alternate between controls as animations scale icons.
                // Leave dialogs to their own window's focus handling.
                if (direction == KeyEvent.KEYCODE_DPAD_UP ||
                    direction == KeyEvent.KEYCODE_DPAD_DOWN) {
                    val focused = currentFocus
                    if (focused === timeline) {
                        if (direction == KeyEvent.KEYCODE_DPAD_UP)
                            iconControls.firstOrNull()?.requestFocus()
                        else playButton.requestFocus()
                    } else if (focused === iconControls.firstOrNull()) {
                        if (direction == KeyEvent.KEYCODE_DPAD_DOWN)
                            timeline.requestFocus()
                    } else if (iconControls.any { it === focused }) {
                        if (direction == KeyEvent.KEYCODE_DPAD_UP)
                            timeline.requestFocus()
                    } else playButton.requestFocus()
                    return true
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    private fun showMessage(text: String) {
        message.text = text
        message.visibility = View.VISIBLE
    }

    private fun resolveUrl(path: String): String =
        URI(server + "/").resolve(path).toString()

    private fun request(
        path: String, method: String = "GET", payload: JSONObject? = null
    ): JSONObject {
        val connection = URL(resolveUrl(path)).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 7000
            connection.readTimeout =
                if (path.contains("/search") || path.contains("/download")) 45_000 else 10_000
            connection.setRequestProperty("Accept", "application/json")
            if (method == "POST") {
                connection.doOutput = true
                val bytes = payload?.toString()?.toByteArray(Charsets.UTF_8) ?: ByteArray(0)
                if (payload != null)
                    connection.setRequestProperty("Content-Type", "application/json")
                connection.setFixedLengthStreamingMode(bytes.size)
                connection.outputStream.use { it.write(bytes) }
            }
            val code = connection.responseCode
            val body = (if (code in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val detail = try {
                    JSONObject(body).optString("detail").takeIf { it.isNotBlank() }
                } catch (_: Exception) { null }
                throw IllegalStateException(detail ?: "Server returned HTTP $code")
            }
            return JSONObject(body)
        } finally {
            connection.disconnect()
        }
    }

    private fun canDirectPlay(media: JSONObject, extension: String): Boolean {
        if (extension !in setOf(".mp4", ".m4v", ".mov", ".mkv", ".webm",
                ".ts", ".m2ts", ".mpg", ".mpeg")) return false
        val videoMime = when (media.optString("video_codec").lowercase()) {
            "h264" -> "video/avc"
            "hevc" -> "video/hevc"
            "vp8" -> "video/x-vnd.on2.vp8"
            "vp9" -> "video/x-vnd.on2.vp9"
            "av1" -> "video/av01"
            "mpeg2video" -> "video/mpeg2"
            "mpeg4" -> "video/mp4v-es"
            else -> return false
        }
        val audioMime = when (media.optString("audio_codec").lowercase()) {
            "" -> null
            "aac" -> "audio/mp4a-latm"
            "ac3" -> "audio/ac3"
            "eac3" -> "audio/eac3"
            "dts" -> "audio/vnd.dts"
            "truehd" -> "audio/true-hd"
            "opus" -> "audio/opus"
            "vorbis" -> "audio/vorbis"
            "mp3" -> "audio/mpeg"
            "flac" -> "audio/flac"
            else -> return false
        }
        return try {
            val width = media.optInt("width", 0)
            val height = media.optInt("height", 0)
            if (width <= 0 || height <= 0) return false
            val codecs = MediaCodecList(MediaCodecList.REGULAR_CODECS)
            val format = MediaFormat.createVideoFormat(videoMime, width, height)
            if (codecs.findDecoderForFormat(format) == null) return false
            if (audioMime != null) {
                val audio = MediaFormat.createAudioFormat(
                    audioMime, 48000, media.optInt("audio_channels", 2).coerceAtLeast(1)
                )
                if (codecs.findDecoderForFormat(audio) == null) return false
            }
            true
        } catch (_: Exception) { false }
    }

    private fun openMedia() {
        network.execute {
            try {
                quality = Quality.normalize(progressStore.getString("quality:$server", null))
                val info = request("/api/watch/$mediaId/status")
                val restart = intent.getBooleanExtra("restart", false)
                if (restart) progressStore.edit().remove(progressKey()).apply()
                val stored = if (restart) null else pendingProgress()
                val serverPosition = info.optDouble("position_seconds", 0.0).coerceAtLeast(0.0)
                val storedPosition = stored?.optDouble("position_seconds", 0.0)
                    ?.takeIf { it.isFinite() && it > 0.0 } ?: 0.0
                val resume = if (restart || info.optBoolean("watched", false)) 0.0
                    else maxOf(serverPosition, storedPosition)
                durationSeconds = info.optDouble("duration_seconds", 0.0)
                completed = info.optBoolean("watched",false)
                replayingWatchedEpisode = completed
                val mode = info.optString("mode", "")
                val actual = info.optJSONObject("media")
                val direct = if (actual != null && actual.optString("video_codec").isNotBlank())
                    canDirectPlay(actual, info.optString("extension", ""))
                    else mode == "direct"
                val streamUrl = info.optString("stream_url", "")
                directCapable = direct && streamUrl.isNotBlank()
                directUrl = streamUrl
                if (directCapable && Quality.allowsDirect(quality)) {
                    handler.post {
                        if (!shuttingDown) {
                            hlsMode = false
                            player?.setMediaItem(MediaItem.fromUri(resolveUrl(streamUrl)))
                            player?.prepare()
                            player?.seekTo((resume * 1000).toLong())
                            player?.playWhenReady = true
                            if (selectedCaption != null) applyCaption()
                        }
                    }
                } else {
                    startHlsOnNetwork(resume)
                }
            } catch (error: Exception) {
                handler.post {
                    if (!shuttingDown) showMessage("Could not start video: ${error.message}")
                }
            }
        }
    }

    /** Starts a transcoding session, retrying brief network failures (not HTTP refusals). */
    private fun createHlsSession(start: Double): JSONObject {
        var failure: java.io.IOException? = null
        for (attempt in 0 until 3) {
            try {
                return request("/api/stream/hls/start/$mediaId?start=$start" +
                    "&quality=${Quality.transcodeParam(quality)}", "POST")
            } catch (error: java.io.IOException) {
                failure = error
                Thread.sleep(800L * (attempt + 1))
            }
        }
        throw failure ?: IllegalStateException("Could not reach the server")
    }

    private fun startHls(position: Double) {
        if (shuttingDown) return
        val serial = hlsStarts.next()
        player?.stop()
        network.execute { startHlsOnNetwork(position, serial) }
    }

    /**
     * Starts a transcoding session at [position] and plays it, unless a newer
     * start (or a newer seek) has been issued meanwhile. A superseded start
     * deletes the session it created and never touches the player, so an older
     * asynchronous seek cannot overwrite a newer one. [generation] ties the
     * start to the seek that caused it.
     */
    private fun startHlsOnNetwork(
        position: Double,
        serial: Long = hlsStarts.next(),
        generation: Long = SeekTracker.NO_GENERATION
    ) {
        fun superseded() = shuttingDown || !hlsStarts.isCurrent(serial)
        if (superseded()) return
        var createdToken: String? = null
        fun discard(token: String) {
            try { request("/api/stream/hls/$token", "DELETE") } catch (_: Exception) {}
            if (session == token) session = null
        }
        try {
            val start = position.coerceAtLeast(0.0)
            handler.post { if (!superseded()) showMessage("Preparing compatible HLS stream…") }
            val created = createHlsSession(start)
            val token = created.getString("session")
            createdToken = token
            if (superseded()) { discard(token); return }
            session = token
            var ready: JSONObject? = null
            for (attempt in 0 until 80) {
                if (superseded()) { discard(token); return }
                Thread.sleep(400)
                val candidate = request("/api/stream/hls/$token/status")
                if (candidate.optBoolean("ready")) { ready = candidate; break }
            }
            val playlist = ready?.optString("playlist").orEmpty()
            if (playlist.isBlank()) throw IllegalStateException("HLS transcoder did not become ready")
            handler.post {
                if (superseded()) {
                    network.execute { discard(token) }
                    return@post
                }
                hlsMode = true
                hlsOffset = start
                val item = MediaItem.Builder()
                    .setUri(resolveUrl(playlist))
                    .setMimeType(MimeTypes.APPLICATION_M3U8)
                    .build()
                player?.setMediaItem(item)
                player?.prepare()
                player?.seekTo(0L) // EVENT HLS begins at zero, not the live edge.
                player?.playWhenReady = true
                if (selectedCaption != null) applyCaption()
                // The new session now starts at the requested position. If the
                // viewer has pressed again meanwhile, settle() is a no-op and
                // their newer target stays on screen.
                if (generation != SeekTracker.NO_GENERATION) seek.settle(generation)
                NavTrace.log { "HLS_READY serial=$serial offset=$start gen=$generation" }
            }
        } catch (error: Exception) {
            createdToken?.let { discard(it) }
            handler.post {
                if (generation != SeekTracker.NO_GENERATION) seek.settle(generation)
                if (!superseded()) showMessage("Compatible playback failed: ${error.message}")
            }
        }
    }

    /**
     * The server supports POST and PUT for playback checkpoints. POST is used
     * here so we do not depend on network intermediaries accepting PUT bodies.
     * Keep requests serialized on the player executor: the last checkpoint
     * should follow older 15-second heartbeats.
     */
    private fun persistProgress(body: String): String? {
        var lastFailure = "Unknown error"
        for (attempt in 0..1) {
            try {
                val connection = URL(resolveUrl("/api/playback/progress"))
                    .openConnection() as HttpURLConnection
                try {
                    connection.requestMethod = "POST"
                    // Avoid reusing a stale keep-alive socket while Media3
                    // sustains its long-lived video streaming connection.
                    connection.setRequestProperty("Connection", "close")
                    connection.useCaches = false
                    connection.connectTimeout = 8_000
                    connection.readTimeout = 12_000
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.setRequestProperty("Accept", "application/json")
                    val bytes = body.toByteArray(Charsets.UTF_8)
                    connection.setFixedLengthStreamingMode(bytes.size)
                    connection.outputStream.use { it.write(bytes) }
                    val status = connection.responseCode
                    if (status in 200..299) return null
                    lastFailure = "HTTP $status"
                    // Retry only temporary server errors. A 4xx needs diagnosis.
                    if (status < 500) break
                } finally {
                    connection.disconnect()
                }
            } catch (error: Exception) {
                // Do not hide the underlying cause behind "check connection".
                // The message is visible while playing, but does not expose
                // request body or the user's server URL.
                val kind = error.javaClass.simpleName
                lastFailure = if (kind.isNotEmpty()) kind else "Network error"
                Log.w("YarrMedia", "Progress POST attempt ${attempt + 1} failed: $lastFailure: ${error.message}", error)
                if (error !is java.io.IOException) break
            }
        }
        return lastFailure
    }

    private fun saveProgress(finished: Boolean) {
        val active = player ?: return
        val position = currentPosition()
        // HLS / transcoded streams may report TIME_UNSET for duration.
        // The server accepts duration_seconds=0 for unknown duration.
        val knownDuration = currentDuration().takeIf { it.isFinite() && it > 0.0 } ?: 0.0
        if (mediaId < 1 || server.isBlank() || !position.isFinite() ||
            (position < 1.0 && !finished)) return
        val safePosition = if (knownDuration > 0) position.coerceAtMost(knownDuration) else position
        val body = JSONObject().apply {
            put("media_id", mediaId)
            put("position_seconds", safePosition)
            put("duration_seconds", knownDuration)
            // A previously watched episode is *not* finished merely because
            // the server said it had been watched before this playback.
            put("completed", finished)
            put("replaying", replayingWatchedEpisode && !finished)
        }.toString()
        // Save locally BEFORE scheduling any network operation. A failed
        // connection or immediate Back no longer discards the resume point.
        rememberProgress(body)
        if (network.isShutdown) return
        network.execute {
            val failure = persistProgress(body)
            if (failure == null) {
                acknowledgeProgress(body)
            } else {
                // Network failures should not cover a still-playing video.
                // The next heartbeat (or next launch) retries the saved point.
                Log.w("YarrMedia", "Playback checkpoint queued locally: $failure")
            }
        }
    }

    override fun onPause() {
        // Persist before MainActivity resumes and flushes the pending POST.
        // onStop can occur after the browsing activity has already resumed.
        saveProgress(false)
        super.onPause()
    }

    override fun onStop() {
        visibleForPlayback = false
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        handler.removeCallbacks(checkpoint)
        handler.removeCallbacks(uiRefresh)
        handler.removeCallbacks(hideChrome)
        handler.removeCallbacks(scrubCommit)
        seekCommit?.let(handler::removeCallbacks)
        seekCommit = null
        if (::thumbnailPreview.isInitialized) thumbnailPreview.hide()
        saveProgress(false)
        player?.pause()
        super.onStop()
    }

    override fun onStart() {
        super.onStart()
        visibleForPlayback = true
        updatePlaybackScreenAwake()
        if (player != null) {
            handler.removeCallbacks(checkpoint)
            handler.postDelayed(checkpoint, 15_000)
            handler.removeCallbacks(uiRefresh)
            handler.post(uiRefresh)
        }
    }

    override fun onDestroy() {
        NavTrace.log { "PLAYER_DESTROY" }
        shuttingDown = true
        visibleForPlayback = false
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        seekCommit?.let(handler::removeCallbacks)
        seekCommit = null
        hlsStarts.invalidate()   // abandon any HLS start still in flight
        handler.removeCallbacks(scrubCommit)
        if (::thumbnailPreview.isInitialized) thumbnailPreview.dispose()
        handler.removeCallbacks(checkpoint)
        handler.removeCallbacks(uiRefresh)
        handler.removeCallbacks(hideChrome)
        player?.release()
        player = null
        session?.let { token ->
            network.execute {
                try { request("/api/stream/hls/$token", "DELETE") } catch (_: Exception) { }
            }
        }
        network.shutdown()
        lookups.shutdown()
        super.onDestroy()
    }
}
