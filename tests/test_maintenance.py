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
        self.assertEqual(original["maintenance_hour"], 4)
        self.assertEqual(original["timezone"], "America/Chicago")
        self.assertIn("04:00", original["next_window"])
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

    def test_analysis_batches_advance_across_indexed_media(self):
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'TV','tv','/media/test')")
            for idx in range(1,6):
                conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns) VALUES(?,?,?,?,?,?)",
                             (idx,1,f"/media/test/{idx}.mp4",f"Video {idx}",100,1))
        first = maintenance._next_media_batch("preview", 2)
        second = maintenance._next_media_batch("preview", 2)
        third = maintenance._next_media_batch("preview", 2)
        self.assertEqual([x["id"] for x in first], [1,2])
        self.assertEqual([x["id"] for x in second], [3,4])
        self.assertEqual([x["id"] for x in third], [5,1])

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

    def test_timed_scrub_frames_are_bound_to_local_media(self):
        data = {key: False for key in maintenance.DEFAULTS}
        data["video_preview_thumbnails"] = True
        media = maintenance.DATA / "sample.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"test")
        record = {"id": 9, "size": media.stat().st_size, "mtime_ns": media.stat().st_mtime_ns}
        folder = maintenance.PREVIEWS / maintenance._preview_key(record)
        folder.mkdir(parents=True)
        for index in (5, 11, 23):
            (folder / f"{index:03}.jpg").write_bytes(b"sample")
        with patch.object(maintenance, "settings", return_value=data), \
             patch.object(maintenance, "inspect_media", return_value={"duration": 2400}), \
             patch.object(maintenance, "_item", return_value=({"id": 9}, media)), \
             patch.object(maintenance, "WORKING") as busy:
            busy.locked.return_value = True
            result = maintenance.preview_info(9)
        self.assertEqual(len(result["frames"]), 3)
        self.assertEqual(result["images"][0], result["frames"][0]["url"])
        self.assertEqual(result["frames"][0]["time_seconds"], 2400 * 6 / 25)
        self.assertEqual(result["frames"][2]["time_seconds"], 2400 * 24 / 25)
        with patch.object(maintenance, "settings", return_value=data), \
             patch.object(maintenance, "_item", return_value=({"id": 9}, media)):
            self.assertEqual(maintenance.preview_image(9, "023.jpg").media_type, "image/jpeg")
            with self.assertRaises(HTTPException):
                maintenance.preview_image(9, "024.jpg")
        self.assertTrue(maintenance._preview_complete(folder) is False)
        for index in range(maintenance.PREVIEW_FRAMES):
            (folder / f"{index:03}.jpg").write_bytes(b"sample")
        self.assertTrue(maintenance._preview_complete(folder))

    def test_maintenance_errors_do_not_mark_task_complete(self):
        enabled = {key: False for key in maintenance.DEFAULTS}
        enabled["update_all_libraries"] = True
        with patch.object(maintenance, "settings", return_value=enabled), \
             patch.object(maintenance, "_run_task", side_effect=RuntimeError("drive offline")):
            self.assertTrue(maintenance.run_due(now=2000000000))
        self.assertNotIn("update_all_libraries", maintenance.get_settings()["last_runs"])

    def test_detailed_preview_times_keep_original_frames_and_cover_timeline(self):
        self.assertEqual(maintenance.preview_times(10), [])
        times = maintenance.preview_times(7200)
        # The original 24 positions are unchanged so older apps and sets stay valid.
        self.assertEqual(times[:24], [7200 * (i + 1) / 25 for i in range(24)])
        self.assertGreater(len(times), 300)
        self.assertEqual(len(times), len(set(times)))
        self.assertTrue(all(0 < t < 7200 for t in times))
        # Coarse-to-fine: the first detailed frames already span the whole video.
        early = sorted(times[24:44])
        self.assertLess(early[0], 1200)
        self.assertGreater(early[-1], 5500)
        # Bounded work for very long videos, and dense for short ones.
        self.assertLessEqual(len(maintenance.preview_times(6 * 3600)), 24 + maintenance.PREVIEW_MAX_EXTRA)
        short = sorted(maintenance.preview_times(1200))
        self.assertLessEqual(max(b - a for a, b in zip(short, short[1:])), 60)

    def test_preview_info_uses_manifest_times_and_reports_total(self):
        data = {key: False for key in maintenance.DEFAULTS}
        data["video_preview_thumbnails"] = True
        media = maintenance.DATA / "long.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"test")
        record = {"id": 4, "size": media.stat().st_size, "mtime_ns": media.stat().st_mtime_ns}
        folder = maintenance.PREVIEWS / maintenance._preview_key(record)
        folder.mkdir(parents=True)
        times = maintenance.preview_times(7200)
        maintenance._save_times(folder, times)
        for index in (0, 24, 25, 398):
            (folder / f"{index:03}.jpg").write_bytes(b"sample")
        with patch.object(maintenance, "settings", return_value=data), \
             patch.object(maintenance, "inspect_media", return_value={"duration": 7200}), \
             patch.object(maintenance, "_item", return_value=({"id": 4}, media)), \
             patch.object(maintenance, "WORKING") as busy:
            busy.locked.return_value = True
            result = maintenance.preview_info(4)
            self.assertEqual(result["total_frames"], len(times))
            self.assertEqual([f["time_seconds"] for f in result["frames"]],
                             [times[0], times[24], times[25], times[398]])
            self.assertEqual(maintenance.preview_image(4, "398.jpg").media_type, "image/jpeg")
            with self.assertRaises(HTTPException):
                maintenance.preview_image(4, "999.jpg")

    def test_legacy_24_frame_set_is_topped_up_not_regenerated(self):
        media = maintenance.DATA / "legacy.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"test")
        row = {"id": 6, "size": media.stat().st_size, "mtime_ns": media.stat().st_mtime_ns}
        folder = maintenance.PREVIEWS / maintenance._preview_key(row)
        folder.mkdir(parents=True)
        for index in range(24):
            (folder / f"{index:03}.jpg").write_bytes(b"old")
        made = []

        def fake_ffmpeg(command, **kwargs):
            made.append(command)
            Path(command[-1]).write_bytes(b"new")

        with patch.object(maintenance, "_safe_media", return_value=media), \
             patch.object(maintenance, "_probe", return_value={"duration": 3600}), \
             patch.object(maintenance.subprocess, "run", side_effect=fake_ffmpeg):
            self.assertTrue(maintenance._create_preview(row))
        times = maintenance._load_times(folder)
        self.assertEqual(len(made), len(times) - 24)       # only the missing frames
        self.assertEqual((folder / "000.jpg").read_bytes(), b"old")
        self.assertTrue(maintenance._preview_complete(folder))
        with patch.object(maintenance, "_safe_media", return_value=media):
            self.assertFalse(maintenance._create_preview(row))   # nothing left to do


if __name__ == "__main__":
    unittest.main()
