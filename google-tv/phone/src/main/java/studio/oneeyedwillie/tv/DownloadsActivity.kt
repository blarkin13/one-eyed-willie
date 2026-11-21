package studio.oneeyedwillie.tv

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView

/** Everything downloaded to this phone. Works with no connection at all. */
class DownloadsActivity : Activity() {
    private lateinit var list: LinearLayout
    private lateinit var summary: TextView
    private val refresh: () -> Unit = { render() }

    private fun dp(v: Int) = (v * resources.displayMetrics.density + .5f).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = BG
        window.navigationBarColor = BG
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(BG) }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), dp(10), dp(16), dp(6))
        }
        header.addView(TextView(this).apply {
            text = "←"; textSize = 26f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
            contentDescription = "Back"; isClickable = true
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        header.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(this@DownloadsActivity).apply {
                text = "Downloads"; textSize = 24f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
            })
            summary = TextView(this@DownloadsActivity).apply { textSize = 13f; setTextColor(MUTED) }
            addView(summary)
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dp(6) })
        column.addView(header)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(4), dp(16), dp(24)) }
        column.addView(ScrollView(this).apply { addView(list) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(column)
        if (android.os.Build.VERSION.SDK_INT >= 30) column.setOnApplyWindowInsetsListener { v, insets ->
            val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
    }

    override fun onStart() {
        super.onStart()
        OfflineStore.observe(refresh)
        render()
        DownloadService.kick(this)
        OfflineSync.later(this)
    }

    override fun onStop() { OfflineStore.stopObserving(refresh); super.onStop() }

    private fun render() {
        val items = OfflineStore.all(this).sortedByDescending { it.addedAt }
        val total = items.filter { it.status == "done" }.sumOf { it.bytes }
        summary.text = if (items.isEmpty()) "" else
            items.size.toString() + (if (items.size == 1) " title" else " titles") +
                (if (total > 0) " · " + OfflineLogic.sizeLabel(total) + " on this phone" else "")
        list.removeAllViews()
        if (items.isEmpty()) {
            list.addView(TextView(this).apply {
                text = "Nothing downloaded yet.\n\nOn a movie or episode, tap the download button to watch it later without a connection."
                textSize = 15f; setTextColor(MUTED); gravity = Gravity.CENTER
                setPadding(dp(24), dp(80), dp(24), 0)
            })
            return
        }
        items.forEach { list.addView(row(it)) }
    }

    private fun row(item: OfflineItem): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(8))
            val ripple = TypedValue().also { theme.resolveAttribute(android.R.attr.selectableItemBackground, it, true) }.resourceId
            if (ripple != 0) setBackgroundResource(ripple)
            isClickable = true
            setOnClickListener { open(item) }
        }
        val poster = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = GradientDrawable().apply { setColor(0xFF1C1F24.toInt()); cornerRadius = dp(6).toFloat() }
            clipToOutline = true
            val file = OfflineStore.poster(this@DownloadsActivity, item)
            if (file.isFile) {
                val options = BitmapFactory.Options().apply { inSampleSize = 2 }
                BitmapFactory.decodeFile(file.path, options)?.let { setImageBitmap(it) }
            }
        }
        row.addView(poster, LinearLayout.LayoutParams(dp(62), dp(92)))
        val text = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), 0, dp(6), 0) }
        text.addView(TextView(this).apply {
            this.text = item.heading; textSize = 16f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
            maxLines = 2
        })
        if (item.detail.isNotBlank()) text.addView(TextView(this).apply {
            this.text = item.detail; textSize = 13f; setTextColor(0xFFD0D4DA.toInt()); maxLines = 2
        })
        val line = OfflineLogic.statusLine(item.status, item.progress, item.bytes, item.error) +
            (if (item.status == "done" && item.watched) " · Watched" else "")
        text.addView(TextView(this).apply {
            this.text = line; textSize = 12f
            setTextColor(if (item.status == "failed") 0xFFFF8A80.toInt() else MUTED)
            setPadding(0, dp(3), 0, 0)
        })
        if (item.status in setOf("preparing", "downloading")) text.addView(
            ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = 1000; progress = (item.progress * 1000).toInt().coerceIn(0, 1000)
            }, LinearLayout.LayoutParams(-1, dp(10)).apply { topMargin = dp(5) })
        if (item.status == "done" && item.durationMs > 0 && !item.watched && item.positionMs > 30_000) text.addView(
            ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = 1000; progress = (1000L * item.positionMs / item.durationMs).toInt().coerceIn(0, 1000)
            }, LinearLayout.LayoutParams(-1, dp(6)).apply { topMargin = dp(5) })
        row.addView(text, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(ImageButton(this).apply {
            setImageResource(android.R.drawable.ic_menu_delete)
            setColorFilter(MUTED)
            background = null
            contentDescription = "Remove download"
            setOnClickListener { confirmRemove(item) }
        }, LinearLayout.LayoutParams(dp(44), dp(44)))
        return row
    }

    private fun open(item: OfflineItem) {
        when (item.status) {
            "done" -> startActivity(Intent(this, OfflinePlayerActivity::class.java).putExtra("id", item.id))
            "failed", "paused", "waiting_wifi" -> Sheet(this, item.heading, item.detail)
                .text(OfflineLogic.statusLine(item.status, item.progress, item.bytes, item.error))
                .button("Try again", primary = true) {
                    OfflineStore.update(this, item.id) { it.status = "waiting"; it.error = null }
                    DownloadService.kick(this)
                }
                .apply { if (item.status == "waiting_wifi") button("Download on mobile data now") {
                    replaceWifiOnly(item); DownloadService.kick(this@DownloadsActivity) } }
                .button("Close").show()
            else -> {}
        }
    }

    /** Lets a download that's waiting for Wi-Fi go ahead on mobile data. */
    private fun replaceWifiOnly(item: OfflineItem) {
        OfflineStore.add(this, OfflineItem(item.id, item.key, item.mediaId, item.kind, item.title, item.subtitle,
            item.showTitle, item.season, item.episode, item.posterUrl, item.origin, item.remote, item.serverId,
            item.quality, wifiOnly = false, status = "waiting", progress = item.progress, jobId = item.jobId,
            positionMs = item.positionMs, durationMs = item.durationMs, watched = item.watched,
            pendingSync = item.pendingSync, addedAt = item.addedAt))
    }

    private fun confirmRemove(item: OfflineItem) {
        Sheet(this, "Remove download?", item.heading + (if (item.detail.isNotBlank()) " · " + item.detail else ""))
            .text("It stays on your server; this only frees space on the phone.")
            .button("Remove from phone", primary = true) { OfflineStore.remove(this, item.id) }
            .button("Cancel").show()
    }

    companion object {
        private const val BG = 0xFF0B0D10.toInt()
        private const val MUTED = 0xFF9AA0A6.toInt()
    }
}
