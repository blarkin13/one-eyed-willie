package studio.oneeyedwillie.tv

import android.os.Bundle
import android.view.ViewGroup
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

class PlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private var mediaId: Int = -1
    private var server: String = ""
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra("url") ?: run { finish(); return }
        mediaId = intent.getIntExtra("media_id", -1)
        server = intent.getStringExtra("server") ?: ""
        window.decorView.systemUiVisibility = (
            android.view.View.SYSTEM_UI_FLAG_FULLSCREEN or
            android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY)
        player = ExoPlayer.Builder(this).build().also {
            it.setMediaItem(MediaItem.fromUri(url))
            it.prepare()
            it.playWhenReady = true
        }
        setContentView(PlayerView(this).apply {
            layoutParams = ViewGroup.LayoutParams(-1, -1)
            useController = true
            player = this@PlayerActivity.player
        })
    }
    override fun onStop() {
        player?.pause()
        super.onStop()
    }
    override fun onDestroy() {
        player?.release()
        player = null
        super.onDestroy()
    }
}
