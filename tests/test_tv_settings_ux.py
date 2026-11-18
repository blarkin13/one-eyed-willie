"""TV-only Settings must be legible, easy to move through, and confirm saves."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TV_SETTINGS = ROOT / "server/tv_settings.html"
TV_NATIVE = ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt"


class TvSettingsUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = TV_SETTINGS.read_text()
        cls.native = TV_NATIVE.read_text()

    def test_focus_uses_configured_selection_color_not_brightness_alone(self):
        page = self.page
        self.assertIn('html body[data-page="settings"] .tv-playback-settings', page)
        self.assertIn('outline:3px solid var(--oew-tv-select-color,#8B5CF6)!important',page)
        self.assertIn('.setting-toggle:focus-within',page)
        self.assertIn('grid-template-columns:minmax(0,1fr)',page)

    def test_remote_navigates_tv_settings_in_dom_order(self):
        native = self.native
        self.assertIn('const tvSettingsControls=()=>',native)
        self.assertIn('const moveTvSettings=(active,direction)=>',native)
        self.assertIn('if(moveTvSettings(active,direction))return true;',native)
        self.assertIn('onTvSettings?tvSettingsControls()[0]',native)

    def test_save_confirmation_is_visible_at_current_scroll_position(self):
        page = self.page
        self.assertIn('id="tv-save-toast"',page)
        self.assertIn('position:fixed;bottom:80px',page)
        self.assertIn('id="tv-remote-help"',page)
        for section in ('subtitle','color','playback','ambient'):
            self.assertIn('id="tv-'+section+'-status"',page)
        self.assertIn('kind===\'error\'?8500:4500',page)

    def test_changing_options_saves_automatically(self):
        page = self.page
        self.assertIn("el('tv-subtitles-on').addEventListener('change',saveSubtitleOnTv)",page)
        self.assertIn("void saveSelectionColor()",page)
        self.assertIn("el(id).addEventListener('change',()=>{void saveSharedPlayback()})",page)
        self.assertIn("el('tv-theme-volume').addEventListener('change'",page)
        self.assertIn("saveAmbientOnTv()",page)

    def test_remote_help_describes_focused_control(self):
        page = self.page
        self.assertIn("document.addEventListener('focusin',event=>{",page)
        self.assertIn("el('tv-focused-control').textContent=",page)
        self.assertIn("'Left / Right to adjust'",page)
        self.assertIn("'OK to toggle'",page)


if __name__ == "__main__":
    unittest.main()
