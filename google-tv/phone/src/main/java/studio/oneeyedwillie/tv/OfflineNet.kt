package studio.oneeyedwillie.tv

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Requests to the server a download comes from. At home the server is reached
 * directly; away (or when home can't be reached any more) through its internet
 * address with a Yarr pass, as long as the server is on the Yarr account.
 */
object OfflineNet {
    class HttpError(val status: Int, val error: String?) : IOException("Server returned HTTP $status")

    private data class Pass(val origin: String, val pass: String, val expiresAtMillis: Long)
    private val passes = mutableMapOf<String, Pass>()

    private fun remotePass(context: Context, serverId: String, fresh: Boolean = false): Pass? {
        synchronized(passes) {
            passes[serverId]?.let { if (!fresh && it.expiresAtMillis - System.currentTimeMillis() > 5 * 60_000) return it }
            val token = YarrAccount.savedToken(context) ?: return null
            val reply = YarrAccount.pass(token, serverId)
            if (reply is YarrAccount.PassReply.Granted && !reply.remoteAddress.isNullOrBlank()) {
                return Pass(reply.remoteAddress.trimEnd('/'), reply.pass, reply.expiresAtMillis).also { passes[serverId] = it }
            }
            if (reply is YarrAccount.PassReply.ProRequired || reply is YarrAccount.PassReply.OwnerProRequired)
                throw HttpError(403, "pro_required")
            return null
        }
    }

    private fun open(url: String, method: String, auth: String?, range: String?, timeoutMs: Int): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = timeoutMs
            readTimeout = 30_000
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json, video/mp4, */*")
            auth?.let { setRequestProperty("Authorization", it) }
            range?.let { setRequestProperty("Range", it) }
            if (method == "POST") { doOutput = true; setFixedLengthStreamingMode(0) }
        }

    /**
     * An open connection for [path] on [target]'s server (response code already
     * read and OK). Throws [HttpError] for server refusals, IOException when the
     * server can't be reached at all.
     */
    fun connect(context: Context, target: ServerTarget, path: String, method: String = "GET", range: String? = null): HttpURLConnection {
        var lastProblem: IOException? = null
        if (!target.remote) {
            try {
                val c = open(target.origin + path, method, null, range, 4_000)
                val code = c.responseCode
                if (code in 200..299) return c
                val error = readError(c)
                if (code != 401 && code != 403 || target.serverId == null) throw HttpError(code, error)
            } catch (e: HttpError) { throw e } catch (e: IOException) { lastProblem = e }
        }
        val serverId = target.serverId ?: throw (lastProblem ?: IOException("This server can't be reached from here"))
        for (fresh in listOf(false, true)) {
            val pass = remotePass(context, serverId, fresh) ?: throw (lastProblem ?: IOException("Sign in to Yarr Media to download away from home"))
            val c = open(pass.origin + path, method, "Yarr-Pass " + pass.pass, range, 10_000)
            val code = c.responseCode
            if (code in 200..299) return c
            val error = readError(c)
            if (code == 401 && !fresh) continue     // pass expired: get a new one once
            throw HttpError(code, error)
        }
        throw IOException("Could not reach the server")
    }

    fun json(context: Context, target: ServerTarget, path: String, method: String = "GET"): JSONObject {
        val c = connect(context, target, path, method)
        try { return JSONObject(c.inputStream.bufferedReader().use { it.readText().take(200_000) }) }
        finally { c.disconnect() }
    }

    private fun readError(c: HttpURLConnection): String? = try {
        val text = c.errorStream?.bufferedReader()?.use { it.readText().take(4000) } ?: ""
        val detail = JSONObject(text).opt("detail")
        when (detail) {
            is JSONObject -> detail.optString("error").ifBlank { null }
            is String -> detail
            else -> JSONObject(text).optString("error").ifBlank { null }
        }
    } catch (_: Exception) { null } finally { c.disconnect() }
}
