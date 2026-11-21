package studio.oneeyedwillie.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.IBinder
import androidx.core.app.ServiceCompat
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.Executors

/**
 * Downloads titles for offline use, one at a time, while the app is in the
 * background too. The server prepares a phone-ready file first; the download
 * resumes where it stopped if the connection drops or the app is closed.
 */
class DownloadService : Service() {
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground("Getting downloads ready", null)
        if (!running) {
            running = true
            worker.execute { try { work() } finally { running = false; stopForegroundAndSelf() } }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() { worker.shutdownNow(); super.onDestroy() }

    private fun stopForegroundAndSelf() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    // ---- The queue ---------------------------------------------------------------
    private fun work() {
        val tried = mutableSetOf<String>()
        var waitedForWifi = 0
        while (true) {
            val item = OfflineStore.all(this).sortedBy { it.addedAt }
                .firstOrNull { it.status !in setOf("done", "failed") && it.id !in tried } ?: break
            if (item.wifiOnly && metered()) {
                OfflineStore.update(this, item.id) { it.status = "waiting_wifi" }
                // Wait a while for Wi-Fi; afterwards the next app start picks it up.
                if (waitedForWifi++ < 60) { notify("Waiting for Wi-Fi", item.heading, null); Thread.sleep(30_000); continue }
                tried.add(item.id); continue
            }
            tried.add(item.id)
            try { download(item) }
            catch (e: InterruptedException) { return }
            catch (e: OfflineNet.HttpError) {
                val message = when {
                    e.error == "pro_required" -> "Downloads need Yarr Media Pro"
                    e.status == 404 -> "This title isn't on the server any more"
                    e.status == 403 -> "You can't download this title"
                    else -> e.error ?: "The server refused the download"
                }
                OfflineStore.update(this, item.id) { it.status = "failed"; it.error = message }
            }
            catch (e: IOException) {
                OfflineStore.update(this, item.id) { it.status = "paused"; it.error = "Waiting for a connection to your server" }
            }
        }
    }

    private fun download(start: OfflineItem) {
        val target = ServerTarget(start.origin, start.remote, start.serverId)
        val id = start.id
        // 1. The server prepares a phone-ready file (or has it already).
        val quality = URLEncoder.encode(start.quality, "UTF-8")
        var job = OfflineNet.json(this, target, "/api/downloads/prepare/${start.mediaId}?quality=$quality", "POST")
        OfflineStore.update(this, id) { it.jobId = job.optString("id"); it.status = "preparing"; it.error = null } ?: return
        while (job.optString("status") in setOf("queued", "preparing")) {
            val p = job.optDouble("progress", 0.0)
            OfflineStore.update(this, id) { it.progress = p } ?: return
            notify("Preparing on your server", start.heading, (p * 100).toInt())
            Thread.sleep(3_000)
            job = OfflineNet.json(this, target, "/api/downloads/jobs/${job.optString("id")}")
        }
        if (job.optString("status") != "ready") throw OfflineNet.HttpError(500, job.optString("error").ifBlank { "Preparing the download failed" })

        // 2. Download it, resuming a partial file.
        val part = OfflineStore.partial(this, start)
        val have = if (part.isFile) part.length() else 0L
        val c = OfflineNet.connect(this, target, "/api/downloads/jobs/${job.optString("id")}/file", range = OfflineLogic.rangeHeader(have))
        val resumed = OfflineLogic.resumes(c.responseCode, have)
        val total = OfflineLogic.totalBytes(c.getHeaderField("Content-Range"), c.contentLengthLong, have, resumed)
        var done = if (resumed) have else 0L
        OfflineStore.update(this, id) { it.status = "downloading"; it.progress = if (total > 0) done.toDouble() / total else 0.0 } ?: run { c.disconnect(); return }
        var lastReport = 0L
        try {
            c.inputStream.use { input ->
                FileOutputStream(part, resumed).use { out ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        if (Thread.interrupted()) throw InterruptedException()
                        val n = input.read(buffer)
                        if (n < 0) break
                        out.write(buffer, 0, n)
                        done += n
                        val now = System.currentTimeMillis()
                        if (now - lastReport > 1_000) {
                            lastReport = now
                            val p = if (total > 0) done.toDouble() / total else 0.0
                            if (OfflineStore.update(this, id) { it.progress = p } == null) { part.delete(); return }
                            notify("Downloading", start.heading, (p * 100).toInt())
                        }
                    }
                }
            }
        } finally { c.disconnect() }
        if (total > 0 && done < total) throw IOException("The download was cut off")
        val video = OfflineStore.video(this, start)
        if (!part.renameTo(video)) throw IOException("Couldn't save the download")

        // 3. Poster and subtitles (best effort: the video already plays without them).
        fetchPoster(start, target)
        fetchSubtitles(start, target)
        OfflineStore.update(this, id) { it.status = "done"; it.progress = 1.0; it.bytes = video.length(); it.error = null }
        notifyDone(start)
    }

