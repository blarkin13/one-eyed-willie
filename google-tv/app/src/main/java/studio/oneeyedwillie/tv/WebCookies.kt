package studio.oneeyedwillie.tv

import android.webkit.CookieManager
import java.net.CookieHandler
import java.net.URI

/**
 * Lets the app's own requests (the native player, downloads, progress sync)
 * carry the same cookies as its web pages, most importantly the household
 * profile ("Who's watching?") the person picked. Without it, those requests
 * would count as Family.
 */
object WebCookies : CookieHandler() {
    const val PROFILE = "yarr_profile"

    fun install() {
        if (CookieHandler.getDefault() !== this) CookieHandler.setDefault(this)
    }

    override fun get(uri: URI, requestHeaders: Map<String, List<String>>): Map<String, List<String>> {
        if (requestHeaders.keys.any { it.equals("Cookie", ignoreCase = true) }) return emptyMap()
        val cookie = cookiesFor(uri.toString())
        return if (cookie.isNullOrBlank()) emptyMap() else mapOf("Cookie" to listOf(cookie))
    }

    // Cookies are set by the web pages; the app's own requests never change them.
    override fun put(uri: URI, responseHeaders: Map<String, List<String>>) = Unit

    /** The profile token chosen on [origin]'s pages, for requests sent another way (e.g. away from home). */
    fun profileToken(origin: String): String? = ShellLogic.cookieValue(cookiesFor(origin), PROFILE)

    private fun cookiesFor(url: String): String? =
        try { CookieManager.getInstance().getCookie(url) } catch (_: Throwable) { null }
}
