package studio.oneeyedwillie.tv

import android.app.Activity
import android.view.View
import android.webkit.WebView
import android.widget.FrameLayout

/**
 * Google TV: no app shell. Every hook leaves the TV exactly as it was; the
 * phone app (google-tv/phone) has its own AppShell with the same functions.
 */
object AppShell {
    fun prepareWebView(activity: Activity, web: WebView) = Unit
    fun wrap(activity: Activity, host: ShellHost, screen: FrameLayout, web: WebView): View = screen
    fun onPageStarted(url: String?) = Unit
    fun onPageFinished(web: WebView, url: String?) = Unit
    fun onBack(activity: Activity, host: ShellHost, web: WebView): Boolean = false
    fun onPrompt(activity: Activity, message: String): Boolean = false
    /** Null keeps WebView's own default. */
    fun defaultVideoPoster(): android.graphics.Bitmap? = null
    fun openDownloads(activity: Activity) = Unit
    /** 0: the TV keeps Android's own dialog look. */
    fun dialogTheme(): Int = 0
    fun styleDialog(dialog: android.app.Dialog) = Unit
}
