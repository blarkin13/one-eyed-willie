package studio.oneeyedwillie.tv

import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/** Plays a downloaded title from the phone, with no connection needed. */
class OfflinePlayerActivity : Activity() {
    private var player: ExoPlayer? = null
    private var itemId: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        itemId = intent.getStringExtra("id").orEmpty()
        val item = OfflineStore.get(this, itemId)
        val video = item?.let { OfflineStore.video(this, it) }
        if (item == null || video == null || !video.isFile) { finish(); return }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
        val subtitles = OfflineStore.subtitles(this, item).map { file ->
            MediaItem.SubtitleConfiguration.Builder(Uri.fromFile(file))
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLabel(file.nameWithoutExtension.substringAfter(' ').ifBlank { "Subtitles" })
                .setSelectionFlags(0)
                .build()
        }
        val media = MediaItem.Builder().setUri(Uri.fromFile(video)).setSubtitleConfigurations(subtitles).build()
        val exo = ExoPlayer.Builder(this).build()
        player = exo
        val view = PlayerView(this).apply {
            setBackgroundColor(Color.BLACK)
            this.player = exo
            setShowSubtitleButton(subtitles.isNotEmpty())
            setShowNextButton(false); setShowPreviousButton(false)
            controllerShowTimeoutMs = 2500
        }
        setContentView(view)
        exo.setMediaItem(media, OfflineLogic.resumeFrom(item.positionMs, item.durationMs))
        exo.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) { save(); offerNext() }
            }
        })
        exo.prepare()
        exo.playWhenReady = true
    }

    /** Remembers where playback is; sent to the server when the phone is back online. */
    private fun save() {
        val exo = player ?: return
        val duration = exo.duration.takeIf { it != C.TIME_UNSET && it > 0 } ?: return
        val position = if (exo.playbackState == Player.STATE_ENDED) duration else exo.currentPosition
        OfflineStore.update(this, itemId) {
            it.positionMs = position
            it.durationMs = duration
            if (OfflineLogic.watched(position, duration)) it.watched = true
            it.pendingSync = true
            it.playedAt = System.currentTimeMillis()
        }
    }

    /** At the end of an episode: play the next one if it's downloaded, or offer to download it. */
    private fun offerNext() {
        val item = OfflineStore.get(this, itemId) ?: return finish()
        OfflineNext.downloaded(this, item)?.let { next ->
            Sheet(this, "Play the next episode?", listOf(next.heading, next.subtitle, next.title).filter { it.isNotBlank() }.joinToString(" · "))
                .button("Play", primary = true) {
                    startActivity(android.content.Intent(this, OfflinePlayerActivity::class.java).putExtra("id", next.id))
                    finish()
                }
                .button("Not now") { finish() }
                .onClose { finish() }.show()
            return
        }
        Thread {
            val next = OfflineNext.fromServer(this, item)
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                if (next == null) { finish(); return@runOnUiThread }
                Sheet(this, "Download the next episode?", listOf(next.heading, next.subtitle, next.title).filter { it.isNotBlank() }.joinToString(" · "))
                    .text("Same quality (" + next.quality + ")" + (if (next.wifiOnly) ", on Wi-Fi." else "."))
                    .button("Download", primary = true) { OfflineStore.add(this, next); DownloadService.kick(this); finish() }
                    .button("Not now") { finish() }
                    .onClose { finish() }.show()
            }
        }.start()
    }

    override fun onPause() { save(); player?.pause(); super.onPause() }

    override fun onDestroy() {
        OfflineSync.later(this)
        player?.release()
        player = null
        super.onDestroy()
    }
}
