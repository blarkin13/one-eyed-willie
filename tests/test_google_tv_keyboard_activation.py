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

    def test_native_connection_setup_requires_click(self):
        src = self.source
        self.assertIn("showSoftInputOnFocus = false", src)
        self.assertIn("setOnClickListener {\n                showSoftInputOnFocus = true", src)
        self.assertIn("if (!focused) showSoftInputOnFocus = false", src)

    def test_non_text_inputs_are_unaffected(self):
        src = self.source
        self.assertIn("['text','search','email','password','tel','url','number']", src)
        self.assertNotIn("node.disabled=true", src)


if __name__ == "__main__":
    unittest.main()
