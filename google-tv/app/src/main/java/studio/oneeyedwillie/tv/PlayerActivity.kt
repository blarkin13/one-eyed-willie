package studio.oneeyedwillie.tv

import android.media.MediaCodecList
import android.media.MediaFormat
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.app.AlertDialog
import android.view.KeyEvent
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.SeekBar
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.concurrent.Executors

/**
 * Native TV playback follows the server player's playback negotiation:
 * /api/watch/{id}/status selects direct or HLS, with HLS fallback on decoder
 * or source errors. The raw playback stream alone cannot decode every file.
 */
class PlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private var mediaId = -1
    private var server = ""
    private var session: String? = null
    private var hlsMode = false
    private var hlsOffset = 0.0
    private var durationSeconds = 0.0
    private var completed = false
    private var shuttingDown = false
    private var fallbackStarted = false
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
    private var nextMediaId: Int? = null
    private var nextTitle = ""
    private var autoPlayNext = false
    private var pendingSeek = 0.0
    private var pendingSeekAction: Runnable? = null
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
    private val network = Executors.newSingleThreadExecutor()

    private val checkpoint = object : Runnable {
        override fun run() {
            saveProgress(false)
            handler.postDelayed(this, 15_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        mediaId = intent.getIntExtra("media_id", -1)
        server = intent.getStringExtra("server")?.trimEnd('/') ?: ""
        if (mediaId <= 0 || server.isBlank()) { finish(); return }
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY

        title = intent.getStringExtra("title")?.takeIf { it.isNotBlank() } ?: "Now Playing"
        val surface = FrameLayout(this)
        playerView = PlayerView(this).apply {
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            useController = false
        }
        surface.addView(playerView)
        chrome = createControls()
        surface.addView(chrome, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        thumbnailPreview = PlayerScrubPreview(this, server, mediaId)
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
        thumbnailPreview.start()
        player = ExoPlayer.Builder(this).build().also { exo ->
            playerView.player = exo
            exo.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_READY) {
                        message.visibility = View.GONE
                        scheduleHide()
                    } else if (state == Player.STATE_ENDED) {
                        completed = true
                        saveProgress(true)
                        chrome.visibility = View.VISIBLE
                        handler.removeCallbacks(hideChrome)
                        if (autoPlayNext && nextMediaId != null) showNextEpisode()
                    }
                }
                override fun onPlayerError(error: PlaybackException) {
                    if (!hlsMode && !fallbackStarted) {
                        fallbackStarted = true
                        val position = (exo.currentPosition / 1000.0).coerceAtLeast(0.0)
                        showMessage("Direct play unavailable. Preparing compatible stream…")
                        startHls(position)
                    } else {
                        showMessage("Playback failed: ${error.errorCodeName}. Check server transcoding and codecs.")
                    }
                }
            })
        }
        openMedia()
        loadNextEpisode()
        handler.post(uiRefresh)
        handler.postDelayed(checkpoint, 15_000)
    }


    private fun dp(value: Int) = (value * resources.displayMetrics.density + .5f).toInt()

    private fun iconControl(icon: Int, description: String, large: Boolean = false,
                            action: () -> Unit): ImageButton = ImageButton(this).apply {
        val dimension = dp(if (large) 64 else 54)
        layoutParams = LinearLayout.LayoutParams(dimension, dimension)
        setImageResource(icon)
        contentDescription = description
        tooltipText = description
        scaleType = ImageButton.ScaleType.CENTER_INSIDE
        setPadding(dp(if (large) 15 else 14), dp(if (large) 15 else 14),
                   dp(if (large) 15 else 14), dp(if (large) 15 else 14))
        isFocusable = true
        isFocusableInTouchMode = true
        val idle = GradientDrawable().apply {
            cornerRadius = dp(40).toFloat()
            setColor(if (large) 0x2AF4EFE4 else Color.TRANSPARENT)
        }
        background = idle
        setOnFocusChangeListener { button, hasFocus ->
            button.background = GradientDrawable().apply {
                cornerRadius = dp(40).toFloat()
                setColor(if (hasFocus) 0x48F4EFE4 else if (large) 0x2AF4EFE4 else Color.TRANSPARENT)
                if (hasFocus) setStroke(dp(2), 0xFFF4EFE4.toInt())
            }
            button.animate().scaleX(if (hasFocus) 1.10f else 1f)
                .scaleY(if (hasFocus) 1.10f else 1f).setDuration(110).start()
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
            setPadding(dp(32), dp(18), dp(32), 0)
        }
        val heading = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
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
            setPadding(dp(18), dp(64), dp(18), dp(23))
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
            progressTintList = android.content.res.ColorStateList.valueOf(0xFFF4EFE4.toInt())
            thumbTintList = android.content.res.ColorStateList.valueOf(0xFFF4EFE4.toInt())
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
            if (nextMediaId != null) showNextEpisode() else showMessage("No next episode available")
        })
        extras.addView(iconControl(R.drawable.ic_player_more, "More playback options") {
            showPlaybackMenu()
        })
        toolbar.addView(extras)
        bottom.addView(toolbar)
        root.addView(bottom)
        return root
    }

    private fun showPlaybackMenu() {
        val labels = arrayOf(
            if (completed) "Mark as unwatched" else "Mark as watched",
            "Playback details",
            "Play from beginning"
        )
        AlertDialog.Builder(this).setTitle("Playback options")
            .setItems(labels) { _, choice ->
                when (choice) {
                    0 -> toggleWatched()
                    1 -> showDiagnostics()
                    2 -> seekTo(0.0)
                }
                showChrome()
            }
            .setNegativeButton("Close", null).show()
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
        if(!timeline.isPressed && !scrubbing && duration>0)
            timeline.progress = (position/duration*1000).toInt().coerceIn(0,1000)
        elapsed.text = fmt(position)
        totalTime.text = fmt(duration)
        playButton.setImageResource(
            if (player?.isPlaying == true) R.drawable.ic_player_pause else R.drawable.ic_player_play
        )
    }

    private fun seekBy(delta: Double) {
        val base = if (pendingSeekAction != null) pendingSeek else currentPosition()
        seekTo(base + delta)
    }

    private fun seekTo(seconds: Double) {
        pendingSeek = seconds.coerceIn(0.0, if (currentDuration() > 0) currentDuration() else 1e7)
        showScrubAt(pendingSeek)
        thumbnailPreview.hideSoon()
        pendingSeekAction?.let(handler::removeCallbacks)
        val action = Runnable {
            pendingSeekAction = null
            val target = pendingSeek
            if (hlsMode) {
                val relative = target - hlsOffset
                val p = player
                val buffered = (p?.bufferedPosition ?: 0L) / 1000.0
                if (relative >= 0 && relative < buffered - 0.3 &&
                    p?.isCurrentMediaItemSeekable == true) {
                    p.seekTo((relative * 1000).toLong())
                } else {
                    val previous = session
                    session = null
                    p?.stop()
                    network.execute {
                        previous?.let {
                            try { request("/api/stream/hls/$it", "DELETE") }
                            catch (_: Exception) {}
                        }
                        startHlsOnNetwork(target)
                    }
                }
            } else player?.seekTo((target * 1000).toLong())
            showChrome()
        }
        pendingSeekAction = action
        handler.postDelayed(action, 220)
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
            "\nState: "+(p?.playbackState ?: -1)+
            "\nPosition: "+fmt(currentPosition())+
            "\nServer: "+server+
            "\nSession: "+(if(session!=null)"Active" else "None")
        AlertDialog.Builder(this).setTitle("Playback diagnostics")
            .setMessage(messageText).setPositiveButton("Close",null).show()
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
                    handler.post {completed=next;showMessage(if(next)"Marked watched" else "Marked unwatched")}
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

    /** Existing tracks plus the same OpenSubtitles workflow as server/player.js. */
    private fun showCaptions() {
        showChrome()
        network.execute {
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
                    AlertDialog.Builder(this).setTitle("Closed Captions")
                        .setSingleChoiceItems(
                            labels.toTypedArray(), ids.indexOf(selectedCaption).coerceAtLeast(0)
                        ) { dialog, index ->
                            dialog.dismiss()
                            if (index == labels.lastIndex) {
                                chooseSubtitleLanguage()
                            } else {
                                selectedCaption = ids[index]
                                applyCaption()
                                showChrome()
                            }
                        }
                        .setNegativeButton("Cancel", null).show()
                }
            } catch (error: Exception) {
                handler.post { if (!shuttingDown) showMessage("Subtitles unavailable: ${error.message}") }
            }
        }
    }

    private fun chooseSubtitleLanguage() {
        showChrome()
        AlertDialog.Builder(this).setTitle("Search subtitle language")
            .setItems(subtitleLanguages.map { it.first }.toTypedArray()) { _, index ->
                searchOpenSubtitles(subtitleLanguages[index].second)
            }
            .setNegativeButton("Cancel", null).show()
    }

    private fun searchOpenSubtitles(language: String) {
        if (shuttingDown || subtitleLanguages.none { it.second == language }) return
        showMessage("Searching OpenSubtitles…")
        network.execute {
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
                    AlertDialog.Builder(this).setTitle("OpenSubtitles results")
                        .setItems(names.toTypedArray()) { _, selected ->
                            val (id, lang) = options[selected]
                            downloadSubtitle(id, lang)
                        }
                        .setNegativeButton("Cancel", null)
                        .setNeutralButton("Change language") { _, _ -> chooseSubtitleLanguage() }
                        .show()
                }
            } catch (error: Exception) {
                handler.post { if (!shuttingDown) showMessage("Subtitle search failed: ${error.message}") }
            }
        }
    }

    private fun downloadSubtitle(fileId: Int, language: String) {
        if (fileId <= 0 || subtitleLanguages.none { it.second == language } || shuttingDown) return
        showMessage("Downloading subtitle…")
        network.execute {
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
                .setLanguage("en")
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
        network.execute {
            try {
                val data=request("/api/tv/next?media_id=$mediaId")
                val next=data.optJSONObject("next")
                val settings=request("/api/settings/playback")
                handler.post {
                    autoPlayNext=settings.optBoolean("auto_play_next",false)
                    if(next!=null){
                        nextMediaId=next.optInt("media_id").takeIf{it>0}
                        nextTitle=next.optString("title","Next Episode")
                    }
                }
            }catch(_:Exception){}
        }
    }

    private fun showNextEpisode() {
        val next=nextMediaId ?: return
        AlertDialog.Builder(this).setTitle("Up next")
            .setMessage(nextTitle)
            .setPositiveButton("Play Next"){_,_->
                startActivity(intent.putExtra("media_id",next).putExtra("title",nextTitle))
                finish()
            }.setNegativeButton("Cancel",null).show()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if(event.keyCode==KeyEvent.KEYCODE_BACK)return super.dispatchKeyEvent(event)
        if(event.action==KeyEvent.ACTION_DOWN && ::chrome.isInitialized &&
            chrome.visibility!=View.VISIBLE){
            showChrome()
            return true
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
                val info = request("/api/watch/$mediaId/status")
                val resume = if (intent.getBooleanExtra("restart", false) || info.optBoolean("watched", false)) 0.0
                    else info.optDouble("position_seconds", 0.0).coerceAtLeast(0.0)
                durationSeconds = info.optDouble("duration_seconds", 0.0)
                completed = info.optBoolean("watched",false)
                val mode = info.optString("mode", "")
                val actual = info.optJSONObject("media")
                val direct = if (actual != null && actual.optString("video_codec").isNotBlank())
                    canDirectPlay(actual, info.optString("extension", ""))
                    else mode == "direct"
                val streamUrl = info.optString("stream_url", "")
                if (direct && streamUrl.isNotBlank()) {
                    handler.post {
                        if (!shuttingDown) {
                            hlsMode = false
                            player?.setMediaItem(MediaItem.fromUri(resolveUrl(streamUrl)))
                            player?.prepare()
                            player?.seekTo((resume * 1000).toLong())
                            player?.playWhenReady = true
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

    private fun startHls(position: Double) {
        if (shuttingDown) return
        player?.stop()
        network.execute { startHlsOnNetwork(position) }
    }

    private fun startHlsOnNetwork(position: Double) {
        if (shuttingDown) return
        var createdToken: String? = null
        try {
            val start = position.coerceAtLeast(0.0)
            handler.post { if (!shuttingDown) showMessage("Preparing compatible HLS stream…") }
            val created = request("/api/stream/hls/start/$mediaId?start=$start", "POST")
            val token = created.getString("session")
            createdToken = token
            if (shuttingDown) {
                try { request("/api/stream/hls/$token", "DELETE") } catch (_: Exception) {}
                return
            }
            session = token
            var ready: JSONObject? = null
            for (attempt in 0 until 80) {
                if (shuttingDown) return
                Thread.sleep(400)
                val candidate = request("/api/stream/hls/$token/status")
                if (candidate.optBoolean("ready")) { ready = candidate; break }
            }
            val playlist = ready?.optString("playlist").orEmpty()
            if (playlist.isBlank()) throw IllegalStateException("HLS transcoder did not become ready")
            handler.post {
                if (shuttingDown) return@post
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
            }
        } catch (error: Exception) {
            createdToken?.let { token ->
                try { request("/api/stream/hls/$token", "DELETE") }
                catch (_: Exception) {}
                if (session == token) session = null
            }
            handler.post {
                if (!shuttingDown) showMessage("Compatible playback failed: ${error.message}")
            }
        }
    }

    private fun saveProgress(finished: Boolean) {
        val active = player ?: return
        val position = (active.currentPosition / 1000.0).coerceAtLeast(0.0) +
            (if (hlsMode) hlsOffset else 0.0)
        val duration = if (durationSeconds > 0) durationSeconds else active.duration / 1000.0
        if (mediaId < 1 || server.isBlank() || !duration.isFinite() ||
            duration <= 0 || position < 0) return
        val body = JSONObject().apply {
            put("media_id", mediaId)
            put("position_seconds", position.coerceAtMost(duration))
            put("duration_seconds", duration)
            put("completed", finished || completed)
        }.toString()
        network.execute {
            try {
                val connection = URL(resolveUrl("/api/playback/progress"))
                    .openConnection() as HttpURLConnection
                try {
                    connection.requestMethod = "PUT"
                    connection.connectTimeout = 4000
                    connection.readTimeout = 4000
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    connection.responseCode
                } finally { connection.disconnect() }
            } catch (_: Exception) {
                // Progress failures must not interrupt playback.
            }
        }
    }

    override fun onStop() {
        handler.removeCallbacks(checkpoint)
        handler.removeCallbacks(uiRefresh)
        handler.removeCallbacks(hideChrome)
        handler.removeCallbacks(scrubCommit)
        if (::thumbnailPreview.isInitialized) thumbnailPreview.hide()
        saveProgress(false)
        player?.pause()
        super.onStop()
    }

    override fun onStart() {
        super.onStart()
        if (player != null) {
            handler.removeCallbacks(checkpoint)
            handler.postDelayed(checkpoint, 15_000)
            handler.removeCallbacks(uiRefresh)
            handler.post(uiRefresh)
        }
    }

    override fun onDestroy() {
        shuttingDown = true
        pendingSeekAction?.let(handler::removeCallbacks)
        pendingSeekAction = null
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
        super.onDestroy()
    }
}
