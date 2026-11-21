package studio.oneeyedwillie.tv

import java.util.Locale

/** Plain rules behind downloads for offline use (no Android types, unit-tested). */
object OfflineLogic {
    fun sizeLabel(bytes: Long): String = when {
        bytes <= 0 -> ""
        bytes >= 1_000_000_000L -> String.format(Locale.US, "%.1f GB", bytes / 1e9)
        bytes >= 1_000_000L -> String.format(Locale.US, "%d MB", Math.round(bytes / 1e6))
        else -> String.format(Locale.US, "%d KB", Math.max(1, Math.round(bytes / 1e3)))
    }

    /** "720p · about 1.1 GB", "Original quality · up to 4.2 GB". */
    fun qualityLabel(label: String, bytes: Long, kind: String): String {
        val size = sizeLabel(bytes)
        if (size.isEmpty()) return label
        return label + " · " + (if (kind == "up_to") "up to " else "about ") + size
    }

    /** Range header to resume a partly downloaded file, or null to start fresh. */
    fun rangeHeader(alreadyHave: Long): String? = if (alreadyHave > 0) "bytes=$alreadyHave-" else null

    /** True when the server answered a resume request by continuing (206) rather than restarting. */
    fun resumes(status: Int, alreadyHave: Long): Boolean = alreadyHave > 0 && status == 206

    /** Total size from "Content-Range: bytes 100-999/1000", else from Content-Length plus what we have. */
    fun totalBytes(contentRange: String?, contentLength: Long, alreadyHave: Long, resumed: Boolean): Long {
        val total = contentRange?.substringAfterLast('/', "")?.trim()?.toLongOrNull()
        if (total != null && total > 0) return total
        if (contentLength <= 0) return -1
        return if (resumed) contentLength + alreadyHave else contentLength
    }

    /** Watched once 95% has been played (the same rule as the server). */
    fun watched(positionMs: Long, durationMs: Long): Boolean = durationMs > 0 && positionMs >= durationMs * 0.95

    /** Where to start playing again: from the saved spot, unless it was finished or barely started. */
    fun resumeFrom(positionMs: Long, durationMs: Long): Long =
        if (positionMs < 30_000 || watched(positionMs, durationMs)) 0 else positionMs

    /** One line under a download in the list. */
    fun statusLine(status: String, progress: Double, bytes: Long, error: String?): String = when (status) {
        "done" -> sizeLabel(bytes)
        "preparing" -> "Preparing on your server" + percent(progress)
        "downloading" -> "Downloading" + percent(progress)
        "waiting_wifi" -> "Waiting for Wi-Fi"
        "paused" -> error ?: "Waiting for a connection"
        "failed" -> error ?: "Download failed"
        else -> "Waiting to download"
    }

    private fun percent(progress: Double) =
        if (progress > 0) " · " + (progress * 100).toInt().coerceIn(0, 100) + "%" else ""

    /** "S01 · E04" (or what's known of it). */
    fun episodeLabel(season: Int?, episode: Int?): String = when {
        season != null && episode != null -> "S" + season.toString().padStart(2, '0') + " · E" + episode.toString().padStart(2, '0')
        episode != null -> "E" + episode.toString().padStart(2, '0')
        else -> ""
    }

    /** Index of the episode that comes right after [current] among [candidates], or -1. */
    fun nextEpisode(current: Pair<Int?, Int?>, candidates: List<Pair<Int?, Int?>>): Int {
        val (season, episode) = current
        if (season == null || episode == null) return -1
        var best = -1
        candidates.forEachIndexed { i, (s, e) ->
            if (s == null || e == null) return@forEachIndexed
            val after = s > season || (s == season && e > episode)
            val b = candidates.getOrNull(best)
            if (after && (b == null || s < b.first!! || (s == b.first && e < b.second!!))) best = i
        }
        return best
    }

    /** The same title from the same server counts as one download. */
    fun key(serverKey: String, mediaId: Long) = "$serverKey#$mediaId"
}
