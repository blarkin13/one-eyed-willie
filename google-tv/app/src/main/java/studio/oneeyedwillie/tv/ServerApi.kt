package studio.oneeyedwillie.tv

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class MediaEntry(val title: String, val key: String, val libraryId: Int, val kind: String, val year: Int?)
data class EpisodeEntry(val id: Int, val title: String)

class ServerApi(rawUrl: String) {
    val base = rawUrl.trim().trimEnd('/')
    init {
        val u = URL(base)
        require(u.protocol == "http" || u.protocol == "https") { "Use an HTTP or HTTPS server address" }
        require(u.host.isNotBlank() && u.userInfo == null && u.query == null && u.ref == null &&
            (u.path.isEmpty() || u.path == "/")) { "Use the server address only, without a path" }
    }
    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
    private suspend fun get(path: String): JSONObject = withContext(Dispatchers.IO) {
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 6000
            readTimeout = 12000
            requestMethod = "GET"
        }
        try {
            if (connection.responseCode !in 200..299) error("Server returned HTTP ${connection.responseCode}")
            JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }
    suspend fun ping(): Boolean = get("/health").optString("status") == "ok"
    suspend fun catalog(kind: String): List<MediaEntry> {
        val data = get("/api/catalog?kind=${enc(kind)}&limit=100")
        val items = data.getJSONArray("items")
        return (0 until items.length()).map { i ->
            val o = items.getJSONObject(i)
            MediaEntry(o.getString("title"), o.getString("key"), o.getInt("library_id"),
                o.getString("kind"), if (o.isNull("year")) null else o.getInt("year"))
        }
    }
    suspend fun episodes(item: MediaEntry): List<EpisodeEntry> {
        val data = get("/api/tv/show?library_id=${item.libraryId}&key=${enc(item.key)}")
        val seasons = data.getJSONArray("seasons")
        val result = mutableListOf<EpisodeEntry>()
        for (i in 0 until seasons.length()) {
            val season = seasons.getJSONObject(i)
            if (season.isNull("number")) continue
            val number = season.getInt("number")
            val detail = get("/api/tv/season?library_id=${item.libraryId}&key=${enc(item.key)}&season_number=$number")
            val episodes = detail.getJSONArray("episodes")
            for (j in 0 until episodes.length()) {
                val e = episodes.getJSONObject(j)
                result.add(EpisodeEntry(e.getInt("id"), "S${number.toString().padStart(2, '0')}E${e.optInt("episode", 0).toString().padStart(2, '0')} · ${e.optString("title", "Episode")}"))
            }
        }
        return result
    }
    suspend fun movieMediaId(item: MediaEntry): Int =
        get("/api/playback/movie?library_id=${item.libraryId}&key=${enc(item.key)}").getInt("media_id")
    fun streamUrl(mediaId: Int): String = "$base/api/playback/$mediaId/stream"
}
