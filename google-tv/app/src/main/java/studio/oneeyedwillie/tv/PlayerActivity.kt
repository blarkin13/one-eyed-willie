package studio.oneeyedwillie.tv

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import androidx.activity.ComponentActivity
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class PlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private var mediaId = -1
    private var server = ""
    private val handler = Handler(Looper.getMainLooper())
    private val writer = Executors.newSingleThreadExecutor()
    private var completed = false

    private val checkpoint = object : Runnable {
        override fun run() {
            saveProgress(false)
            handler.postDelayed(this, 15_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra("url") ?: run { finish(); return }
        mediaId = intent.getIntExtra("media_id", -1)
        server = intent.getStringExtra("server") ?: ""
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
        player = ExoPlayer.Builder(this).build().also {
            it.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_ENDED) {
                        completed = true
                        saveProgress(true)
                    }
                }
            })
            it.setMediaItem(MediaItem.fromUri(url))
            it.prepare()
            it.playWhenReady = true
        }
        setContentView(PlayerView(this).apply {
            layoutParams = ViewGroup.LayoutParams(-1, -1)
            useController = true
            player = this@PlayerActivity.player
        })
        handler.postDelayed(checkpoint, 15_000)
    }

    private fun saveProgress(finished: Boolean) {
        val active = player ?: return
        val duration = active.duration
        val position = active.currentPosition
        if (mediaId < 1 || server.isBlank() || duration <= 0 ||
            duration == C.TIME_UNSET || position < 0) return
        val body = org.json.JSONObject().apply {
            put("media_id", mediaId)
            put("position_seconds", (position / 1000.0).coerceAtMost(duration / 1000.0))
            put("duration_seconds", duration / 1000.0)
            put("completed", finished || completed)
        }.toString()
        writer.execute {
            try {
                val connection = URL(server.trimEnd('/') + "/api/playback/progress")
                    .openConnection() as HttpURLConnection
                connection.requestMethod = "PUT"
                connection.connectTimeout = 4000
                connection.readTimeout = 4000
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                try {
                    connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    connection.responseCode
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                // An interrupted network connection must never interrupt playback.
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
        handler.removeCallbacks(checkpoint)
        player?.release()
        player = null
        writer.shutdown()
        super.onDestroy()
    }
}
