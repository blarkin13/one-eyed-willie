"""Time Adrift server accounting, idempotency and player-integration regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from server import library, time_adrift

ROOT = Path(__file__).resolve().parents[1]


class TimeAdriftTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db_patch = patch.object(library, "DB_PATH", Path(folder.name) / "test.sqlite3")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies','/media/movies')"
            )
            conn.executemany(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns) VALUES(?,?,?,?,?,?)",
                [(101, 1, "/media/movies/one.mp4", "One", 100, 1),
                 (102, 1, "/media/movies/two.mp4", "Two", 100, 1)]
            )

    def event(self, event_id, kind, seconds, media_id=101):
        return time_adrift.record_event(
            media_id, time_adrift.TimeAdriftEvent(
                event_id=event_id, kind=kind, seconds=seconds)
        )

    def test_disabled_by_default_and_not_recording(self):
        self.assertEqual(time_adrift.get_settings(), {"enabled": False})
        result = self.event("a" * 24, "pause", 12)
        self.assertFalse(result["enabled"])
        self.assertEqual(result["paused_seconds"], 0)
        self.assertEqual(result["pause_count"], 0)

    def test_persistence_per_video_and_duplicate_events(self):
        self.assertEqual(time_adrift.save_settings(
            time_adrift.TimeAdriftSettings(enabled=True)), {"enabled": True})
        first = self.event("a" * 24, "pause", 83.125)
        self.assertEqual(first["paused_seconds"], 83.125)
        again = self.event("a" * 24, "pause", 83.125)
        self.assertEqual(again["paused_seconds"], 83.125)
        self.assertEqual(again["pause_count"], 1)
        second = self.event("b" * 24, "rewind", 16.5)
        self.assertEqual(second["rewound_seconds"], 16.5)
        self.assertEqual(second["rewind_count"], 1)
        self.assertEqual(time_adrift.get_media_totals(102)["paused_seconds"], 0)
        self.assertEqual(time_adrift.get_media_totals(101)["paused_seconds"], 83.125)
        self.assertEqual(time_adrift.get_settings(), {"enabled": True})

    def test_disable_preserves_earlier_totals(self):
        time_adrift.save_settings(time_adrift.TimeAdriftSettings(enabled=True))
        self.event("a" * 24, "pause", 5)
        time_adrift.save_settings(time_adrift.TimeAdriftSettings(enabled=False))
        self.event("b" * 24, "rewind", 30)
        totals = time_adrift.get_media_totals(101)
        self.assertFalse(totals["enabled"])
        self.assertEqual(totals["paused_seconds"], 5)
        self.assertEqual(totals["rewound_seconds"], 0)

    def test_bad_events_and_unknown_media_are_rejected(self):
        with self.assertRaises(ValidationError):
            time_adrift.TimeAdriftEvent(event_id="bad", kind="pause", seconds=5)
        with self.assertRaises(ValidationError):
            time_adrift.TimeAdriftEvent(event_id="c" * 24, kind="seek", seconds=5)
        with self.assertRaises(ValidationError):
            time_adrift.TimeAdriftEvent(event_id="d" * 24, kind="rewind", seconds=-5)
        with self.assertRaises(HTTPException) as caught:
            time_adrift.get_media_totals(99)
        self.assertEqual(caught.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            self.event("e" * 24, "pause", 12, media_id=99)

    def test_settings_web_and_native_player_wiring(self):
        ui = (ROOT / "server/arr_connections.html").read_text()
        browser = (ROOT / "server/player.js").read_text()
        tv = (ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()
        hub = (ROOT / "server/connections_hub.html").read_text()
        self.assertIn('data-connection-id="time-adrift"', ui)
        self.assertIn('id="time-adrift-enabled"', ui)
        self.assertIn("/api/time-adrift/settings", ui)
        self.assertIn("time-adrift-overlay", browser)
        self.assertIn("if(!forceRestart&&before!==null&&desired<before-0.5)", browser)
        self.assertIn("adriftPauseAt=Date.now()", browser)
        self.assertIn("private fun loadTimeAdrift()", tv)
        self.assertIn('saveAdriftEvent("rewind", before - target)', tv)
        self.assertIn("Gravity.TOP or Gravity.RIGHT", tv)
        self.assertIn("'/api/time-adrift/settings'", hub)


if __name__ == "__main__":
    unittest.main()
