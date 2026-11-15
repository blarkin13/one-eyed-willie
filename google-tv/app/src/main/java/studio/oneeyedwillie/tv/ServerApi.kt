package studio.oneeyedwillie.tv

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class MediaEntry(
    val title: String, val key: String, val libraryId: Int, val kind: String,
    val year: Int?, val mediaId: Int? = null, val progress: Int = 0,\n    val posterUrl: String? = null
)
data class EpisodeEntry(val id: Int, val title: String)
data class MediaDetails(val description: String, val artwork: String?, val backdrop: String?, val genres: String)

class ServerApi(rawUrl: String) {
    val base = rawUrl.trim().trimEnd('/')
    init {
        val u = URL(base)
        require(u.protocol == "http" || u.protocol == "https") { "Use HTTP or HTTPS" }
        require(u.host.isNotBlank() && u.userInfo == null && u.query == null && u.ref == null &&
            (u.path.isEmpty() || u.path == "/")) { "Enter the server address without a path" }
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
        } finally { connection.disconnect() }
    }
    private fun entry(o: JSONObject): MediaEntry = MediaEntry(
        o.getString("title"), o.getString("key"), o.getInt("library_id"),
        o.getString("kind"), if(o.isNull("year")) null else o.getInt("year"),
        if(o.has("media_id")) o.optInt("media_id") else null, o.optInt("progress_percent", 0),\n        o.optString("poster_url").takeIf { it.startsWith("/api/artwork/") }?.let { base + it }
    )
    suspend fun ping() = get("/health").optString("status") == "ok"
    suspend fun home(): List<Pair<String, List<MediaEntry>>> {
        val data = get("/api/home")
        fun shelf(name: String): List<MediaEntry> {
            val a = data.getJSONArray(name)
            return (0 until a.length()).map { entry(a.getJSONObject(it)) }
        }
        return listOf(
            "Continue Watching" to shelf("continue_watching"),
            "Recently Added Movies" to shelf("recent_movies"),
            "Recently Added TV Shows" to shelf("recent_tv")
        )
    }
    suspend fun catalog(kind: String): List<MediaEntry> {
        val result = mutableListOf<MediaEntry>()
        var offset = 0
        do {
            val data = get("/api/catalog?kind=${enc(kind)}&limit=100&offset=$offset")
            val a = data.getJSONArray("items")
            for (i in 0 until a.length()) result.add(entry(a.getJSONObject(i)))
            offset += a.length()
            if (a.length() == 0) break
        } while (offset < data.optInt("total", 0))
        return result
    }
    suspend fun details(item: MediaEntry): MediaDetails {
        val path = if(item.kind == "movies") "/api/movies/details" else "/api/tv/show"
        val data = get("$path?library_id=${item.libraryId}&key=${enc(item.key)}")
        val art = data.optString("poster_url").takeIf { it.startsWith("/api/artwork/") }
        val backdrop = data.optString("backdrop_url").takeIf { it.startsWith("/api/artwork/") }
        return MediaDetails(data.optString("overview"), art?.let { base + it },
            backdrop?.let { base + it }, data.optJSONArray("genres")?.let { a ->
                (0 until a.length()).joinToString(" · ") { a.optString(it) }
            } ?: "")
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
            val a = detail.getJSONArray("episodes")
            for (j in 0 until a.length()) {
                val e = a.getJSONObject(j)
                result.add(EpisodeEntry(e.getInt("id"),
                    "S${number.toString().padStart(2, '0')}E${e.optInt("episode", 0).toString().padStart(2, '0')}  ·  ${e.optString("title", "Episode")}"))
            }
        }
        return result
    }
    suspend fun movieMediaId(item: MediaEntry): Int =
        get("/api/playback/movie?library_id=${item.libraryId}&key=${enc(item.key)}").getInt("media_id")
    fun streamUrl(mediaId: Int) = "$base/api/playback/$mediaId/stream"
}
