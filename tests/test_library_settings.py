"""Persistent library editing, multi-folder scanning and safe sidebar settings."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import library, sidebar_settings
from server.catalog import catalog
from server.tv import local_show


class LibrarySettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.media = self.root / "media"
        self.first = self.media / "TV"
        self.second = self.media / "Other TV"
        self.first.mkdir(parents=True)
        self.second.mkdir(parents=True)
        self.first_episode = self.first / "The Show" / "Season 1" / "The.Show.S01E01.mkv"
        self.second_episode = self.second / "The Show" / "Season 2" / "The.Show.S02E01.mkv"
        for episode in [self.first_episode, self.second_episode]:
            episode.parent.mkdir(parents=True)
            episode.write_bytes(b"fake episode")
        for target, name, val in (
            (library, "DB_PATH", self.root / "db.sqlite"),
            (library, "MEDIA_ROOT", self.media),
        ):
            p = patch.object(target, name, val)
            p.start()
            self.addCleanup(p.stop)

    def create(self):
        return library.create_library(library.LibraryRequest(
            name="TV Shows", kind="tv", path=str(self.first)
        ))

    def test_old_single_folder_data_is_backfilled(self):
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(10,'Legacy','tv',?)",
                (str(self.first),),
            )
        result = library.libraries()
        self.assertEqual(result[0]["folders"][0]["path"], str(self.first))
        self.assertEqual(result[0]["font"], "default")
        self.assertEqual(result[0]["icon"], "folder")

    def test_edit_library_and_scan_multiple_roots_without_losing_episode_grouping(self):
        lib = self.create()
        updated = library.update_library(lib["id"], library.LibraryEdit(
            name="All My Shows", icon="star", font="serif", sidebar_hidden=True,
        ))
        self.assertEqual(updated["name"], "All My Shows")
        self.assertEqual(updated["icon"], "star")
        self.assertEqual(updated["font"], "serif")
        self.assertTrue(updated["sidebar_hidden"])
        library.add_library_folder(lib["id"], library.FolderRequest(path=str(self.second)))
        scanned = library.scan_library(lib["id"])
        self.assertEqual(scanned["found"], 2)
        groups = catalog(kind="tv", library_id=lib["id"])
        self.assertEqual(groups["total"], 1)
        self.assertEqual(len(groups["items"][0]["episodes"]), 2)
        show = local_show(lib["id"], groups["items"][0]["key"])
        self.assertEqual({x["season"] for x in show["episodes"]}, {1, 2})
        with library.db() as conn:
            paths = {(row["path"], row["source_root"]) for row in conn.execute(
                "SELECT path,source_root FROM media ORDER BY path")}
        self.assertIn((str(self.first_episode), str(self.first)), paths)
        self.assertIn((str(self.second_episode), str(self.second)), paths)

    def test_unsafe_overlaps_and_last_folder_are_rejected(self):
        first = self.create()
        with self.assertRaises(HTTPException) as same:
            library.add_library_folder(first["id"], library.FolderRequest(path=str(self.first)))
        self.assertEqual(same.exception.status_code, 409)
        with self.assertRaises(HTTPException) as nested:
            library.add_library_folder(first["id"], library.FolderRequest(
                path=str(self.first_episode.parent)))
        self.assertEqual(nested.exception.status_code, 409)
        folder_id = first["folders"][0]["id"]
        with self.assertRaises(HTTPException) as last:
            library.remove_library_folder(first["id"], folder_id)
        self.assertEqual(last.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            library.update_library(first["id"], library.LibraryEdit(
                name="Bad",icon="<img>",font="default"
            ))

    def test_remove_secondary_folder_preserves_files_and_legacy_watch_history_until_scan(self):
        lib = self.create()
        extra = library.add_library_folder(lib["id"], library.FolderRequest(path=str(self.second)))
        library.scan_library(lib["id"])
        with library.db() as conn:
            row = conn.execute("SELECT id FROM media WHERE path=?", (str(self.second_episode),)).fetchone()
            watched_id = row["id"]
            conn.execute("INSERT INTO playback_progress(media_id,position_seconds,duration_seconds) "
                         "VALUES(?,?,?)",(watched_id,100,1000))
        folder_id = next(x["id"] for x in extra["folders"] if x["path"] == str(self.second))
        library.remove_library_folder(lib["id"], folder_id)
        self.assertTrue(self.second_episode.is_file())
        with library.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM playback_progress WHERE media_id=?",
                                         (watched_id,)).fetchone()[0], 1)
        library.scan_library(lib["id"])
        with library.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM media WHERE id=?",
                                         (watched_id,)).fetchone()[0], 0)

    def test_sidebar_order_visibility_and_invalid_ids(self):
        first = self.create()
        original = sidebar_settings.get_sidebar()
        items = original["items"]
        self.assertIn("library:"+str(first["id"]), original["order"])
        order = [x["id"] for x in items]
        order.remove("library:"+str(first["id"]))
        order.insert(1,"library:"+str(first["id"]))
        result = sidebar_settings.update_sidebar(sidebar_settings.SidebarRequest(
            order=order,hidden=["sabnzbd","library:"+str(first["id"])]
        ))
        self.assertEqual(result["order"], order)
        self.assertIn("sabnzbd", result["hidden"])
        self.assertTrue(next(x for x in library.libraries() if x["id"]==first["id"])["sidebar_hidden"])
        # The API stores library visibility with the library itself.
        # It is reflected in the GET list after committing the update.
        self.assertFalse(next(x for x in result["items"] if x["id"]=="library:"+str(first["id"]))["visible"])
        with self.assertRaises(HTTPException):
            sidebar_settings.update_sidebar(sidebar_settings.SidebarRequest(
                order=order,hidden=["settings"]
            ))


if __name__ == "__main__":
    unittest.main()
