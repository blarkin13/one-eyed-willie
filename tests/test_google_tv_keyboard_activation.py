"""TV keyboard opens only on explicit selection of a text field."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = ROOT / "google-tv" / "app" / "src" / "main" / "java" / "studio" / "oneeyedwillie" / "tv" / "MainActivity.kt"


class TvTextInputFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ACTIVITY.read_text()

    def test_dpad_focus_is_not_edit_activation(self):
        src = self.source
        self.assertIn("window.__oewTvInputGateInstalled=true", src)
        self.assertIn("node.readOnly=true;", src)
        self.assertIn("protectedFields.add(node)", src)
        self.assertIn("document.addEventListener('focusin',event=>{", src)
        self.assertIn("new MutationObserver(records=>", src)
        self.assertIn("const focusNode=node=>{", src)
        self.assertIn("node.focus({preventScroll:true});", src)
        self.assertIn("window.__willieTvEndTextEdit=endEditing", src)

    def test_explicit_select_or_click_enables_keyboard(self):
        src = self.source
        self.assertIn("document.addEventListener('keydown',event=>{", src)
        self.assertIn("['Enter',' '].includes(event.key)", src)
        self.assertIn("document.addEventListener('click',event=>{", src)
        self.assertIn("field.readOnly=false", src)
        self.assertIn("field.blur();", src)
        self.assertIn("field.focus({preventScroll:true});", src)
        self.assertIn("notify('begin');", src)
        self.assertIn('message == "oewtv:edit:begin"', src)
        self.assertIn("showSoftInput(web, InputMethodManager.SHOW_IMPLICIT)", src)
        self.assertIn("web.postDelayed({", src)

    def test_back_and_blur_restore_navigation_without_leaving_page(self):
        src = self.source
        self.assertIn("if (tvTextEditing) {\n                    finishTvTextEditing(web)", src)
        self.assertIn("if (tvTextEditing) return super.dispatchKeyEvent(event)", src)
        self.assertNotIn("if(!refocusing&&event.target===editingField)endEditing();", src)
        self.assertIn("Do NOT end editing on focusout", src)
        self.assertIn("if(editingField && event.target!==editingField", src)
        self.assertIn("field.readOnly=true", src)
        self.assertIn("notify('end');", src)
        self.assertIn("hideSoftInputFromWindow(web.windowToken, 0)", src)
        self.assertIn("tvTextEditing = false", src)

    def test_new_pages_initially_focus_content_not_sidebar(self):
        src = self.source
        self.assertIn("const settleInitialFocus=()=>{", src)
        self.assertIn("firstPoster()", src)
        self.assertIn("destination.focus({preventScroll:true})", src)
        self.assertIn("if(!settleInitialFocus())", src)

    def test_library_search_leaves_text_mode_for_sidebar_and_posters(self):
        src = self.source
        self.assertIn('librarySearchPage && direction in listOf("left", "down")', src)
        self.assertIn('finishTvTextEditing(web)', src)
        self.assertIn("window.__willieTvExitLibrarySearch", src)
        self.assertIn("if(direction==='left'){", src)
        self.assertIn("if(direction==='down'){", src)
        self.assertIn("return focusNode(selected)", src)
        self.assertIn("return focusNode(target)", src)

    def test_closed_sidebar_still_accepts_dpad_left_navigation(self):
        src = self.source
        self.assertIn("const allMenu=()=>[...document.querySelectorAll('#app-nav .side-nav .nav-link')]", src)
        self.assertNotIn("const allMenu=()=>[...document.querySelectorAll('#app-nav .side-nav .nav-link')].filter(isVisible)", src)
        self.assertIn("Closed TV rail uses pointer-events:none", src)
        self.assertIn("getComputedStyle(node).display!=='none'", src)
        self.assertIn("document.body.classList.toggle('oew-tv-rail-open',isMenu(node))", src)
        self.assertIn("if(direction==='left'){", src)
        self.assertIn("if(menu.length)return focusNode(", src)
        self.assertIn("if(isMenu(active)){", src)
        self.assertIn("if(direction==='right'){", src)

    def test_native_connection_setup_requires_click(self):
        src = self.source
        self.assertIn("showSoftInputOnFocus = false", src)
        self.assertIn("setOnClickListener {\n                showSoftInputOnFocus = true", src)
        self.assertIn("if (!focused) showSoftInputOnFocus = false", src)

    def test_fullscreen_ime_onpause_does_not_close_keyboard(self):
        src = self.source
        start = src.index("    override fun onPause()")
        end = src.index("    override fun onDestroy()", start)
        pause = src[start:end]
        self.assertNotIn("finishTvTextEditing", pause)
        self.assertIn("super.onPause()", pause)

    def test_sidebar_hidden_before_first_paint_and_explicitly_reopened(self):
        src = self.source
        stylesheet = (ROOT / "server" / "main.py").read_text()
        self.assertIn('OneEyedWillieTV/1', src)
        self.assertIn('OneEyedWillieTV/1', stylesheet)
        self.assertIn("body .sidebar,body .sidebar:hover,body .sidebar:focus-within", stylesheet)
        self.assertIn("transform:translateX(-120%)!important", stylesheet)
        self.assertIn("body.oew-tv-rail-open .sidebar", stylesheet)
        self.assertIn("document.body.classList.toggle('oew-tv-rail-open',isMenu(node))", src)
        self.assertIn("document.body.classList.remove('oew-tv-rail-open')", src)

    def test_ship_loading_screen_runs_only_at_initial_connection(self):
        src = self.source
        self.assertIn("private var initialPageLoaded = false", src)
        self.assertIn("if (initialPageLoaded) return", src)
        self.assertIn("initialPageLoaded = true", src)
        self.assertIn("!initialPageLoaded)", src)
        self.assertIn("if (browser === web && sameOrigin(url.orEmpty()) && !initialPageLoaded)", src)

    def test_search_ime_stays_active_during_transient_focus_changes(self):
        self.assertIn("window.__willieTvRefocusText", self.source)
        self.assertIn("ime.restartInput(web)", self.source)
        self.assertIn("ime.showSoftInput(web", self.source)
        self.assertIn("Only Back, deliberate remote navigation or an", self.source)

    def test_library_horizontal_movement_is_level_and_up_reaches_toolbar(self):
        self.assertIn("const moveLibraryHorizontal=(active,direction)=>", self.source)
        self.assertIn("focusNode(row[next],{preserveVertical:true})", self.source)
        self.assertIn("const moveLibraryToolbar=(active,direction)=>", self.source)
        self.assertIn("glideTo(document.scrollingElement||document.documentElement,'top',0)", self.source)
        self.assertIn("if(moveLibraryToolbar(active,direction))return true;", self.source)

    def test_library_return_restores_header_and_retains_selected_backdrop(self):
        src = self.source
        self.assertIn("const firstRowTop=Math.min(...rows.map(row=>row.top))", src)
        self.assertIn("if(Math.abs(rowTop-firstRowTop)<15)", src)
        self.assertIn("glideTo(root,'top',0);", src)
        self.assertIn("focusNode(target,{preserveVertical:true})", src)
        self.assertIn("event.target?.closest?.('#library-masthead .library-head-actions')", src)
        shell = (ROOT / "server" / "shell.js").read_text()
        self.assertIn("const onLibraryToolbar=target=>", shell)
        self.assertIn("else if(!onLibraryToolbar(document.activeElement))select(null);", shell)
        catalog = (ROOT / "server" / "catalog.html").read_text()
        self.assertIn('shell.js?v=library-backdrop-2', catalog)

    def test_tv_switches_pages_without_exposing_unpopulated_content(self):
        source = self.source
        self.assertIn("private fun captureNavigationStill(web: WebView, target: Uri)", source)
        self.assertIn("web.draw(android.graphics.Canvas(bitmap))", source)
        self.assertIn("target.path !in setOf(\"/\", \"/movies\", \"/tv\")", source)
        self.assertIn("override fun onPageCommitVisible(web: WebView, url: String?)", source)
        self.assertIn("releaseNavigationStill()", source)
        self.assertIn("setDuration(180L)", source)
        self.assertIn("translationX(-dp(12).toFloat())", source)
        self.assertIn("480L", source)
        self.assertNotIn("revealPopulatedPage", source)
        self.assertNotIn("5500L", source)

    def test_library_title_icons_are_large_but_sidebar_icons_unchanged(self):
        catalog = (ROOT / "server" / "catalog.html").read_text()
        self.assertIn("width:76px;height:76px", catalog)
        self.assertIn("className='library-page-icon'", catalog)
        self.assertIn("libraryAppearance.createIcon(iconKey,76)", catalog)
        self.assertIn("width:60px;height:60px", catalog)

    def test_non_text_inputs_are_unaffected(self):
        src = self.source
        self.assertIn("['text','search','email','password','tel','url','number']", src)
        self.assertNotIn("node.disabled=true", src)


if __name__ == "__main__":
    unittest.main()
