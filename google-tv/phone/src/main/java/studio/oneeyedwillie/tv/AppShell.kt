package studio.oneeyedwillie.tv

import android.app.Activity
import android.app.Dialog
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.webkit.WebView
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONArray

/**
 * The phone app's shell around the server's pages: a native tab bar (Home,
 * Movies, TV Shows, Music, More), a More sheet for server tools and this
 * phone's settings, pull to refresh, and app-only styling that removes the
 * web navigation and makes touch behave like an app. The Google TV app has a
 * no-op AppShell with the same functions (app/src/tvShell).
 */
object AppShell {
    private const val ACTIVE = 0xFFA9DDFF.toInt()
    private const val INACTIVE = 0xFFAEB5BE.toInt()
    private const val BAR = 0xFF060608.toInt()
    private const val SHEET = 0xFF111317.toInt()

    private class Tab(val id: String, val path: String, val label: String, val icon: Int)
    private val TABS = listOf(
        Tab("home", "/", "Home", R.drawable.ic_tab_home),
        Tab("movies", "/movies", "Movies", R.drawable.ic_tab_movies),
        Tab("tv", "/tv", "TV Shows", R.drawable.ic_tab_tv),
        Tab("music", "/music", "Music", R.drawable.ic_tab_music),
        Tab("more", "", "More", R.drawable.ic_tab_more))

    private class TabView(val root: View, val icon: ImageView, val label: TextView)
    private var tabViews = emptyMap<String, TabView>()
    private var refresher: SwipeRefreshLayout? = null
    private var currentPath = "/"
    private var navLinks = emptyList<ShellLogic.NavLink>()
    private var documentStartStyle = false

    /** App-only styling, added before the page's own scripts run. */
    private val APP_CSS = """
html.yarr-app{-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%}
html.yarr-app body{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;overscroll-behavior:none}
html.yarr-app input,html.yarr-app textarea,html.yarr-app select,html.yarr-app [contenteditable="true"]{-webkit-user-select:text;user-select:text;-webkit-touch-callout:default}
html.yarr-app ::-webkit-scrollbar{display:none}
html.yarr-app .sidebar{display:none!important}
html.yarr-app .workspace{margin:0!important}
html.yarr-app .workspace>.content,html.yarr-app body[data-page] .workspace>.content{padding-top:16px!important;padding-bottom:28px!important}
html.yarr-app body[data-page="home"] .shelf-track{scroll-snap-type:x mandatory}
html.yarr-app body[data-page="home"] .shelf-track>.tile{scroll-snap-align:start}
html.yarr-app body[data-page="home"] .shelf-track .tile h3{min-height:0!important;margin:7px 0 2px!important;-webkit-line-clamp:1!important;max-height:1.3em!important}
html.yarr-app body[data-page="home"] .shelf-track .tile-meta{min-height:0!important}
html.yarr-app .cover,html.yarr-app .tile-button{transition:transform .12s ease,opacity .12s ease}
html.yarr-app .tile-button:active,html.yarr-app a:active>.cover{transform:scale(.97);opacity:.88}
html.yarr-app button:active,html.yarr-app .filter-link:active{opacity:.75}
""".trimIndent().replace("\n", "")

    private val APP_SCRIPT = """(function(){
 if(window.__yarrAppShell)return;window.__yarrAppShell=1;
 var css=${JSONArray(listOf(APP_CSS)).toString().removePrefix("[").removeSuffix("]")};
 function add(){var r=document.documentElement;if(!r)return false;r.classList.add('yarr-app');
  if(document.getElementById('yarr-app-style'))return true;
  var s=document.createElement('style');s.id='yarr-app-style';s.textContent=css;(document.head||r).appendChild(s);return true}
 if(!add())new MutationObserver(function(m,o){if(add())o.disconnect()}).observe(document,{childList:true,subtree:true});
})();"""

    /** The web navigation's links (the page draws them; the app shows them natively). */
    private val NAV_SCRIPT = """(()=>{const out=[];document.querySelectorAll('.sidebar a.nav-link').forEach(a=>{
 if(a.hidden||a.classList.contains('sidebar-hidden'))return;
 const text=(a.querySelector('.nav-text')?.textContent||a.title||a.getAttribute('aria-label')||'').replace(/ library${'$'}/,'').trim();
 out.push({id:a.dataset.navId||'',href:a.getAttribute('href')||'',name:text,service:a.dataset.serviceNav||''});});
 return JSON.stringify(out);})()"""

