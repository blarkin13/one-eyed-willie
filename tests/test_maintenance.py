import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import library, maintenance


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for obj, field, value in [
            (library, "DB_PATH", root / "library.sqlite3"),
            (maintenance, "DATA", root / "maintenance"),
            (maintenance, "PREVIEWS", root / "maintenance/previews"),
            (maintenance, "MANAGED_BUNDLES", root / "maintenance/bundles"),
        ]:
            p = patch.object(obj, field, value)
            p.start()
            self.addCleanup(p.stop)

    def test_default_schedule_and_persistence(self):
        original = maintenance.get_settings()
        self.assertTrue(original["settings"]["video_preview_thumbnails"])
        self.assertEqual(original["cadence_seconds"]["refresh_local_metadata"], 3*86400)
        self.assertEqual(original["cadence_seconds"]["optimize_database"], 7*86400)
        values = {key: False for key in maintenance.DEFAULTS}
        values["update_all_libraries"] = True
        response = maintenance.update_settings(maintenance.Settings(**values))
        self.assertTrue(response["settings"]["update_all_libraries"])
        self.assertFalse(response["settings"]["video_preview_thumbnails"])
        self.assertFalse(maintenance.settings()["optimize_database"])

    def test_only_due_jobs_run_and_status_is_retained(self):
        enabled = {key: False for key in maintenance.DEFAULTS}
        enabled["remove_old_bundles"] = True
        with patch.object(maintenance, "settings", return_value=enabled), \
             patch.object(maintenance, "_run_task", return_value="cleaned") as task:
            self.assertTrue(maintenance.run_due(now=2000000000))
            self.assertTrue(maintenance.run_due(now=2000000060))
            task.assert_called_once_with("remove_old_bundles")
            self.assertTrue(maintenance.run_due(now=2000000000 + maintenance.WEEK))
            self.assertEqual(task.call_count, 2)
        self.assertEqual(maintenance.get_settings()["last_runs"]["remove_old_bundles"]["last_result"], "cleaned")

    def test_cleanup_never_follows_symlinks_and_ignores_new_files(self):
        root = maintenance.DATA / "bundles"
        root.mkdir(parents=True)
        external = maintenance.DATA / "keep"
        external.write_text("important")
        (root / "link").symlink_to(external)
        current = root / "new.bundle"
        current.write_text("new")
        old = root / "old.bundle"
        old.write_text("old")
        ago = time.time() - maintenance.WEEK * 2
        import os
        os.utime(old, (ago, ago))
        self.assertEqual(maintenance._safe_clean(root, time.time()-maintenance.WEEK), 1)
        self.assertTrue(current.exists())
        self.assertTrue(external.exists())
        self.assertTrue((root / "link").is_symlink())

    def test_preview_setting_disables_generation(self):
        data = {key: False for key in maintenance.DEFAULTS}
        with patch.object(maintenance, "settings", return_value=data):
            with self.assertRaises(HTTPException) as error:
                maintenance.start_preview_generation()
        self.assertEqual(error.exception.status_code, 409)

    def test_preview_urls_are_bound_to_indexed_media(self):
        data = {key: False for key in maintenance.DEFAULTS}
        data["video_preview_thumbnails"] = True
        movie = maintenance.DATA / "movie.mp4"
        movie.parent.mkdir(parents=True)
        movie.write_bytes(b"abc")
        with patch.object(maintenance, "settings", return_value=data), \
             patch.object(maintenance, "_item", return_value=({"id": 2}, movie)):
            self.assertEqual(maintenance.preview_info(2)["images"], [])
            record = {"id": 2, "size": movie.stat().st_size, "mtime_ns": movie.stat().st_mtime_ns}
            dest = maintenance.PREVIEWS / maintenance._preview_key(record)
            dest.mkdir(parents=True)
            (dest/"000.jpg").write_bytes(b"\xff\xd8\xff" + b"x"*10)
            urls = maintenance.preview_info(2)["images"]
            self.assertEqual(len(urls), 1)
            self.assertEqual(maintenance.preview_image(2, "000.jpg").media_type, "image/jpeg")
            with self.assertRaises(HTTPException):
                maintenance.preview_image(2, "../x")

    def test_maintenance_errors_do_not_mark_task_complete(self):
        enabled = {key: False for key in maintenance.DEFAULTS}
        enabled["update_all_libraries"] = True
        with patch.object(maintenance, "settings", return_value=enabled), \
             patch.object(maintenance, "_run_task", side_effect=RuntimeError("drive offline")):
            self.assertTrue(maintenance.run_due(now=2000000000))
        self.assertNotIn("update_all_libraries", maintenance.get_settings()["last_runs"])


if __name__ == "__main__":
    unittest.main()
