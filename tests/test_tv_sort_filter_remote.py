"""Google TV D-pad must operate visible Sort/Filter popup options.

The server's catalog already builds a remote-friendly menu; the native
WebView's own D-pad router must recognize it instead of moving page focus.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt"
CATALOG = ROOT / "server/catalog.html"


class TvSortFilterNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.catalog = CATALOG.read_text()

    def test_open_catalog_menu_captures_dpad(self):
        native = self.native
        self.assertIn("const menu=document.querySelector(\n"
                      "                  'dialog[open],.season-more-popover,.catalog-tool-menu:not([hidden])'",
                      native)
        self.assertIn("const options=menu.matches('.catalog-tool-menu')", native)
        self.assertIn("menu.querySelectorAll('.catalog-tool-option:not(:disabled)')", native)
        self.assertIn("if(direction==='up'||direction==='down'){", native)
        self.assertIn("return focusNode(options[next]);", native)
        self.assertIn("if(!options.length)return true;", native)

    def test_scrolling_tall_filter_menu_does_not_scroll_page_behind_it(self):
        native = self.native
        self.assertIn("'dialog[open],.season-more-popover,.catalog-tool-menu:not([hidden])'",
                      native)
        self.assertIn("const modal=node.closest(", native)
        self.assertIn("glideTo(scroller,'top'", native)
        self.assertIn("if(modal){", native)

    def test_selected_sort_or_filter_button_is_remote_clickable(self):
        native = self.native
        catalog = self.catalog
        self.assertIn("node.matches?.('a[href],button,[role=\"button\"]", native)
        self.assertIn("node.click();return true", native)
        self.assertIn("button.setAttribute('role','menuitemradio')", catalog)
        self.assertIn("button.addEventListener('click',()=>{", catalog)
        self.assertIn("select.value=option.value", catalog)
        self.assertIn("menu.hidden=false;", catalog)
        self.assertIn(".catalog-tool-option:is(:focus,:focus-visible)", catalog)
        self.assertIn("var(--oew-tv-select-color,#8B5CF6)", catalog)

    def test_closed_catalog_menus_are_not_treated_as_active(self):
        native = self.native
        catalog = self.catalog
        self.assertIn(".catalog-tool-menu:not([hidden])", native)
        self.assertIn(".catalog-tool-menu[hidden]{display:none!important}",catalog)
        self.assertIn("if(menu.hidden)return;",catalog)
        self.assertIn("closeCatalogMenu(id,true)",catalog)


if __name__ == "__main__":
    unittest.main()
