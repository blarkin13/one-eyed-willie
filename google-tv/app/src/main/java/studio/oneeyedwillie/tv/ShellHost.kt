package studio.oneeyedwillie.tv

/** What MainActivity offers the app shell (the phone app's tab bar and More sheet). */
interface ShellHost {
    /** Opens a path on the connected server, e.g. "/movies". */
    fun shellOpen(path: String)
    fun shellConnectionSettings()
    fun shellYarrAccount()
}
