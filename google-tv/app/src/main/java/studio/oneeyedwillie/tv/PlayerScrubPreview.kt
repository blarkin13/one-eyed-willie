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
    private val mediaId: Int,
    private val videoDuration: () -> Double
) {
    private data class Frame(val time: Double, val url: String)
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private val cache = object : LruCache<String, Bitmap>(12 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val framePattern = Regex("^/api/maintenance/preview/$mediaId/\\d{3}\\.jpg$")
    private var frames: List<Frame> = emptyList()
    private var currentUrl: String? = null
    private var lastPosition = 0.0
    private var desiredUrl: String? = null
    private var disposed = false
    private var refreshCount = 0
    private val inFlight = HashSet<String>()
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
        val nearestIndex = frames.indices.minByOrNull { i ->
            val frame = frames[i]
            val time = if (frame.time < 0) -frame.time * videoDuration() else frame.time
            abs(time - seconds)
        } ?: return
        val nearest = frames[nearestIndex]
        desiredUrl = nearest.url
        prefetchAround(nearestIndex)
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
                RemoteSession.authorize(activity.applicationContext, connection)
                connection.connectTimeout = 4000
                connection.readTimeout = 6000
                try {
                    if (connection.responseCode !in 200..299) return@execute
                    val data = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                    val arr = data.optJSONArray("frames")
                    val incoming = mutableListOf<Frame>()
                    if (arr != null) {
                        for (i in 0 until arr.length()) {
                            val frame = arr.optJSONObject(i) ?: continue
                            val url = frame.optString("url")
                            if (!framePattern.matches(url)) continue
                            incoming.add(Frame(frame.optDouble("time_seconds", 0.0), url))
                        }
                    } else {
                        // Older servers provide only six images without timestamps.
                        val legacy = data.optJSONArray("images")
                        if (legacy != null) for (i in 0 until legacy.length()) {
                            val url = legacy.optString(i)
                            if (framePattern.matches(url)) {
                                incoming.add(Frame(-((i + 1).toDouble() / (legacy.length() + 1)), url))
                            }
                        }
                    }
                    val generating = data.optBoolean("generating", false)
                    handler.post {
                        if (disposed) return@post
                        if (!data.optBoolean("enabled", true)) {
                            placeholder.text = "Previews disabled in server settings"
                        } else if (incoming.isEmpty()) {
                            placeholder.text = "Preparing thumbnails…"
                        }
                        // Detailed frames arrive coarse-to-fine, so order by time for neighbour lookups.
                        frames = incoming.sortedBy { it.time }
                        if (view.visibility == View.VISIBLE) {
                            show(lastPosition)
                            hideSoon()
                        }
                        val expected = data.optInt("total_frames", 24)
                        val remaining = incoming.size < expected &&
                            data.optDouble("duration_seconds", 0.0) > 15
                        // Dense sets take minutes to build: poll quickly at first, then back off.
                        if ((generating || remaining) && refreshCount++ < 120) {
                            val delay = if (refreshCount < 10) 3000L else 12000L
                            handler.postDelayed({ if (!disposed) refresh() }, delay)
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

    /** Warm the cache for the thumbnails on either side so single steps don't flash a placeholder. */
    private fun prefetchAround(index: Int) {
        for (neighbour in intArrayOf(index + 1, index - 1, index + 2, index - 2)) {
            val url = frames.getOrNull(neighbour)?.url ?: continue
            if (cache.get(url) == null && inFlight.add(url)) fetchImage(url, prefetch = true)
        }
    }

    private fun fetchImage(url: String, prefetch: Boolean = false) {
        if (disposed) return
        if (!prefetch && !inFlight.add(url)) return
        worker.execute {
            var bitmap: Bitmap? = null
            try {
                if (!framePattern.matches(url)) return@execute
                val conn = URL(origin + url).openConnection() as HttpURLConnection
                RemoteSession.authorize(activity.applicationContext, conn)
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
                inFlight.remove(url)
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
