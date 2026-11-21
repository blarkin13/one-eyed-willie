package studio.oneeyedwillie.tv

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Watch progress made offline goes back to the server when it can be reached
 * again. Each update carries when it was watched, and the server ignores it if
 * the title was watched more recently somewhere else.
 */
object OfflineSync {
    private val running = AtomicBoolean(false)

    fun later(context: Context) {
        val app = context.applicationContext
        if (OfflineStore.all(app).none { it.pendingSync }) return
        if (!running.compareAndSet(false, true)) return
        Thread({ try { run(app) } finally { running.set(false) } }, "offline-sync").start()
    }

    private fun run(context: Context) {
        for (item in OfflineStore.all(context).filter { it.pendingSync && it.durationMs > 0 }) {
            val target = ServerTarget(item.origin, item.remote, item.serverId)
            val body = JSONObject()
                .put("media_id", item.mediaId)
                .put("position_seconds", item.positionMs / 1000.0)
                .put("duration_seconds", item.durationMs / 1000.0)
                .put("completed", item.watched)
                .put("played_at", (if (item.playedAt > 0) item.playedAt else System.currentTimeMillis()) / 1000.0)
            try {
                OfflineNet.json(context, target, "/api/playback/progress", "PUT", body)
                OfflineStore.update(context, item.id) { if (it.playedAt == item.playedAt) it.pendingSync = false }
            } catch (e: OfflineNet.HttpError) {
                // The server won't take it (title gone, access removed): stop trying.
                if (e.status in 400..499) OfflineStore.update(context, item.id) { it.pendingSync = false }
            } catch (_: IOException) {
                return   // not reachable yet; try again next time
            }
        }
    }
}

/** The episode after a downloaded one, on the phone or on the server. */
object OfflineNext {
    /** A downloaded episode that comes next in the same show, if any. */
    fun downloaded(context: Context, current: OfflineItem): OfflineItem? {
        if (current.kind != "episode") return null
        val server = current.key.substringBeforeLast('#')
        val candidates = OfflineStore.all(context).filter {
            it.status == "done" && it.kind == "episode" && it.id != current.id &&
                it.showTitle == current.showTitle && it.key.substringBeforeLast('#') == server
        }
        val index = OfflineLogic.nextEpisode(current.season to current.episode, candidates.map { it.season to it.episode })
        return candidates.getOrNull(index)
    }

    /**
     * The next episode on the server that isn't downloaded yet, as a new download
     * with the same quality and Wi-Fi choice. Blocks; null when there's none or
     * the server can't be reached.
     */
    fun fromServer(context: Context, current: OfflineItem): OfflineItem? {
        if (current.kind != "episode") return null
        val target = ServerTarget(current.origin, current.remote, current.serverId)
        return try {
            val next = OfflineNet.json(context, target, "/api/tv/next?media_id=${current.mediaId}&include_watched=true")
                .optJSONObject("next") ?: return null
            val mediaId = next.optLong("media_id")
            val key = current.key.substringBeforeLast('#') + "#" + mediaId
            if (mediaId <= 0 || OfflineStore.find(context, key) != null) return null
            val season = if (next.isNull("season")) null else next.optInt("season")
            val episode = if (next.isNull("episode")) null else next.optInt("episode")
            val title = try {
                OfflineNet.json(context, target, "/api/tv/episode?media_id=" + URLEncoder.encode(mediaId.toString(), "UTF-8"))
                    .optString("title")
            } catch (_: Exception) { "" }
            OfflineItem(
                id = OfflineItem.newId(), key = key, mediaId = mediaId, kind = "episode",
                title = title.ifBlank { "Episode " + (episode ?: "") }, subtitle = OfflineLogic.episodeLabel(season, episode),
                showTitle = current.showTitle, season = season, episode = episode, posterUrl = current.posterUrl,
                origin = current.origin, remote = current.remote, serverId = current.serverId,
                quality = current.quality, wifiOnly = current.wifiOnly)
        } catch (_: Exception) { null }
    }
}
