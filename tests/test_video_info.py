"""Video badges must describe the actual source, never guessed metadata."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.video_info import video_format


class VideoFormatTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "test.mkv"
        self.path.write_bytes(b"indexed media fixture")

    def check_format(self, stream, expected):
        with patch("server.video_info._probe", return_value=stream):
            result = video_format(self.path)
        for key, value in expected.items():
            self.assertEqual(result.get(key), value)
        return result

    def test_4k_dolby_vision(self):
        self.check_format(
            {"width": 3840, "height": 2160, "color_transfer": "smpte2084",
             "side_data_list": [{"side_data_type": "DOVI configuration record"}]},
            {"resolution": "4K", "hdr": "Dolby Vision"},
        )

    def test_hdr10_plus_over_plain_hdr(self):
        self.check_format(
            {"width": 1920, "height": 1080, "color_transfer": "smpte2084",
             "side_data_list": [{"side_data_type": "HDR Dynamic Metadata SMPTE2094-40"}]},
            {"resolution": "1080p", "hdr": "HDR10+"},
        )

    def test_hdr10_and_hlg(self):
        self.check_format(
            {"width": 1920, "height": 1080, "color_transfer": "smpte2084",
             "color_primaries": "bt2020"},
            {"resolution": "1080p", "hdr": "HDR10"},
        )
        self.check_format(
            {"width": 1280, "height": 720, "color_transfer": "arib-std-b67"},
            {"resolution": "720p", "hdr": "HLG"},
        )

    def test_sd_and_unknown_hdr(self):
        result = self.check_format(
            {"width": 720, "height": 480},
            {"resolution": "SD"},
        )
        self.assertNotIn("hdr", result)

    def test_missing_file_and_no_video(self):
        self.assertEqual(video_format(self.path.with_name("absent.mkv")), {})
        with patch("server.video_info._probe", return_value={}):
            self.assertEqual(video_format(self.path), {})


if __name__ == "__main__":
    unittest.main()
