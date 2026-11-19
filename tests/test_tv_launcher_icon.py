"""Google TV launcher: clean native glyph outlines and adaptive/density assets."""
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv/app/src/main"
RES = ANDROID / "res"
MANIFEST = ANDROID / "AndroidManifest.xml"
MASTER = ROOT / "google-tv/artwork/yarrmedia_launcher_true_vector.svg"
ADAPTIVE = RES / "mipmap-anydpi-v26/yarrmedia_launcher.xml"
FOREGROUND = RES / "drawable/yarrmedia_launcher_foreground.xml"
BACKGROUND = RES / "values/yarrmedia_launcher_colors.xml"
BANNER = RES / "drawable-nodpi/yarr_tv_banner.png"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
SVG_NS = "{http://www.w3.org/2000/svg}"
DENSITIES = {"mdpi": 80, "hdpi": 120, "xhdpi": 160,
             "xxhdpi": 240, "xxxhdpi": 320}
LETTERS = {"glyph-Y-52", "glyph-A-239", "glyph-R-479", "glyph-R-688",
           "glyph-M-979", "glyph-E-1253", "glyph-D-1435", "glyph-I-1657",
           "glyph-A-1741"}


class GoogleTvLauncherTests(unittest.TestCase):
    def test_manifest_keeps_yarrmedia_name_and_mipmap_adaptive_icon(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:label="YarrMedia"', manifest)
        self.assertIn('android:icon="@mipmap/yarrmedia_launcher"', manifest)
        self.assertIn('android:roundIcon="@mipmap/yarrmedia_launcher"', manifest)
        self.assertIn('android:banner="@drawable/yarr_tv_banner"', manifest)

    def test_adaptive_icon_layers_are_valid(self):
        root = ET.parse(ADAPTIVE).getroot()
        self.assertEqual(root.tag, "adaptive-icon")
        children = {child.tag: child.attrib[ANDROID_NS + "drawable"] for child in root}
        self.assertEqual(children, {
            "background": "@color/yarrmedia_launcher_background",
            "foreground": "@drawable/yarrmedia_launcher_foreground",
        })
        background = ET.parse(BACKGROUND).getroot()
        self.assertEqual(background.find("color").text, "#FFFFFF")

    def test_android_foreground_uses_clean_glyphs_not_old_angular_word_shapes(self):
        vector = ET.parse(FOREGROUND).getroot()
        self.assertEqual(vector.tag, "vector")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportWidth"], "2048")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportHeight"], "2048")
        group = vector.find("group")
        self.assertIsNotNone(group)
        self.assertEqual(group.attrib[ANDROID_NS + "scaleX"], "0.84")
        self.assertEqual(group.attrib[ANDROID_NS + "scaleY"], "0.84")
        paths = {p.attrib[ANDROID_NS + "name"]: p for p in group.findall("path")}
        self.assertEqual(set(paths), LETTERS | {"sail", "wave", "dot"})
        self.assertEqual({p.attrib[ANDROID_NS + "fillColor"] for p in paths.values()},
                         {"#000000", "#9B9B9B", "#A61E1E"})
        for glyph in LETTERS:
            self.assertEqual(paths[glyph].attrib[ANDROID_NS + "fillType"], "evenOdd")
        for glyph in ("glyph-R-479", "glyph-R-688", "glyph-D-1435",
                      "glyph-M-979"):
            self.assertIn("C", paths[glyph].attrib[ANDROID_NS + "pathData"])
        self.assertNotIn("yarr", paths)
        self.assertNotIn("media", paths)

    def test_generated_android_curves_match_the_master(self):
        source_root = ET.parse(MASTER).getroot()
        source_paths = {p.attrib["id"]: " ".join(p.attrib["d"].split())
                        for p in source_root.findall(SVG_NS + "path")}
        foreground = ET.parse(FOREGROUND).getroot().find("group")
        rendered_paths = {p.attrib[ANDROID_NS + "name"]: p.attrib[ANDROID_NS + "pathData"]
                          for p in foreground.findall("path")}
        for name, curve in source_paths.items():
            self.assertEqual(curve, rendered_paths[name], name)

    def test_density_assets_and_antialiased_edges(self):
        from PIL import Image
        for density, pixels in DENSITIES.items():
            with self.subTest(density=density):
                with Image.open(RES / f"mipmap-{density}/yarrmedia_launcher.png") as image:
                    self.assertEqual(image.size, (pixels, pixels))
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.getpixel((0, 0))[3], 0)
                    self.assertEqual(image.getpixel((pixels-1, pixels-1))[3], 0)
                    self.assertEqual(image.getpixel((pixels//2, pixels//4)),
                                     (255, 255, 255, 255))
                    pixels_flat = list(image.getdata())
                    self.assertTrue(any(r > 110 and r-g > 70 and b < 90 and a >= 170
                                        for r, g, b, a in pixels_flat))
                    self.assertTrue(any(0 < a < 255 for _, _, _, a in pixels_flat))

    def test_full_original_artwork_and_banner_are_unchanged(self):
        svg = MASTER.read_text()
        self.assertIn('id="sail"', svg)
        self.assertIn('id="wave"', svg)
        self.assertIn('fill="#A61E1E"', svg)
        data = BANNER.read_bytes()
        self.assertTrue(data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertEqual(struct.unpack(">II", data[16:24]), (1280, 720))
        self.assertTrue((RES / "drawable-nodpi/tv_loading_screen.png").is_file())


if __name__ == "__main__":
    unittest.main()
