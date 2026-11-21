package studio.oneeyedwillie.tv

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/** One downloaded (or downloading) title, kept in the app's private storage. */
class OfflineItem(
    val id: String,
    val key: String,
    val mediaId: Long,
    val kind: String,                 // "movie" | "episode"
    val title: String,
    val subtitle: String,
    val showTitle: String,
    val season: Int?,
    val episode: Int?,
    val posterUrl: String,
    val origin: String,               // the server address used when it was added
    val remote: Boolean,
    val serverId: String?,
    val quality: String,
    val wifiOnly: Boolean,
    var status: String = "waiting",   // waiting | waiting_wifi | preparing | downloading | paused | failed | done
    var progress: Double = 0.0,
    var bytes: Long = 0,
    var error: String? = null,
    var jobId: String? = null,
    var positionMs: Long = 0,
    var durationMs: Long = 0,
    var watched: Boolean = false,
    var pendingSync: Boolean = false, // watch progress made offline, not yet sent to the server
    val addedAt: Long = System.currentTimeMillis(),
) {
    val heading: String get() = if (kind == "episode" && showTitle.isNotBlank()) showTitle else title
    val detail: String get() = if (kind == "episode") listOf(subtitle, title).filter { it.isNotBlank() }.joinToString(" · ") else subtitle

    fun toJson(): JSONObject = JSONObject()
        .put("id", id).put("key", key).put("media_id", mediaId).put("kind", kind).put("title", title)
        .put("subtitle", subtitle).put("show_title", showTitle).put("season", season ?: JSONObject.NULL)
        .put("episode", episode ?: JSONObject.NULL).put("poster_url", posterUrl).put("origin", origin)
        .put("remote", remote).put("server_id", serverId ?: JSONObject.NULL).put("quality", quality)
        .put("wifi_only", wifiOnly).put("status", status).put("progress", progress).put("bytes", bytes)
        .put("error", error ?: JSONObject.NULL).put("job_id", jobId ?: JSONObject.NULL)
        .put("position_ms", positionMs).put("duration_ms", durationMs).put("watched", watched)
        .put("pending_sync", pendingSync).put("added_at", addedAt)

    companion object {
        fun fromJson(o: JSONObject) = OfflineItem(
            id = o.getString("id"), key = o.getString("key"), mediaId = o.getLong("media_id"),
            kind = o.optString("kind", "movie"), title = o.optString("title"), subtitle = o.optString("subtitle"),
            showTitle = o.optString("show_title"),
            season = if (o.isNull("season")) null else o.optInt("season"),
            episode = if (o.isNull("episode")) null else o.optInt("episode"),
            posterUrl = o.optString("poster_url"), origin = o.getString("origin"), remote = o.optBoolean("remote"),
            serverId = if (o.isNull("server_id")) null else o.optString("server_id"),
            quality = o.optString("quality", "720p"), wifiOnly = o.optBoolean("wifi_only", true),
            status = o.optString("status", "waiting"), progress = o.optDouble("progress", 0.0),
            bytes = o.optLong("bytes"), error = if (o.isNull("error")) null else o.optString("error"),
            jobId = if (o.isNull("job_id")) null else o.optString("job_id"),
            positionMs = o.optLong("position_ms"), durationMs = o.optLong("duration_ms"),
            watched = o.optBoolean("watched"), pendingSync = o.optBoolean("pending_sync"),
            addedAt = o.optLong("added_at", System.currentTimeMillis()),
        )

        fun newId(): String = UUID.randomUUID().toString()
    }
}

/** The phone's list of downloads, saved as JSON next to the files. */
object OfflineStore {
    private val lock = Any()
    private val listeners = mutableSetOf<() -> Unit>()
    private val main = Handler(Looper.getMainLooper())

    fun root(context: Context) = File(context.filesDir, "offline").apply { mkdirs() }
    fun folder(context: Context, item: OfflineItem) = File(root(context), item.id).apply { mkdirs() }
    fun video(context: Context, item: OfflineItem) = File(folder(context, item), "video.mp4")
    fun partial(context: Context, item: OfflineItem) = File(folder(context, item), "video.mp4.part")
    fun poster(context: Context, item: OfflineItem) = File(folder(context, item), "poster.jpg")
    fun subtitles(context: Context, item: OfflineItem): List<File> =
        File(folder(context, item), "subs").listFiles { f -> f.name.endsWith(".vtt") }?.sortedBy { it.name } ?: emptyList()

    private fun index(context: Context) = File(root(context), "index.json")

    fun all(context: Context): List<OfflineItem> = synchronized(lock) {
        val file = index(context)
        if (!file.isFile) return emptyList()
        return try {
            val list = JSONArray(file.readText())
            (0 until list.length()).mapNotNull { i -> list.optJSONObject(i)?.let { runCatching { OfflineItem.fromJson(it) }.getOrNull() } }
        } catch (_: Exception) { emptyList() }
    }

    private fun write(context: Context, items: List<OfflineItem>) {
        val file = index(context)
        val tmp = File(file.parentFile, "index.json.tmp")
        tmp.writeText(JSONArray().apply { items.forEach { put(it.toJson()) } }.toString())
        tmp.renameTo(file)
        main.post { listeners.toList().forEach { it() } }
    }

    fun find(context: Context, key: String): OfflineItem? = all(context).firstOrNull { it.key == key }
    fun get(context: Context, id: String): OfflineItem? = all(context).firstOrNull { it.id == id }

    fun add(context: Context, item: OfflineItem) = synchronized(lock) {
        write(context, all(context).filterNot { it.key == item.key } + item)
    }

    /** Changes one item; returns it, or null if it was deleted meanwhile. */
    fun update(context: Context, id: String, change: (OfflineItem) -> Unit): OfflineItem? = synchronized(lock) {
        val items = all(context)
        val item = items.firstOrNull { it.id == id } ?: return null
        change(item)
        write(context, items)
        return item
    }

    fun remove(context: Context, id: String) = synchronized(lock) {
        val items = all(context)
        items.firstOrNull { it.id == id }?.let { File(root(context), it.id).deleteRecursively() }
        write(context, items.filterNot { it.id == id })
    }

    /** The next download that still has work to do. */
    fun nextWork(context: Context): OfflineItem? =
        all(context).sortedBy { it.addedAt }.firstOrNull { it.status !in setOf("done", "failed") }

    fun observe(listener: () -> Unit) { listeners.add(listener) }
    fun stopObserving(listener: () -> Unit) { listeners.remove(listener) }
}
