"""Static regression checks for icon-only library sorting and genre filtering."""
import unittest
from pathlib import Path
from html.parser import HTMLParser

SERVER = Path(__file__).resolve().parents[1] / "server"


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attributes = {}
        self.entries = {}
    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if "id" in props:
            self.attributes[props["id"]] = (tag, props)
        if tag == "option":
            self.entries.setdefault("option", []).append(props)


class CatalogToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (SERVER / "catalog.html").read_text()
        cls.markup = Controls()
        cls.markup.feed(cls.page)

    def test_only_compact_icons_visible_instead_of_selects(self):
        page = self.page
        elements = self.markup.attributes
        self.assertIn('id="sort" hidden', page)
        self.assertIn('id="genre" hidden', page)
        for key in ("sort", "genre"):
            self.assertEqual(elements[key][0], "select")
            self.assertEqual(elements[key + "-toggle"][0], "button")
            self.assertEqual(elements[key + "-menu"][0], "div")
            self.assertEqual(elements[key + "-toggle"][1]["aria-haspopup"], "menu")
            self.assertEqual(elements[key + "-toggle"][1]["aria-expanded"], "false")
            self.assertEqual(elements[key + "-toggle"][1]["aria-controls"], key + "-menu")
            self.assertEqual(elements[key + "-menu"][1]["role"], "menu")
            self.assertTrue("hidden" in elements[key + "-menu"][1])
        self.assertNotIn('class="sort-wrapper"', page)
        self.assertNotIn('class="genre-wrapper"', page)
        for value in ("title", "added", "length", "rating"):
            self.assertIn('value="' + value + '"', page)
        self.assertIn('All Genres', page)

    def test_dropdown_uses_actual_catalog_genres(self):
        page = self.page
        self.assertIn("updateGenreChoices(data.genres);", page)
        self.assertIn("for(const option of select.options)", page)
        self.assertIn("button.setAttribute('role','menuitemradio')", page)
        self.assertIn("button.setAttribute('aria-checked',String(option.selected))", page)
        self.assertIn("selectedGenre=option.value;select.value=option.value;", page)
        self.assertIn("closeCatalogMenu(id,true);setMenuLabels();load();", page)
        self.assertIn("if(selectedGenre)params.set('genre',selectedGenre);", page)
        self.assertIn("sort:$('sort').value", page)

    def test_remote_and_outside_click_navigation(self):
        page = self.page
        for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape", "ArrowLeft", "ArrowRight"):
            self.assertIn(key, page)
        self.assertIn("event.stopImmediatePropagation()", page)
        self.assertIn("event.target.closest('.catalog-menu-anchor')", page)
        self.assertIn("closeCatalogMenu(openId,true)", page)
        self.assertIn("focus({preventScroll:true})", page)

    def test_catalog_popovers_render_above_poster_grid(self):
        # '#items' creates its own isolated stacking context in ui.css.
        # The menu's z-index is ineffective unless its masthead is above it.
        import re
        masthead = re.search(r"\\.library-head\\{([^}]*)\\}", self.page, re.S)
        menu = re.search(r"\\.catalog-tool-menu\\{([^}]*)\\}", self.page, re.S)
        self.assertIsNotNone(masthead)
        self.assertIsNotNone(menu)
        self.assertIn("position:relative", masthead.group(1))
        self.assertIn("isolation:isolate", masthead.group(1))
        self.assertIn("z-index:20", masthead.group(1))
        self.assertIn("overflow:visible", masthead.group(1))
        self.assertIn("z-index:45", menu.group(1))
        styles = (SERVER / "ui.css").read_text()
        self.assertIn("#items,.shelf-track,.explore-grid,.movie-grid,.tv-grid{position:relative;isolation:isolate}", styles)

    def test_open_menu_and_selected_filter_visuals(self):
        page = self.page
        self.assertIn(".catalog-tool-menu[hidden]{display:none!important}", page)
        self.assertIn(".catalog-tool-icon.is-active", page)
        self.assertIn(".catalog-tool-option[aria-checked=true]", page)
        self.assertIn(".catalog-tool-dot", page)
        self.assertIn("id==='sort'?sort.value!=='title':Boolean(selectedGenre)", page)
        self.assertIn("role=\"group\" aria-label=\"Browse library controls\"", page)
        self.assertIn("id=\"refresh-metadata\"", page)
        self.assertIn("id=\"explore-library\"", page)


if __name__ == "__main__":
    unittest.main()
