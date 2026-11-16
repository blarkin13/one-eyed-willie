package studio.oneeyedwillie.tv

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.util.LruCache
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * Remote-friendly thumbnail preview. The source remains the server's validated
 * indexed video. Preview JPEGs are fetched only from the local media endpoint.
 * No per-keypress FFmpeg jobs or decoded frames on the TV's UI thread.
 */
internal class PlayerScrubPreview(
    private val activity: Activity,
    private val origin: String,
    private val mediaId: Int
) {
    private data class Frame(val time: Double, val url: String)
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private val cache = object : LruCache<String, Bitmap>(6 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val framePattern = Regex("^/api/maintenance/preview/$mediaId/0(?:0[0-9]|1[0-9]|2[0-3])\\.jpg$")
    private var frames: List<Frame> = emptyList()
    private var currentUrl: String? = null
    private var lastPosition = 0.0
    private var desiredUrl: String? = null
    private var disposed = false
    private var refreshCount = 0
    private val hideAction = Runnable { view.visibility = View.GONE }
    private var imageAction: Runnable? = null

    private fun dp(v: Int) = (v * activity.resources.displayMetrics.density + 0.5f).toInt()

    private val image = ImageView(activity).apply {
        scaleType = ImageView.ScaleType.CENTER_CROP
        setBackgroundColor(Color.rgb(24, 30, 37))
    }
    private val placeholder = TextView(activity).apply {
        text = "Preparing thumbnails…"
        textSize = 13f
        setTextColor(0xFFD7D8D9.toInt())
        gravity = Gravity.CENTER
    }
    private val timestamp = TextView(activity).apply {
        textSize = 17f
        setTextColor(0xFFF4EFE4.toInt())
        gravity = Gravity.CENTER
        typeface = android.graphics.Typeface.DEFAULT_BOLD
        setPadding(0, dp(7), 0, dp(2))
    }

    val view = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(7), dp(7), dp(7), dp(7))
        background = GradientDrawable().apply {
            cornerRadius = dp(15).toFloat()
            setColor(0xEC12181F.toInt())
            setStroke(dp(1), 0xA0F4EFE4.toInt())
        }
        elevation = dp(12).toFloat()
        visibility = View.GONE
        val imageFrame = FrameLayout(activity)
        imageFrame.addView(image, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        imageFrame.addView(placeholder, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        addView(imageFrame, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(140)))
        addView(timestamp, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(34)))
    }

    fun start() = refresh()

    fun show(seconds: Double) {
        if (disposed) return
        handler.removeCallbacks(hideAction)
        lastPosition = seconds
        view.visibility = View.VISIBLE
        val sec = seconds.coerceAtLeast(0.0).toLong()
        timestamp.text = if (sec >= 3600)
            "%d:%02d:%02d".format(sec / 3600, (sec % 3600) / 60, sec % 60)
        else "%d:%02d".format(sec / 60, sec % 60)
        if (frames.isEmpty()) {
            placeholder.visibility = View.VISIBLE
            image.setImageDrawable(null)
            currentUrl = null
            return
        }
        val nearest = frames.minByOrNull { abs(it.time - seconds) } ?: return
        desiredUrl = nearest.url
        if (currentUrl == nearest.url) return
        cache.get(nearest.url)?.let {
            image.setImageBitmap(it)
            currentUrl = nearest.url
            placeholder.visibility = View.GONE
            return
        }
        imageAction?.let(handler::removeCallbacks)
        currentUrl = null
        image.setImageDrawable(null)
        placeholder.text = "Loading thumbnail…"
        placeholder.visibility = View.VISIBLE
        val requestedUrl = nearest.url
        val action = Runnable { fetchImage(requestedUrl) }
        imageAction = action
        handler.postDelayed(action, 100) // Rapid remote repeats request only the final frame
    }

    fun hideSoon() {
        if (disposed) return
        handler.removeCallbacks(hideAction)
        handler.postDelayed(hideAction, 1400)
    }

    fun hide() {
        handler.removeCallbacks(hideAction)
        view.visibility = View.GONE
    }

    private fun refresh() {
        if (disposed) return
        worker.execute {
            try {
                val connection = URL("$origin/api/maintenance/preview/$mediaId")
                    .openConnection() as HttpURLConnection
                connection.connectTimeout = 4000
                connection.readTimeout = 6000
                try {
                    if (connection.responseCode !in 200..299) return@execute
                    val data = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                    val arr = data.optJSONArray("frames")
                    val incoming = mutableListOf<Frame>()
                    if (arr != null) for (i in 0 until arr.length()) {
                        val frame = arr.optJSONObject(i) ?: continue
                        val url = frame.optString("url")
                        if (!framePattern.matches(url)) continue
                        incoming.add(Frame(frame.optDouble("time_seconds", 0.0), url))
                    }
                    val generating = data.optBoolean("generating", false)
                    handler.post {
                        if (disposed) return@post
                        frames = incoming
                        if (view.visibility == View.VISIBLE) {
                            show(lastPosition)
                            hideSoon()
                        }
                        val remaining = incoming.size < 24 &&
                            data.optDouble("duration_seconds", 0.0) > 15
                        if ((generating || remaining) && refreshCount++ < 30) {
                            handler.postDelayed({ if (!disposed) refresh() }, 3000)
                        }
                    }
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                // Thumbnails are optional; never interrupt playback.
            }
        }
    }

    private fun fetchImage(url: String) {
        if (disposed) return
        worker.execute {
            var bitmap: Bitmap? = null
            try {
                if (!framePattern.matches(url)) return@execute
                val conn = URL(origin + url).openConnection() as HttpURLConnection
                conn.instanceFollowRedirects = false
                conn.connectTimeout = 3500
                conn.readTimeout = 6000
                try {
                    if (conn.responseCode == 200 && conn.contentLength <= 800000) {
                        bitmap = BitmapFactory.decodeStream(conn.inputStream, null,
                            BitmapFactory.Options().apply {
                                inPreferredConfig = Bitmap.Config.RGB_565
                            })
                    }
                } finally {
                    conn.disconnect()
                }
            } catch (_: Exception) {
                // Missing or still-generating previews are not playback errors.
            }
            val result = bitmap
            handler.post {
                if (disposed) return@post
                if (result != null) cache.put(url, result)
                if (desiredUrl == url && result != null) {
                    image.setImageBitmap(result)
                    placeholder.visibility = View.GONE
                    currentUrl = url
                }
            }
        }
    }

    fun dispose() {
        disposed = true
        handler.removeCallbacks(hideAction)
        imageAction?.let(handler::removeCallbacks)
        worker.shutdownNow()
        cache.evictAll()
    }
}