    fun prepareWebView(activity: Activity, web: WebView) {
        web.settings.apply {
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            // Follow the phone's text size, within limits the layout was made for.
            textZoom = (activity.resources.configuration.fontScale.coerceIn(0.85f, 1.15f) * 100).toInt()
        }
        web.overScrollMode = View.OVER_SCROLL_NEVER
        web.isVerticalScrollBarEnabled = false
        web.isHorizontalScrollBarEnabled = false
        web.setBackgroundColor(Color.BLACK)
        documentStartStyle = try {
            if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                WebViewCompat.addDocumentStartJavaScript(web, APP_SCRIPT, setOf("*"))
                true
            } else false
        } catch (_: Exception) { false }
    }

    fun wrap(activity: Activity, host: ShellHost, screen: FrameLayout, web: WebView): View {
        val index = screen.indexOfChild(web)
        screen.removeView(web)
        val pull = SwipeRefreshLayout(activity).apply {
            setColorSchemeColors(ACTIVE)
            setProgressBackgroundColorSchemeColor(0xFF1B1E24.toInt())
            addView(web, ViewGroup.LayoutParams(-1, -1))
            setOnRefreshListener { web.reload() }
        }
        refresher = pull
        screen.addView(pull, index.coerceAtLeast(0), FrameLayout.LayoutParams(-1, -1))
        return LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(screen, LinearLayout.LayoutParams(-1, 0, 1f))
            addView(tabBar(activity, host, web), LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }

    fun onPageStarted(url: String?) {
        currentPath = url?.let { Uri.parse(it).path }.orEmpty().ifEmpty { "/" }
        refreshTabs()
    }

    fun onPageFinished(web: WebView, url: String?) {
        refresher?.isRefreshing = false
        if (!documentStartStyle) web.evaluateJavascript(APP_SCRIPT, null)
        readNav(web)
        // Library links appear once the page has asked the server which exist.
        web.postDelayed({ readNav(web) }, 1500)
    }

    /** Back on a tab goes Home, Back on Home leaves the app; deeper pages go back as usual. */
    fun onBack(activity: Activity, host: ShellHost, web: WebView): Boolean {
        if (currentPath == "/" || currentPath.isEmpty()) { activity.finish(); return true }
        if (ShellLogic.isTabRoot(currentPath)) { host.shellOpen("/"); return true }
        return false
    }

    private fun readNav(web: WebView) {
        web.evaluateJavascript(NAV_SCRIPT) { result ->
            val links = try {
                val list = JSONArray(JSONArray("[$result]").getString(0))
                (0 until list.length()).map { i ->
                    val o = list.getJSONObject(i)
                    ShellLogic.NavLink(o.optString("id"), o.optString("href"), o.optString("name"), o.optString("service"))
                }
            } catch (_: Exception) { return@evaluateJavascript }
            if (links.isEmpty()) return@evaluateJavascript
            navLinks = links
            refreshTabs()
        }
    }

    private fun dp(activity: Activity, value: Int) = (value * activity.resources.displayMetrics.density + .5f).toInt()

    private fun tabBar(activity: Activity, host: ShellHost, web: WebView): View {
        val column = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BAR)
        }
        column.addView(View(activity).apply { setBackgroundColor(0xFF1E232B.toInt()) }, LinearLayout.LayoutParams(-1, 1))
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val ripple = TypedValue().also {
            activity.theme.resolveAttribute(android.R.attr.selectableItemBackgroundBorderless, it, true)
        }.resourceId
        tabViews = TABS.associate { tab ->
            val icon = ImageView(activity).apply { setImageResource(tab.icon) }
            val label = TextView(activity).apply {
                text = tab.label
                textSize = 11f
                gravity = Gravity.CENTER
                maxLines = 1
                setPadding(0, dp(activity, 3), 0, 0)
            }
            val item = LinearLayout(activity).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                isClickable = true
                isFocusable = true
                contentDescription = tab.label
                if (ripple != 0) setBackgroundResource(ripple)
                addView(icon, LinearLayout.LayoutParams(dp(activity, 24), dp(activity, 24)))
                addView(label)
                setOnClickListener { v ->
                    v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    onTab(activity, host, web, tab)
                }
            }
            row.addView(item, LinearLayout.LayoutParams(0, dp(activity, 62), 1f))
            tab.id to TabView(item, icon, label)
        }
        column.addView(row)
        refreshTabs()
        return column
    }

    private fun onTab(activity: Activity, host: ShellHost, web: WebView, tab: Tab) {
        if (tab.id == "more") { showMore(activity, host); return }
        if (ShellLogic.tabFor(currentPath) == tab.id && ShellLogic.isTabRoot(currentPath))
            web.evaluateJavascript("window.scrollTo({top:0,behavior:'smooth'})", null)
        else host.shellOpen(tab.path)
    }

    private fun refreshTabs() {
        val active = ShellLogic.tabFor(currentPath)
        tabViews["music"]?.root?.visibility = if (ShellLogic.hasMusic(navLinks)) View.VISIBLE else View.GONE
        for ((id, view) in tabViews) {
            val on = id == active
            val color = if (on) ACTIVE else INACTIVE
            view.icon.imageTintList = ColorStateList.valueOf(color)
            view.label.setTextColor(color)
            view.label.typeface = if (on) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
            view.root.isSelected = on
        }
    }

    private fun showMore(activity: Activity, host: ShellHost) {
        val dialog = Dialog(activity)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        val list = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(activity, 10), 0, dp(activity, 18))
            background = GradientDrawable().apply {
                setColor(SHEET)
                val r = dp(activity, 18).toFloat()
                cornerRadii = floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f)
            }
        }
        list.addView(View(activity).apply {
            background = GradientDrawable().apply { setColor(0xFF3A3F47.toInt()); cornerRadius = 99f }
        }, LinearLayout.LayoutParams(dp(activity, 36), dp(activity, 4)).apply {
            gravity = Gravity.CENTER_HORIZONTAL; bottomMargin = dp(activity, 6)
        })
        fun heading(text: String) = list.addView(TextView(activity).apply {
            this.text = text.uppercase()
            textSize = 11f
            letterSpacing = 0.12f
            setTextColor(0xFF8A929C.toInt())
            typeface = Typeface.DEFAULT_BOLD
            setPadding(dp(activity, 22), dp(activity, 14), dp(activity, 22), dp(activity, 6))
        })
        fun row(text: String, action: () -> Unit) = list.addView(TextView(activity).apply {
            this.text = text
            textSize = 16f
            setTextColor(0xFFEDF0F4.toInt())
            gravity = Gravity.CENTER_VERTICAL
            minHeight = dp(activity, 50)
            setPadding(dp(activity, 22), 0, dp(activity, 22), 0)
            val ripple = TypedValue().also {
                activity.theme.resolveAttribute(android.R.attr.selectableItemBackground, it, true)
            }.resourceId
            if (ripple != 0) setBackgroundResource(ripple)
            setOnClickListener { dialog.dismiss(); action() }
        })
        val server = ShellLogic.moreLinks(navLinks)
        if (server.isNotEmpty()) {
            heading("Your server")
            server.forEach { link -> row(link.name) { host.shellOpen(link.href) } }
        }
        heading("This phone")
        row("Server connection") { host.shellConnectionSettings() }
        row("Yarr account") { host.shellYarrAccount() }
        val version = try {
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName
        } catch (_: Exception) { null }
        list.addView(TextView(activity).apply {
            text = "Yarr Media for Android" + (version?.let { " $it" } ?: "")
            textSize = 12f
            setTextColor(0xFF6E7681.toInt())
            setPadding(dp(activity, 22), dp(activity, 16), dp(activity, 22), 0)
        })
        val scroller = ScrollView(activity).apply { addView(list) }
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            // Keep the last row clear of the gesture bar.
            scroller.setOnApplyWindowInsetsListener { _, insets ->
                list.setPadding(0, dp(activity, 10), 0,
                    dp(activity, 18) + insets.getInsets(android.view.WindowInsets.Type.navigationBars()).bottom)
                insets
            }
        }
        dialog.setContentView(scroller)
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setGravity(Gravity.BOTTOM)
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            attributes = attributes.apply { windowAnimations = android.R.style.Animation_InputMethod }
        }
        dialog.show()
    }
}
