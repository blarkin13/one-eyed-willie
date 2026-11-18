"""TV player: playback-critical work must not queue behind slow lookups.

PlayerActivity used to run everything on one single-thread executor, so the
selection-colour request delayed the first frame, and a subtitle search (45 s
read timeout) could hold up a seek's HLS restart or a progress save. Source-level
guard; the real behaviour needs a TV.
"""
import re
import unittest
from pathlib import Path

PLAYER = (Path(__file__).resolve().parents[1]
          / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()


def body(signature):
    start = PLAYER.index(signature)
    return PLAYER[start:start + 900]


class PlayerExecutorLaneTests(unittest.TestCase):
    def test_there_are_two_separate_single_thread_lanes(self):
        self.assertRegex(PLAYER, r"private val network = Executors\.newSingleThreadExecutor\(\)")
        self.assertRegex(PLAYER, r"private val lookups = Executors\.newSingleThreadExecutor\(\)")

    def test_slow_lookups_use_the_lookup_lane(self):
        for signature in ("private fun loadPlayerAppearance()",
                          "private fun applyDefaultSubtitlesForThisTv()",
                          "private fun showCaptions()",
                          "private fun searchOpenSubtitles(",
                          "private fun downloadSubtitle(",
                          "private fun loadNextEpisode()"):
            text = body(signature)
            self.assertIn("lookups.execute", text, signature)
            self.assertNotIn("network.execute", text, signature)

    def test_playback_critical_work_stays_on_the_ordered_lane(self):
        self.assertIn("network.execute", body("private fun openMedia()"))
        self.assertIn("network.execute { startHlsOnNetwork(position, serial) }", PLAYER)
        destroy = PLAYER[PLAYER.index("override fun onDestroy()"):]
        self.assertIn("network.execute", destroy)  # releasing the HLS session
        # Progress saves keep their order: never on the lookup lane.
        for match in re.finditer(r"lookups\.execute \{(.{0,400})", PLAYER, re.S):
            self.assertNotIn("/api/playback/progress", match.group(1))

    def test_both_lanes_are_shut_down(self):
        destroy = PLAYER[PLAYER.index("override fun onDestroy()"):]
        self.assertIn("network.shutdown()", destroy)
        self.assertIn("lookups.shutdown()", destroy)


if __name__ == "__main__":
    unittest.main()
