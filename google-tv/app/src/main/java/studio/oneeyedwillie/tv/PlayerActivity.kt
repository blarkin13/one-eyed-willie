package studio.oneeyedwillie.tv

import android.graphics.Color
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

        val surface = FrameLayout(this)
        val view = PlayerView(this).apply {
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            useController = true
        }
        message = TextView(this).apply {
            text = "Preparing video…"
            textSize = 17f
            setTextColor(Color.WHITE)
            setBackgroundColor(0xDD101820.toInt())
            setPadding(24, 16, 24, 16)
            gravity = Gravity.CENTER
        }
        surface.addView(view)
        surface.addView(message, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM
        ))
        setContentView(surface)

        player = ExoPlayer.Builder(this).build().also { exo ->
            view.player = exo
            exo.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_READY) {
                        message.visibility = View.GONE
                    } else if (state == Player.STATE_ENDED) {
                        completed = true
                        saveProgress(true)
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
        handler.postDelayed(checkpoint, 15_000)
    }

    private fun showMessage(text: String) {
        message.text = text
        message.visibility = View.VISIBLE
    }

    private fun resolveUrl(path: String): String =
        URI(server + "/").resolve(path).toString()

    private fun request(path: String, method: String = "GET"): JSONObject {
        val connection = URL(resolveUrl(path)).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 7000
            connection.readTimeout = 10000
            connection.setRequestProperty("Accept", "application/json")
            if (method == "POST") {
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(0)
                connection.outputStream.use { }
            }
            val code = connection.responseCode
            val body = (if (code in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw IllegalStateException(
                "Server returned HTTP $code for $path"
            )
            return JSONObject(body)
        } finally {
            connection.disconnect()
        }
    }

    private fun openMedia() {
        network.execute {
            try {
                val info = request("/api/watch/$mediaId/status")
                val resume = if (info.optBoolean("watched", false)) 0.0
                    else info.optDouble("position_seconds", 0.0).coerceAtLeast(0.0)
                durationSeconds = info.optDouble("duration_seconds", 0.0)
                val mode = info.optString("mode", "")
                val streamUrl = info.optString("stream_url", "")
                if (mode == "direct" && streamUrl.isNotBlank()) {
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
        saveProgress(false)
        player?.pause()
        super.onStop()
    }

    override fun onStart() {
        super.onStart()
        if (player != null) {
            handler.removeCallbacks(checkpoint)
            handler.postDelayed(checkpoint, 15_000)
        }
    }

    override fun onDestroy() {
        shuttingDown = true
        handler.removeCallbacks(checkpoint)
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
