package studio.oneeyedwillie.tv

/** What MainActivity offers the app shell (the phone app's tab bar and More sheet). */
interface ShellHost {
    /** Opens a path on the connected server, e.g. "/movies". */
    fun shellOpen(path: String)
    fun shellConnectionSettings()
    fun shellYarrAccount()
    /** The server the app is showing now (for downloads), or null if none. */
    fun shellServerTarget(): ServerTarget?
}

/**
 * Where a download comes from: the address in use now ([remote] when that's the
 * server's internet address, which needs a Yarr pass) and, when known, the
 * server's id on the Yarr account, so a download started at home can finish away.
 */
data class ServerTarget(val origin: String, val remote: Boolean, val serverId: String?)
