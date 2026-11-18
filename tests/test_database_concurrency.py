"""db() must not queue behind writers, and must use the fast, safe SQLite mode."""
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from server import library


class DatabaseOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(library, "DB_PATH", Path(self.tmp.name) / "lib.sqlite3")
        patch.start()
        self.addCleanup(patch.stop)

    def test_opening_does_not_wait_for_a_writer(self):
        library.db().close()  # create and migrate once
        holding, release = threading.Event(), threading.Event()

        def writer():
            conn = sqlite3.connect(library.DB_PATH, timeout=30)
            conn.execute("BEGIN IMMEDIATE")
            holding.set()
            release.wait(10)
            conn.rollback()
            conn.close()

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            self.assertTrue(holding.wait(5))
            started = time.perf_counter()
            conn = library.db()
            elapsed = time.perf_counter() - started
            # Reading must also work while the write lock is held.
            conn.execute("SELECT COUNT(*) FROM media").fetchone()
            conn.close()
            self.assertLess(elapsed, 1.0, "db() queued behind a write transaction")
        finally:
            release.set()
            thread.join()

    def test_database_uses_wal_with_normal_sync(self):
        conn = library.db()
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)  # NORMAL
        finally:
            conn.close()
        again = library.db()
        try:
            self.assertEqual(again.execute("PRAGMA synchronous").fetchone()[0], 1)
        finally:
            again.close()

    def test_schema_version_is_recorded_and_migration_runs_once(self):
        with mock.patch.object(library, "_migrate", wraps=library._migrate) as migrate:
            library.db().close()
            library.db().close()
            library.db().close()
        self.assertEqual(migrate.call_count, 1)
        conn = sqlite3.connect(library.DB_PATH)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0],
                         library.SCHEMA_VERSION)
        conn.close()

    def test_an_old_database_is_upgraded_in_place_without_losing_rows(self):
        old = sqlite3.connect(library.DB_PATH)  # as an older release left it
        old.execute("CREATE TABLE libraries (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                    "kind TEXT NOT NULL, path TEXT NOT NULL UNIQUE, last_scanned TEXT)")
        old.execute("INSERT INTO libraries(name,kind,path) VALUES ('Movies','movies','/media/m')")
        old.commit()
        old.close()
        conn = library.db()
        try:
            row = conn.execute("SELECT name, icon, sort_order FROM libraries").fetchone()
            self.assertEqual((row["name"], row["icon"], row["sort_order"]), ("Movies", "folder", 0))
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            folders = conn.execute("SELECT path FROM library_folders").fetchall()
            self.assertEqual([f["path"] for f in folders], ["/media/m"])
        finally:
            conn.close()

    def test_concurrent_first_opens_migrate_safely(self):
        errors = []

        def open_it():
            try:
                library.db().close()
            except Exception as error:  # pragma: no cover - failure path
                errors.append(error)

        threads = [threading.Thread(target=open_it) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
