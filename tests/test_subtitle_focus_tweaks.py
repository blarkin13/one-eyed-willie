"""Caption style preferences and remote-focus playback regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from server import library
from server.subtitle_settings import (
    SubtitleAppearance, get_subtitle_appearance, save_subtitle_appearance
)

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt"
PLAYER = ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt"
TV_SETTINGS = ROOT / "server/tv_settings.html"
TV_DETAILS = ROOT / "server/tv_detail.html"
WEB_PLAYER = ROOT / "server/player.js"
CSS = ROOT / "server/ui.css"


class SubtitleStyleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(folder.name) / "test.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_has_no_black_box(self):
        self.assertEqual(get_subtitle_appearance(), {
            "background": "none", "size": "normal",
            "color": "white", "outline": True
        })

    def test_persistence_across_page_loads(self):
        style = SubtitleAppearance(background="75", size="large",
                                   color="yellow", outline=False)
        self.assertEqual(save_subtitle_appearance(style), style.model_dump())
        self.assertEqual(get_subtitle_appearance(), style.model_dump())

    def test_reject_unsupported_style(self):
        for style in ({"background": "black"}, {"size": "huge"},
                      {"color": "red"}):
            with self.assertRaises(ValidationError):
                SubtitleAppearance(**style)

    def test_native_subtitles_have_adjustable_background_and_size(self):
        player = PLAYER.read_text()
        main = MAIN.read_text()
        tv = TV_SETTINGS.read_text()
        for marker in ("setApplyEmbeddedStyles(false)", "CaptionStyleCompat(",
                       'prefs.getString("background", "none")',
                       'prefs.getString("size", "normal")'):
            self.assertIn(marker, player)
        for marker in ('"oewtv:subtitles:get"', '"oewtv:subtitles:set"',
                       '.putString("background", background)', '.putString("size", size)'):
            self.assertIn(marker, main)
        for marker in ("tv-subtitle-background", "tv-subtitle-size",
                       "tv-subtitle-color", "tv-subtitle-outline"):
            self.assertIn(marker, tv)

    def test_select_pauses_video_but_leaves_focused_buttons_working(self):
        player = PLAYER.read_text()
        self.assertIn('val controlsHidden = chrome.visibility != View.VISIBLE', player)
        self.assertIn('focused === timeline', player)
        self.assertIn('if (controlsHidden || videoSelected || focused === playButton)', player)
        self.assertIn('if (active?.isPlaying == true) active.pause() else active?.play()', player)

    def test_poster_and_episode_focus_ring_is_thin(self):
        main = MAIN.read_text()
        css = CSS.read_text()
        self.assertIn("2px var(--oew-tv-select-color", main)
        self.assertIn("2px var(--oew-tv-select-color", css)
        self.assertIn(".season-episode-tile:is(:focus,:focus-visible)", main)

    def test_episode_selection_updates_play_and_resume_buttons(self):
        main = MAIN.read_text()
        detail = TV_DETAILS.read_text()
        self.assertIn("document.getElementById('season-resume-button')||", main)
        self.assertIn("actions.dataset.selectedEpisodeId", detail)
        self.assertIn("Play '+epTitle.textContent+' from beginning", detail)
        self.assertIn("Resume '+epTitle.textContent+' from saved position", detail)

    def test_browser_cues_can_be_transparent(self):
        src = WEB_PLAYER.read_text()
        self.assertIn("willie-subtitle-appearance", src)
        self.assertIn("'.willie-video::cue{background-color:rgba(0,0,0,'", src)
        self.assertIn("requestJson('/api/settings/subtitle-appearance')", src)


if __name__ == "__main__":
    unittest.main()
