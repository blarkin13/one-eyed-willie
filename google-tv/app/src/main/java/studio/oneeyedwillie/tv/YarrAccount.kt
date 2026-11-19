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
 * at home; the credential is only for remote access and the account screen.
 */
object YarrAccount {
    const val SITE = "https://yarr.media"
    private const val PREFS = "yarr_account"

    data class DeviceCode(val deviceCode: String, val userCode: String, val verificationUri: String,
                          val expiresInSeconds: Int, val intervalSeconds: Int)

    data class Profile(val email: String, val displayName: String, val pro: Boolean)

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
    fun requestCode(deviceName: String): DeviceCode {
        val reply = call("POST", "/api/device/code", json = JSONObject()
            .put("device_name", deviceName.take(60)).put("device_type", "google_tv"))
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

    fun signOut(token: String) {
        try { call("POST", "/api/device/signout", token = token) } catch (_: Exception) {}
    }
}

/** Version string sent with account requests (shown on the account's device list). */
object BuildConfigVersion {
    const val name = "tv-0.1.0"
}
