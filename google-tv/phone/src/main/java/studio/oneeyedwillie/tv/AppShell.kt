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
    private var tabBarView: View? = null
    private var playerOpen = false
    private var currentPath = "/"
    private var navLinks = emptyList<ShellLogic.NavLink>()
    private var documentStartStyle = false

    /** App-only styling, added before the page's own scripts run. Plex-like:
     *  Home is rows of posters (no hero, no changing background); libraries are
     *  a plain three-column poster grid. Only inside the phone app. */
    private val APP_CSS = """
html.yarr-app{-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%;background:#000}
html.yarr-app body{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;overscroll-behavior:none;background:#000!important}
html.yarr-app input,html.yarr-app textarea,html.yarr-app select,html.yarr-app [contenteditable="true"]{-webkit-user-select:text;user-select:text;-webkit-touch-callout:default}
html.yarr-app ::-webkit-scrollbar{display:none}
html.yarr-app .sidebar,html.yarr-app .willie-hover-backdrop,html.yarr-app #willie-ambient-effects{display:none!important}
html.yarr-app .workspace{margin:0!important}
html.yarr-app .workspace>.content{padding:16px 16px 28px!important}
html.yarr-app body[data-page="music"] .workspace>.content{padding-bottom:calc(var(--player-space,0px) + 28px)!important}
html.yarr-app #items::before,html.yarr-app .shelf-track::before,html.yarr-app .explore-grid::before,html.yarr-app .movie-grid::before,html.yarr-app .tv-grid::before{display:none!important}
html.yarr-app .cover,html.yarr-app .tile-button{transition:transform .12s ease,opacity .12s ease}
html.yarr-app .tile-button:active,html.yarr-app a:active>.cover{transform:scale(.97);opacity:.88}
html.yarr-app button:active,html.yarr-app .filter-link:active{opacity:.75}
html.yarr-app .yarr-app-bar{display:flex;align-items:center;gap:10px;height:54px;padding:0 16px}
html.yarr-app .yarr-app-bar img{width:34px;height:34px}
html.yarr-app .yarr-app-bar strong{font-size:1.3rem;font-weight:800;letter-spacing:-.02em;color:#fff}
html.yarr-app .yarr-app-switch{margin-left:auto;width:40px;height:40px;border:0;border-radius:20px;background:#1c1f24;color:#fff;display:grid;place-items:center;padding:0}
html.yarr-app .yarr-app-switch[hidden]{display:none}
html.yarr-app .yarr-app-switch svg{width:22px;height:22px}
html.yarr-app body[data-page="home"] .workspace>.content{padding:0 0 28px!important}
html.yarr-app body[data-page="home"] .home-feature{display:none!important}
html.yarr-app body[data-page="home"] .shelf{padding:0!important;margin:20px 0 0!important;height:auto!important;min-height:0!important}
html.yarr-app body[data-page="home"] .shelf>.section-heading{padding:0 16px!important;margin:0 0 10px!important}
html.yarr-app body[data-page="home"] .shelf-title{font-size:1.2rem!important;font-weight:750!important;color:#fff!important;line-height:1.3!important;margin:0!important}
html.yarr-app .yarr-shelf-link{display:inline-flex;align-items:center;gap:6px;color:#fff;text-decoration:none}
html.yarr-app .yarr-shelf-link svg{width:20px;height:20px;flex:none}
html.yarr-app body[data-page="home"] .shelf-track{display:flex;gap:8px!important;padding:0 16px 4px!important;scroll-snap-type:none!important;overscroll-behavior-x:contain;touch-action:pan-x pan-y}
html.yarr-app body[data-page="home"] .shelf-track>.tile{flex:0 0 calc((100vw - 48px)/3.15)!important;width:calc((100vw - 48px)/3.15)!important;scroll-snap-align:none!important}
html.yarr-app .tile .cover{border:0!important;border-radius:6px!important;box-shadow:none!important}
html.yarr-app body[data-page="home"] .tile-button{display:grid!important;grid-template-columns:minmax(0,1fr)}
html.yarr-app body[data-page="home"] .tile-button>.cover{grid-area:1/1}
html.yarr-app body[data-page="home"] .tile-button>.progress-track{grid-area:1/1;align-self:end;z-index:2;height:4px!important;margin:0 7px 7px!important;background:#000a!important;border-radius:3px}
html.yarr-app body[data-page="home"] .progress-fill{background:#a9ddff!important}
html.yarr-app body[data-page="home"] .progress-time,html.yarr-app body[data-page="home"] .next-episode-badge{display:none!important}
html.yarr-app .tile h3{font-size:.9rem!important;font-weight:500!important;color:#f2f2f2!important;line-height:1.3!important;margin:7px 0 1px!important;min-height:0!important;max-height:1.3em!important;display:block!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
html.yarr-app .tile .tile-meta{font-size:.78rem!important;color:#9aa0a6!important;line-height:1.3!important;min-height:0!important;max-height:1.3em!important;display:block!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;margin:0!important}
html.yarr-app .library-header-art-frame,html.yarr-app #eyebrow,html.yarr-app .library-header-icon,html.yarr-app .library-trivia,html.yarr-app #refresh-metadata,html.yarr-app #explore-library,html.yarr-app .alpha-nav{display:none!important}
html.yarr-app .library-head{min-height:0!important;height:auto!important;padding:0!important;margin:0 0 14px!important;background:none!important;border:0!important;box-shadow:none!important;overflow:visible!important}
html.yarr-app .library-head-top{display:block!important;padding:0!important;margin:0!important}
html.yarr-app .library-header-title{display:block!important;margin:0!important}
html.yarr-app #page-title{font-size:1.75rem!important;font-weight:800!important;line-height:1.2!important;margin:0 0 14px!important;color:#fff!important}
html.yarr-app .library-head-actions{display:flex!important;align-items:center!important;gap:8px!important;flex-wrap:nowrap!important;width:100%!important;margin:0!important}
html.yarr-app .library-head-actions .search-box{flex:1 1 auto!important;width:auto!important;min-width:0!important;margin:0!important}
html.yarr-app .library-head-actions .search-box input{width:100%!important;height:40px!important;border-radius:20px!important;background:#1c1f24!important;border:0!important;color:#fff!important;padding-left:40px!important;font-size:.95rem!important}
html.yarr-app .catalog-tool-icon{width:40px!important;height:40px!important;border-radius:20px!important;background:#1c1f24!important;border:0!important;color:#e8eaed!important}
html.yarr-app .catalog-tool-icon svg{width:20px!important;height:20px!important}
html.yarr-app #section-title{display:none!important}
html.yarr-app .library-head~.section-heading{margin:-6px 0 8px!important;padding:0!important;justify-content:flex-end!important;min-height:0!important}
html.yarr-app .count-label{font-size:.8rem!important;color:#9aa0a6!important}
html.yarr-app #items{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:16px 8px!important;padding:0!important}
""".trimIndent().replace("\n", "")

    /** App-only page tweaks: a title bar on Home and ">" links on its rows. */
    private val APP_JS = """
(function(){function run(){
 var b=document.body;if(!b||b.dataset.page!=='home'||document.querySelector('.yarr-app-bar'))return;
 var c=document.querySelector('.workspace>.content');if(!c)return;
 var bar=document.createElement('header');bar.className='yarr-app-bar';
 bar.innerHTML='<img src="/assets/logo.svg?v=moon-sail-v1" alt=""><strong>Yarr Media</strong>';
 c.prepend(bar);
 // Switch server: only when this account can open more than one.
 var sw=document.createElement('button');sw.type='button';sw.className='yarr-app-switch';sw.hidden=true;
 sw.setAttribute('aria-label','Switch server');
 sw.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16v5H4z"/><path d="M4 14h16v5H4z"/><path d="M8 7.5h.01"/><path d="M8 16.5h.01"/><path d="M12 7.5h5"/><path d="M12 16.5h5"/></svg>';
 sw.onclick=function(){if(window.yarrServers)window.yarrServers.open()};
 bar.append(sw);
 function show(n){sw.hidden=!(n>1)}
 if(window.yarrServers)show(window.yarrServers.count);
 window.addEventListener('yarr-servers',function(e){show(e.detail&&e.detail.count)});
 [['movies-heading','/movies'],['tv-heading','/tv'],['music-heading','/music']].forEach(function(p){
  var h=document.getElementById(p[0]);if(!h||h.closest('a'))return;
  var a=document.createElement('a');a.href=p[1];a.className='yarr-shelf-link';
  h.parentNode.insertBefore(a,h);a.appendChild(h);
  a.insertAdjacentHTML('beforeend','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>');
 });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();
 // The player covers the page: the app hides its tabs and the phone's bars meanwhile.
 if(!window.__yarrPlayerWatch){window.__yarrPlayerWatch=1;var playing=false;
  function watch(){var on=!!document.querySelector('body>.willie-player');
   if(on!==playing){playing=on;try{prompt('oewtv:shell:player:'+(on?1:0),'')}catch(_){}}}
  function start(){watch();new MutationObserver(watch).observe(document.body,{childList:true})}
  if(document.body)start();else document.addEventListener('DOMContentLoaded',start);}
})();
"""

    private val APP_SCRIPT = """(function(){
 if(window.__yarrAppShell)return;window.__yarrAppShell=1;
 var css=${JSONArray(listOf(APP_CSS)).toString().removePrefix("[").removeSuffix("]")};
 function add(){var r=document.documentElement;if(!r)return false;r.classList.add('yarr-app');
  if(document.getElementById('yarr-app-style'))return true;
  var s=document.createElement('style');s.id='yarr-app-style';s.textContent=css;(document.head||r).appendChild(s);return true}
 if(!add())new MutationObserver(function(m,o){if(add())o.disconnect()}).observe(document,{childList:true,subtree:true});
})();""" + APP_JS

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
            addView(tabBar(activity, host, web).also { tabBarView = it }, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }

    fun onPageStarted(url: String?) {
        currentPath = url?.let { Uri.parse(it).path }.orEmpty().ifEmpty { "/" }
        // A new page never starts with the player open.
        (tabBarView?.context as? Activity)?.let { setPlayerOpen(it, false) }
        refreshTabs()
    }

    fun onPageFinished(web: WebView, url: String?) {
        refresher?.isRefreshing = false
        if (!documentStartStyle) web.evaluateJavascript(APP_SCRIPT, null)
        readNav(web)
        // Library links appear once the page has asked the server which exist.
        web.postDelayed({ readNav(web) }, 1500)
    }

    /** Messages from the page (prompt bridge). True when handled. */
    fun onPrompt(activity: Activity, message: String): Boolean = when (message) {
        "oewtv:shell:player:1" -> { setPlayerOpen(activity, true); true }
        "oewtv:shell:player:0" -> { setPlayerOpen(activity, false); true }
        else -> false
    }

    /** While a video plays: no tabs, no pull-to-refresh, and the phone's bars tucked away. */
    private fun setPlayerOpen(activity: Activity, open: Boolean) {
        if (open == playerOpen) return
        playerOpen = open
        tabBarView?.visibility = if (open) View.GONE else View.VISIBLE
        refresher?.isEnabled = !open
        val bars = androidx.core.view.WindowCompat.getInsetsController(activity.window, activity.window.decorView)
        if (open) {
            bars.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        } else bars.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
    }

    /** WebView's stand-in picture before a video starts is a big grey play button: show nothing instead. */
    fun defaultVideoPoster(): android.graphics.Bitmap? =
        android.graphics.Bitmap.createBitmap(1, 1, android.graphics.Bitmap.Config.ARGB_8888)

    /** Back on a tab goes Home, Back on Home leaves the app; deeper pages go back as usual. */
    fun onBack(activity: Activity, host: ShellHost, web: WebView): Boolean {
        // Back closes the video player or minimises the full-screen music player first.
        if (playerOpen) {
            web.evaluateJavascript("if(window.yarrShellBack)window.yarrShellBack();else if(window.WilliePlayer)window.WilliePlayer.close()", null)
            return true
        }
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
