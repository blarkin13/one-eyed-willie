package studio.oneeyedwillie.tv

/** Pure rules behind the phone app's tab bar and More sheet (unit tested). */
object ShellLogic {
    data class NavLink(val id: String, val href: String, val name: String, val service: String = "")

    val TAB_IDS = listOf("home", "movies", "tv", "music")
    private val TAB_ROOTS = setOf("/", "/movies", "/tv", "/music")
    private val HUB_SERVICES = setOf("radarr", "sonarr", "sabnzbd")

    /** Which tab a server path belongs to; "" while a video plays. */
    fun tabFor(path: String): String {
        val p = path.ifEmpty { "/" }
        return when {
            p == "/" || p == "/app" -> "home"
            p == "/movies" || p == "/movie" || p.startsWith("/movies/") -> "movies"
            p == "/tv" || p.startsWith("/tv/") -> "tv"
            p == "/music" || p.startsWith("/music/") -> "music"
            p.startsWith("/watch/") -> ""
            else -> "more"
        }
    }

    fun isTabRoot(path: String) = path.ifEmpty { "/" } in TAB_ROOTS

    /** Server pages for the More sheet: everything the web navigation has that isn't a tab. */
    fun moreLinks(links: List<NavLink>): List<NavLink> {
        val hub = links.any { it.service == "services" }
        return links.filter { it.id !in TAB_IDS && it.name.isNotBlank() &&
                it.href.startsWith("/") && !it.href.startsWith("//") }
            .filterNot { hub && it.service in HUB_SERVICES }
            .distinctBy { it.href }
    }

    fun hasMusic(links: List<NavLink>) = links.any { it.id == "music" }
}