    private fun fetchPoster(item: OfflineItem, target: ServerTarget) {
        val url = item.posterUrl
        try {
            val stream = when {
                url.startsWith("/api/") -> OfflineNet.connect(this, target, url).inputStream
                url.startsWith("https://image.tmdb.org/") -> URL(url).openStream()
                else -> return
            }
            stream.use { input -> OfflineStore.poster(this, item).outputStream().use { input.copyTo(it) } }
        } catch (_: Exception) {}
    }

    private fun fetchSubtitles(item: OfflineItem, target: ServerTarget) {
        try {
            val tracks = OfflineNet.json(this, target, "/api/stream/subtitles/${item.mediaId}").optJSONArray("tracks") ?: return
            val dir = File(OfflineStore.folder(this, item), "subs").apply { mkdirs() }
            for (i in 0 until minOf(tracks.length(), 12)) {
                val track = tracks.optJSONObject(i) ?: continue
                val trackId = track.optString("id").takeIf { Regex("[A-Za-z0-9_.:-]{1,80}").matches(it) } ?: continue
                val label = track.optString("label").ifBlank { "Subtitles" }.replace(Regex("[^A-Za-z0-9 ._()-]"), "").take(40)
                try {
                    OfflineNet.connect(this, target, "/api/stream/subtitles/${item.mediaId}/$trackId.vtt").inputStream.use { input ->
                        File(dir, String.format("%02d %s.vtt", i, label)).outputStream().use { input.copyTo(it) }
                    }
                } catch (_: Exception) {}
            }
        } catch (_: Exception) {}
    }

    private fun metered(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return true
        return !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    // ---- Notifications -----------------------------------------------------------
    private fun channel() {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Downloads", NotificationManager.IMPORTANCE_LOW))
    }

    private fun build(title: String, text: String?, percent: Int?): Notification {
        channel()
        val open = PendingIntent.getActivity(this, 0, Intent(this, DownloadsActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(title).setContentText(text).setContentIntent(open).setOngoing(true)
            .apply { if (percent != null) setProgress(100, percent.coerceIn(0, 100), false) }
            .build()
    }

    private fun startInForeground(title: String, text: String?) {
        ServiceCompat.startForeground(this, NOTE_ID, build(title, text, null),
            if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0)
    }

    private fun notify(title: String, text: String?, percent: Int?) {
        getSystemService(NotificationManager::class.java).notify(NOTE_ID, build(title, text, percent))
    }

    private fun notifyDone(item: OfflineItem) {
        channel()
        val open = PendingIntent.getActivity(this, 1, Intent(this, DownloadsActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        getSystemService(NotificationManager::class.java).notify(item.id.hashCode(),
            Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("Downloaded").setContentText(item.heading + (if (item.detail.isNotBlank()) " · " + item.detail else ""))
                .setContentIntent(open).setAutoCancel(true).build())
    }

    companion object {
        private const val CHANNEL = "downloads"
        private const val NOTE_ID = 4207

        /** Starts (or nudges) the downloader if anything is waiting. */
        fun kick(context: Context) {
            if (OfflineStore.nextWork(context) == null) return
            try { context.startForegroundService(Intent(context, DownloadService::class.java)) } catch (_: Exception) {}
        }
    }
}
