package studio.oneeyedwillie.tv

import android.media.MediaCodecList
import android.media.MediaFormat
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.app.AlertDialog
import android.view.KeyEvent
import android.widget.Button
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
    private lateinit var playButton: Button
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
    private val hideChrome = Runnable { if (player?.isPlaying == true) chrome.visibility = View.GONE }
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

    private fun control(label: String, action: () -> Unit) = Button(this).apply {
        text = label
        textSize = 17f
        isAllCaps = false
        setTextColor(Color.WHITE)
        background = GradientDrawable().apply {
            cornerRadius = dp(8).toFloat()
            setColor(Color.TRANSPARENT)
        }
        setOnFocusChangeListener { _, focused ->
            background = GradientDrawable().apply {
                cornerRadius = dp(8).toFloat()
                setColor(if(focused) 0x664A6580 else Color.TRANSPARENT)
            }
        }
        setPadding(dp(11), dp(6), dp(11), dp(6))
        minHeight = dp(46)
        setOnClickListener { action(); scheduleHide() }
    }

    private fun createControls(): LinearLayout {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(35), dp(25), dp(35), dp(24))
            setBackgroundColor(Color.TRANSPARENT)
        }
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(0x99060D16.toInt())
        }
        top.addView(control("‹") { finish() }.apply { contentDescription = "Back to library" })
        titleText = TextView(this).apply {
            text = title
            setTextColor(Color.WHITE)
            textSize = 19f
            setPadding(dp(15), 0, 0, 0)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        top.addView(titleText, LinearLayout.LayoutParams(0, dp(50), 1f).apply {
            gravity = Gravity.CENTER_VERTICAL
        })
        root.addView(top)
        root.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f))
        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(13), dp(16), dp(12))
            setBackgroundColor(0xDD060D16.toInt())
        }
        val progressRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        elapsed = TextView(this).apply { text = "0:00";setTextColor(Color.WHITE);textSize=14f }
        totalTime = TextView(this).apply { text = "0:00";setTextColor(Color.WHITE);textSize=14f }
        timeline = SeekBar(this).apply {
            max = 1000
            progressTintList = android.content.res.ColorStateList.valueOf(0xFFA3D4FF.toInt())
            thumbTintList = android.content.res.ColorStateList.valueOf(0xFFD7E8FC.toInt())
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                private var dragging = false
                override fun onStartTrackingTouch(bar: SeekBar?) { dragging=true;showChrome() }
                override fun onStopTrackingTouch(bar: SeekBar?) {
                    dragging=false
                    val duration = currentDuration()
                    if(duration>0) seekTo(duration*(bar?.progress ?: 0)/1000.0)
                }
                override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                    if(fromUser && !dragging) {
                        val duration = currentDuration()
                        if(duration>0) seekTo(duration*progress/1000.0)
                    }
                }
            })
        }
        progressRow.addView(elapsed)
        progressRow.addView(timeline, LinearLayout.LayoutParams(0, dp(40), 1f))
        progressRow.addView(totalTime)
        bottom.addView(progressRow)
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        playButton = control("❚❚") {
            val p = player
            if(p?.isPlaying==true) p.pause() else p?.play()
            refreshControls()
        }
        playButton.contentDescription = "Play or pause"
        buttons.addView(playButton)
        buttons.addView(control("↶ 10") { seekTo(currentPosition()-10) }.apply { contentDescription = "Rewind ten seconds" })
        buttons.addView(control("10 ↷") { seekTo(currentPosition()+10) }.apply { contentDescription = "Forward ten seconds" })
        buttons.addView(control("CC") { showCaptions() })
        buttons.addView(control("✓") { toggleWatched() }.apply { contentDescription = "Mark watched or unwatched" })
        buttons.addView(control("ⓘ") { showDiagnostics() }.apply { contentDescription = "Playback diagnostics" })
        bottom.addView(buttons)
        root.addView(bottom)
        return root
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
        if(!timeline.isPressed && !timeline.hasFocus() && duration>0)
            timeline.progress = (position/duration*1000).toInt().coerceIn(0,1000)
        elapsed.text = fmt(position)
        totalTime.text = fmt(duration)
        playButton.text = if(player?.isPlaying==true)"❚❚" else "▶"
    }

    private fun seekTo(seconds: Double) {
        pendingSeek = seconds.coerceIn(0.0, if (currentDuration() > 0) currentDuration() else 1e7)
        pendingSeekAction?.let(handler::removeCallbacks)
        val action = Runnable {
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
        try {
            val start = position.coerceAtLeast(0.0)
            handler.post { if (!shuttingDown) showMessage("Preparing compatible HLS stream…") }
            val created = request("/api/stream/hls/start/$mediaId?start=$start", "POST")
            val token = created.getString("session")
            if (shuttingDown) return
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
                player?.playWhenReady = true
            }
        } catch (error: Exception) {
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
