"""Google TV uses the approved YarrMedia SVG via adaptive and density-aware icons."""
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
ANDROID = ROOT / "google-tv/app/src/main"
RES = ANDROID / "res"
MANIFEST = ANDROID / "AndroidManifest.xml"
MASTER = ROOT / "google-tv/artwork/yarrmedia_launcher_precision.svg"
ADAPTIVE = RES / "mipmap-anydpi-v26/yarrmedia_launcher.xml"
FOREGROUND = RES / "drawable/yarrmedia_launcher_foreground.xml"
BACKGROUND = RES / "values/yarrmedia_launcher_colors.xml"
BANNER = RES / "drawable-nodpi/yarr_tv_banner.png"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
DENSITIES = {"mdpi": 80, "hdpi": 120, "xhdpi": 160,
             "xxhdpi": 240, "xxxhdpi": 320}


class GoogleTvLauncherTests(unittest.TestCase):
    def test_manifest_uses_android_standard_launcher_resources(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:label="YarrMedia"', manifest)
        self.assertIn('android:icon="@mipmap/yarrmedia_launcher"', manifest)
        self.assertIn('android:roundIcon="@mipmap/yarrmedia_launcher"', manifest)
        self.assertIn('android:banner="@drawable/yarr_tv_banner"', manifest)
        self.assertNotIn('android:icon="@drawable/yarrmedia_launcher"', manifest)

    def test_adaptive_icon_has_independent_foreground_background(self):
        root = ET.parse(ADAPTIVE).getroot()
        self.assertEqual(root.tag, "adaptive-icon")
        children = {child.tag: child.attrib[ANDROID_NS + "drawable"] for child in root}
        self.assertEqual(children, {
            "background": "@color/yarrmedia_launcher_background",
            "foreground": "@drawable/yarrmedia_launcher_foreground",
        })
        background = ET.parse(BACKGROUND).getroot()
        self.assertEqual(background.find("color").attrib["name"], "yarrmedia_launcher_background")
        self.assertEqual(background.find("color").text, "#FFFFFF")

    def test_foreground_keeps_the_original_four_color_brand(self):
        vector = ET.parse(FOREGROUND).getroot()
        self.assertEqual(vector.tag, "vector")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportWidth"], "2048")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportHeight"], "2048")
        group = vector.find("group")
        self.assertIsNotNone(group)
        self.assertEqual(group.attrib[ANDROID_NS + "scaleX"], "0.84")
        self.assertEqual(group.attrib[ANDROID_NS + "scaleY"], "0.84")
        paths = {p.attrib[ANDROID_NS + "name"]: p for p in group.findall("path")}
        self.assertEqual(set(paths), {"sail", "wave", "yarr", "dot", "media"})
        self.assertEqual({p.attrib[ANDROID_NS + "fillColor"] for p in paths.values()},
                         {"#000000", "#9B9B9B", "#A61E1E"})
        for name in ("yarr", "media"):
            self.assertEqual(paths[name].attrib[ANDROID_NS + "fillType"], "evenOdd")
        self.assertGreater(len(paths["sail"].attrib[ANDROID_NS + "pathData"]), 300)

    def test_density_assets_render_directly_from_vector_and_are_transparent(self):
        from PIL import Image
        for density, pixels in DENSITIES.items():
            with self.subTest(density=density):
                path = RES / f"mipmap-{density}/yarrmedia_launcher.png"
                with Image.open(path) as image:
                    self.assertEqual(image.size, (pixels, pixels))
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.getpixel((0, 0))[3], 0)
                    self.assertEqual(image.getpixel((pixels-1, pixels-1))[3], 0)
                    self.assertEqual(image.getpixel((pixels//2, pixels//4)),
                                     (255, 255, 255, 255))
                    # Text's red is opaque in each device-density icon.
                    self.assertTrue(any(r > 110 and r - g > 70 and b < 90 and a >= 170
                                        for _, (r, g, b, a) in image.getcolors(pixels*pixels) or []))

    def test_source_and_tv_banner_are_preserved(self):
        svg = MASTER.read_text()
        self.assertIn('id="sail"', svg)
        self.assertIn('id="media"', svg)
        self.assertIn('fill="#A61E1E"', svg)
        banner_bytes = BANNER.read_bytes()
        self.assertTrue(banner_bytes.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertEqual(struct.unpack(">II", banner_bytes[16:24]), (1280, 720))
        self.assertTrue((RES / "drawable-nodpi/tv_loading_screen.png").is_file())


if __name__ == "__main__":
    unittest.main()
