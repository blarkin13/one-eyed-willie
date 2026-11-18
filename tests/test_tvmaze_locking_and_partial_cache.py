import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server import library, tvmaze


def show(show_id=7, name="Some Show"):
    return {"id": show_id, "name": name, "premiered": "2010-01-01",
            "summary": "<p>Plot</p>", "image": None, "externals": {}}


class FakeTvmaze:
    """Stands in for tvmaze._get; records calls and can block or fail."""

    def __init__(self, seasons_ok=True):
        self.calls = []
        self.seasons_ok = seasons_ok
        self.release = None
        self.entered = threading.Event()
        self.lock_was_free = None

    def __call__(self, path, query=None):
        self.calls.append(path)
        if path == "/search/shows":
            self.entered.set()
            if self.release is not None:
                self.release.wait(5)
            name = (query or {}).get("q", "Some Show")
            return [{"show": show(name=name)}]
        if path.endswith("/seasons"):
            return [{"number": 1, "name": "Season 1", "summary": ""}] if self.seasons_ok else None
        if path.endswith("/cast"):
            return [{"person": {"id": 1, "name": "A"}, "character": {"name": "B"}}]
        if path.endswith("/episodes"):
            return [{"season": 1, "number": 1, "name": "Pilot"}]
        return show()


class TvmazeLockingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(directory.name) / "t.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        tvmaze._FAILED_UNTIL.clear()
        tvmaze._KEY_LOCKS.clear()

    def use(self, fake):
        patcher = patch.object(tvmaze, "_get", fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_network_call_does_not_hold_the_global_metadata_lock(self):
        fake = FakeTvmaze()
        seen = []

        def probe(path, query=None):
            # Another thread must be able to take the shared lock mid-request.
            got = []
            thread = threading.Thread(target=lambda: got.append(
                tvmaze.LOCK.acquire(timeout=1) and (tvmaze.LOCK.release() or True)))
            thread.start(); thread.join()
            seen.append(bool(got and got[0]))
            return fake(path, query)

        self.use(probe)
        self.assertEqual(tvmaze.show_metadata("Some Show", 2010)["title"], "Some Show")
        self.assertTrue(seen and all(seen), "LOCK was held during a network call")

    def test_slow_lookup_for_one_show_does_not_block_another(self):
        fake = FakeTvmaze()
        fake.release = threading.Event()
        self.use(fake)
        slow = threading.Thread(target=tvmaze.show_metadata, args=("Slow Show", 2010))
        slow.start()
        self.assertTrue(fake.entered.wait(2))
        # A different, already-cached lookup returns while the first is stuck.
        started = time.perf_counter()
        self.assertEqual(tvmaze.show_cast(7)[0]["name"], "A")
        self.assertLess(time.perf_counter() - started, 1.0)
        fake.release.set()
        slow.join(5)
        self.assertFalse(slow.is_alive())

    def test_concurrent_requests_for_the_same_show_fetch_once(self):
        fake = FakeTvmaze()
        fake.release = threading.Event()
        self.use(fake)
        results = []
        threads = [threading.Thread(target=lambda: results.append(
            tvmaze.show_metadata("Some Show", 2010))) for _ in range(3)]
        for thread in threads:
            thread.start()
        self.assertTrue(fake.entered.wait(2))
        time.sleep(0.1)
        fake.release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(fake.calls.count("/search/shows"), 1)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.get("title") == "Some Show" for r in results))

    def test_show_without_seasons_is_returned_but_not_cached(self):
        fake = FakeTvmaze(seasons_ok=False)
        self.use(fake)
        first = tvmaze.show_metadata("Some Show", 2010)
        self.assertEqual(first["title"], "Some Show")
        self.assertEqual(first["seasons"], [])
        fake.seasons_ok = True                    # provider recovers
        second = tvmaze.show_metadata("Some Show", 2010)
        self.assertEqual([s["number"] for s in second["seasons"]], [1])
        before = len(fake.calls)
        tvmaze.show_metadata("Some Show", 2010)    # complete result is cached
        self.assertEqual(len(fake.calls), before)

    def test_provider_outage_is_not_cached_as_no_match(self):
        calls = []
        self.use(lambda path, query=None: calls.append(path))   # returns None
        self.assertEqual(tvmaze.show_metadata("Some Show", 2010), {})
        self.assertEqual(tvmaze.show_cast(7), [])
        self.assertEqual(tvmaze.season_metadata(7, 1), {})
        recovered = FakeTvmaze()
        self.use(recovered)
        self.assertEqual(tvmaze.show_metadata("Some Show", 2010)["title"], "Some Show")
        self.assertEqual(tvmaze.show_cast(7)[0]["name"], "A")
        self.assertIn("Pilot", [e["title"] for e in tvmaze.season_metadata(7, 1)["episodes"].values()])

    def test_explicit_show_id_lookup_is_cached(self):
        fake = FakeTvmaze()
        self.use(fake)
        for _ in range(3):
            self.assertEqual(tvmaze.show_metadata_by_id(7)["tvmaze_id"], 7)
        self.assertEqual(fake.calls.count("/shows/7"), 1)
        self.assertEqual(fake.calls.count("/shows/7/seasons"), 1)

    def test_invalid_ids_do_no_network_work(self):
        fake = FakeTvmaze()
        self.use(fake)
        for value in (0, -1, "7", None):
            self.assertEqual(tvmaze.show_metadata_by_id(value), {})
            self.assertEqual(tvmaze.show_cast(value), [])
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
