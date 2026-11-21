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
                if (state == Player.STATE_ENDED) { save(); finish() }
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
        }
    }

    override fun onPause() { save(); player?.pause(); super.onPause() }

    override fun onDestroy() {
        player?.release()
        player = null
        super.onDestroy()
    }
}
