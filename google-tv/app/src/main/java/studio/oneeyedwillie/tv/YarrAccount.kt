package studio.oneeyedwillie.tv

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Yarr Media account sign-in for the TV (device-code flow).
 *
 * The TV asks yarr.media for a short code, shows it, and the viewer approves it
 * on a phone at yarr.media/activate. The TV then receives its own credential,
 * which can be signed out from My Account. Nothing here touches media playback
 * at home; the credential is only for remote access (see RemoteSession) and the
 * account screen.
 */
object YarrAccount {
    const val SITE = "https://yarr.media"
    private const val PREFS = "yarr_account"

    data class DeviceCode(val deviceCode: String, val userCode: String, val verificationUri: String,
                          val expiresInSeconds: Int, val intervalSeconds: Int)

    data class Profile(val email: String, val displayName: String, val pro: Boolean)

    /** A server paired with the signed-in account, as /api/device/me lists it. */
    data class RemoteServer(val id: String, val identity: String, val name: String,
                            val online: Boolean, val remoteAddress: String?)

    sealed class PassReply {
        data class Granted(val pass: String, val expiresAtMillis: Long, val remoteAddress: String?) : PassReply()
        object ProRequired : PassReply()
        object SignedOut : PassReply()
        object ServerNotFound : PassReply()
        data class Failed(val message: String) : PassReply()
    }

    /** Maps the pass endpoint's reply. Pure, so it is unit tested. */
    fun passOutcome(status: Int, error: String?, pass: String?, expiresAtMillis: Long?, remoteAddress: String?): PassReply = when {
        status == 200 && !pass.isNullOrBlank() && expiresAtMillis != null ->
            PassReply.Granted(pass, expiresAtMillis, remoteAddress?.takeIf { it.startsWith("https://") })
        status == 401 -> PassReply.SignedOut
        status == 402 || error == "pro_required" -> PassReply.ProRequired
        status == 404 -> PassReply.ServerNotFound
        else -> PassReply.Failed("Yarr Media returned HTTP $status")
    }

    sealed class Poll {
        object Pending : Poll()
        data class SlowDown(val intervalSeconds: Int) : Poll()
        object Denied : Poll()
        object Expired : Poll()
        data class Granted(val token: String) : Poll()
        data class Failed(val message: String) : Poll()
    }

    /** Maps the token endpoint's reply to what the TV should do next. Pure, so it is unit tested. */
    fun pollOutcome(status: Int, error: String?, token: String?, interval: Int?, currentInterval: Int): Poll = when {
        status in 200..299 && !token.isNullOrBlank() -> Poll.Granted(token)
        error == "authorization_pending" -> Poll.Pending
        error == "slow_down" -> Poll.SlowDown((interval ?: currentInterval + 5).coerceIn(currentInterval, 30))
        error == "access_denied" -> Poll.Denied
        error == "expired_token" || error == "invalid_grant" -> Poll.Expired
        else -> Poll.Failed("Yarr Media returned HTTP $status")
    }

    fun savedToken(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("token", null)?.takeIf { it.startsWith("ydv_") }

    fun saveToken(context: Context, token: String?) {
        val edit = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
        if (token == null) edit.remove("token") else edit.putString("token", token)
        edit.apply()
    }

    private class Reply(val status: Int, val body: JSONObject)

    private fun call(method: String, path: String, token: String? = null, json: JSONObject? = null): Reply {
        val connection = (URL(SITE + path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000
            readTimeout = 12000
            requestMethod = method
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-Yarr-App-Version", BuildConfigVersion.name)
            if (token != null) setRequestProperty("Authorization", "Bearer $token")
            if (json != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
        }
        try {
            if (json != null) connection.outputStream.use { it.write(json.toString().toByteArray()) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val body = try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            return Reply(status, body)
        } finally {
            connection.disconnect()
        }
    }

    /** Network calls below block; run them off the main thread. */
    fun requestCode(deviceName: String, deviceType: String = "google_tv"): DeviceCode {
        val reply = call("POST", "/api/device/code", json = JSONObject()
            .put("device_name", deviceName.take(60)).put("device_type", deviceType))
        if (reply.status != 201) error("Could not get a sign-in code (HTTP ${reply.status})")
        val b = reply.body
        return DeviceCode(b.getString("device_code"), b.getString("user_code"),
            b.optString("verification_uri", "$SITE/activate"), b.optInt("expires_in", 600), b.optInt("interval", 5))
    }

    fun poll(deviceCode: String, currentInterval: Int): Poll = try {
        val reply = call("POST", "/api/device/token", json = JSONObject().put("device_code", deviceCode))
        val b = reply.body
        pollOutcome(reply.status, b.optString("error").ifBlank { null }, b.optString("access_token").ifBlank { null },
            if (b.has("interval")) b.optInt("interval") else null, currentInterval)
    } catch (e: Exception) {
        Poll.Pending  // a dropped request just waits for the next poll
    }

    /** Returns null when the credential is no longer valid (signed out elsewhere). */
    fun profile(token: String): Profile? {
        val reply = call("GET", "/api/device/me", token = token)
        if (reply.status == 401) return null
        if (reply.status != 200) error("Yarr Media returned HTTP ${reply.status}")
        val user = reply.body.getJSONObject("user")
        return Profile(user.optString("email"), user.optString("display_name"),
            reply.body.optJSONObject("pro")?.optBoolean("active", false) ?: false)
    }

    /** Servers paired with this account; null when the credential is no longer valid. */
    fun servers(token: String): List<RemoteServer>? {
        val reply = call("GET", "/api/device/me", token = token)
        if (reply.status == 401) return null
        if (reply.status != 200) error("Yarr Media returned HTTP ${reply.status}")
        val list = reply.body.optJSONArray("servers") ?: return emptyList()
        return (0 until list.length()).mapNotNull { i ->
            val o = list.optJSONObject(i) ?: return@mapNotNull null
            RemoteServer(o.optString("id"), o.optString("server_identity"), o.optString("display_name"),
                o.optBoolean("online", false),
                if (o.isNull("remote_address")) null else o.optString("remote_address").ifBlank { null })
        }.filter { it.id.isNotBlank() }
    }

    /** A short-lived pass that lets this TV open [serverId] from outside the home network. */
    fun pass(token: String, serverId: String): PassReply = try {
        val reply = call("POST", "/api/passes", token = token, json = JSONObject().put("server_id", serverId))
        val b = reply.body
        val expires = b.optString("expires_at").ifBlank { null }?.let {
            try { java.time.Instant.parse(it).toEpochMilli() } catch (_: Exception) { null }
        }
        passOutcome(reply.status, b.optString("error").ifBlank { null }, b.optString("pass").ifBlank { null },
            expires, if (b.isNull("remote_address")) null else b.optString("remote_address").ifBlank { null })
    } catch (e: Exception) {
        PassReply.Failed(e.message ?: "Could not reach yarr.media")
    }

    fun signOut(token: String) {
        try { call("POST", "/api/device/signout", token = token) } catch (_: Exception) {}
    }
}

/** Version string sent with account requests (shown on the account's device list). */
object BuildConfigVersion {
    /** "tv-<version>" or "android-<version>"; MainActivity fills in the real version. */
    @Volatile var name = "tv-0.1.0"
}
