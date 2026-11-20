package studio.oneeyedwillie.tv

import android.content.Context
import android.os.Looper
import java.net.HttpURLConnection
import java.net.URI

/**
 * Watching away from home (Yarr Media Pro).
 *
 * When the home server can't be reached on the local network, a TV that is
 * signed in to a Yarr account asks yarr.media for its server's internet address
 * and a short-lived signed pass. Video and pages then come straight from the
 * home server; yarr.media only issues the pass. The pass goes to the server as
 * the `yarr_pass` cookie (WebView) or an `Authorization: Yarr-Pass` header
 * (player and native calls), only ever to that server's origin, and is renewed
 * well before it expires.
 */
object RemoteSession {
    private const val PREFS = "yarr_remote"
    /** Renew when less than this is left; passes last an hour. */
    const val REFRESH_BEFORE_MS = 15 * 60 * 1000L

    data class Active(val origin: String, val serverId: String, val pass: String, val expiresAtMillis: Long)

    sealed class Connect {
        data class Ok(val origin: String) : Connect()
        object NotSignedIn : Connect()
        object SignedOut : Connect()
        object NoServer : Connect()
        object NoAddress : Connect()
        object ProRequired : Connect()
        data class Failed(val message: String) : Connect()
    }

    @Volatile private var active: Active? = null
    private val lock = Any()

    // ---- Pure helpers (unit tested) ------------------------------------------

    /** Prefer this TV's home server, then one that is online, then any with an address. */
    fun chooseServer(servers: List<YarrAccount.RemoteServer>, homeIdentity: String?): YarrAccount.RemoteServer? {
        val usable = servers.filter { !it.remoteAddress.isNullOrBlank() }
        return usable.firstOrNull { !homeIdentity.isNullOrBlank() && it.identity == homeIdentity }
            ?: usable.firstOrNull { it.online } ?: usable.firstOrNull()
    }

    fun needsRefresh(expiresAtMillis: Long, nowMillis: Long): Boolean =
        expiresAtMillis - nowMillis < REFRESH_BEFORE_MS

    fun sameOrigin(url: String, origin: String): Boolean = try {
        val a = URI(url)
        val b = URI(origin)
        fun port(u: URI) = if (u.port != -1) u.port else if (u.scheme.equals("https", true)) 443 else 80
        a.scheme.equals(b.scheme, true) && a.host != null && a.host.equals(b.host, true) &&
            port(a) == port(b) && a.userInfo == null
    } catch (_: Exception) { false }

    /** The header value for [url], or null when it is not the remote server. */
    fun authorizationFor(url: String, session: Active?): String? =
        if (session != null && session.origin.startsWith("https://") && sameOrigin(url, session.origin))
            "Yarr-Pass " + session.pass else null

    fun cookieFor(session: Active, nowMillis: Long): String {
        val age = ((session.expiresAtMillis - nowMillis) / 1000).coerceAtLeast(1)
        return "yarr_pass=${session.pass}; Path=/; Max-Age=$age; Secure; HttpOnly; SameSite=Lax"
    }

    // ---- State -------------------------------------------------------------------

    fun current(): Active? = active

    /** True when [origin] is the server this TV is watching remotely. */
    fun isRemote(context: Context, origin: String): Boolean =
        active?.origin == origin || prefs(context).getString("origin", null) == origin

    fun rememberHomeServer(context: Context, identity: String) {
        if (identity.isNotBlank()) prefs(context).edit().putString("home_identity", identity).apply()
    }

    /** Leaves remote mode (back on the home network, or signed out). */
    fun clear(context: Context) {
        synchronized(lock) { active = null }
        prefs(context).edit().remove("origin").remove("server_id").apply()
    }

    /** Finds the account's server and gets a pass. Blocks: call off the main thread. */
    fun connect(context: Context): Connect {
        val token = YarrAccount.savedToken(context) ?: return Connect.NotSignedIn
        val servers = try { YarrAccount.servers(token) } catch (e: Exception) {
            return Connect.Failed(e.message ?: "Could not reach yarr.media")
        } ?: return Connect.SignedOut
        if (servers.isEmpty()) return Connect.NoServer
        val server = chooseServer(servers, prefs(context).getString("home_identity", null))
            ?: return Connect.NoAddress
        return when (val reply = YarrAccount.pass(token, server.id)) {
            is YarrAccount.PassReply.Granted -> {
                val origin = (reply.remoteAddress ?: server.remoteAddress!!).trimEnd('/')
                synchronized(lock) { active = Active(origin, server.id, reply.pass, reply.expiresAtMillis) }
                prefs(context).edit().putString("origin", origin).putString("server_id", server.id).apply()
                Connect.Ok(origin)
            }
            YarrAccount.PassReply.ProRequired -> Connect.ProRequired
            YarrAccount.PassReply.SignedOut -> Connect.SignedOut
            YarrAccount.PassReply.ServerNotFound -> Connect.NoServer
            is YarrAccount.PassReply.Failed -> Connect.Failed(reply.message)
        }
    }

    /**
     * Returns a pass for [origin] with plenty of time left, renewing it if
     * needed (also after the app process was restarted). Blocks: call off the
     * main thread. Null when [origin] is not the remote server or renewal failed.
     */
    fun freshPass(context: Context, origin: String): Active? {
        val now = System.currentTimeMillis()
        active?.let { if (it.origin == origin && !needsRefresh(it.expiresAtMillis, now)) return it }
        val p = prefs(context)
        if (p.getString("origin", null) != origin) return null
        val serverId = p.getString("server_id", null) ?: return null
        val token = YarrAccount.savedToken(context) ?: return null
        synchronized(lock) {
            active?.let { if (it.origin == origin && !needsRefresh(it.expiresAtMillis, System.currentTimeMillis())) return it }
            val reply = YarrAccount.pass(token, serverId)
            if (reply is YarrAccount.PassReply.Granted) {
                active = Active(origin, serverId, reply.pass, reply.expiresAtMillis)
                return active
            }
            // Keep using a still-valid pass if renewal failed for a moment.
            return active?.takeIf { it.origin == origin && it.expiresAtMillis > System.currentTimeMillis() + 60_000 }
        }
    }

    /** Adds the pass to a request for the remote server (renewing it first when off the main thread). */
    fun authorize(context: Context, connection: HttpURLConnection) {
        val url = connection.url.toString()
        val session = if (Looper.myLooper() != Looper.getMainLooper())
            active?.origin?.takeIf { sameOrigin(url, it) }?.let { freshPass(context, it) } ?: active
        else active
        authorizationFor(url, session)?.let { connection.setRequestProperty("Authorization", it) }
    }

    /** For the player's data source: header for [url], renewing first. Called on loader threads. */
    fun headerFor(context: Context, url: String, origin: String): String? =
        if (sameOrigin(url, origin)) authorizationFor(url, freshPass(context, origin) ?: active) else null

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
