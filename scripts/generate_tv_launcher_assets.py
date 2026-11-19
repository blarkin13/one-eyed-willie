#!/usr/bin/env python3
"""Generate Google TV mipmap launchers from the approved, editable YarrMedia SVG.

Requires: pillow, cairosvg. Source artwork is preserved; no automated retracing.
Run from repository root:
    python scripts/generate_tv_launcher_assets.py
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from PIL import Image
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "google-tv/artwork/yarrmedia_launcher_precision.svg"
RES = ROOT / "google-tv/app/src/main/res"
DENSITIES = {
    "mdpi": 80,
    "hdpi": 120,
    "xhdpi": 160,
    "xxhdpi": 240,
    "xxxhdpi": 320,
}
ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)

def android(name: str) -> str:
    return "{" + ANDROID_NS + "}" + name


def make_adaptive_foreground(source: Path, target: Path) -> None:
    """Convert authored SVG curves to actual Android VectorDrawable curves.

    The 84% Android adaptive foreground scale keeps the wordmark legible on
    circular Google TV launchers. The entire artwork remains on its own
    vector layer; the system supplies the white background and round mask.
    Some unusually tight third-party masks may crop details at this scale.
    """
    svg = ET.parse(source).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    parent = ET.Element("vector", {
        android("width"): "108dp", android("height"): "108dp",
        android("viewportWidth"): "2048", android("viewportHeight"): "2048",
    })
    group = ET.SubElement(parent, "group", {
        android("pivotX"): "1024", android("pivotY"): "1024",
        android("scaleX"): "0.84", android("scaleY"): "0.84",
    })
    seen = set()
    for shape in svg:
        if shape.tag == ns + "path":
            fill = shape.attrib.get("fill", "#000000")
            spec = {
                android("name"): shape.attrib.get("id", "path"),
                android("fillColor"): fill,
                android("pathData"): " ".join(shape.attrib["d"].split()),
            }
            if shape.attrib.get("fill-rule") == "evenodd":
                spec[android("fillType")] = "evenOdd"
            ET.SubElement(group, "path", spec)
            seen.add(shape.attrib.get("id"))
        elif shape.tag == ns + "circle" and shape.attrib.get("id") == "dot":
            x = float(shape.attrib["cx"])
            y = float(shape.attrib["cy"])
            r = float(shape.attrib["r"])
            circle_path = (f"M {x-r:g} {y:g} "
                           f"a {r:g},{r:g} 0 1,0 {2*r:g},0 "
                           f"a {r:g},{r:g} 0 1,0 {-2*r:g},0 Z")
            ET.SubElement(group, "path", {
                android("name"): "dot", android("fillColor"): shape.attrib["fill"],
                android("pathData"): circle_path,
            })
            seen.add("dot")
    expected = {"sail", "wave", "yarr", "media", "dot"}
    assert seen == expected, f"Unexpected foreground artwork: {seen}"
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(parent).write(target, encoding="unicode", xml_declaration=True)
    target.write_text(target.read_text() + "\n")


def render(source: Path, target: Path, pixels: int) -> None:
    # Render directly from SVG vectors at 4x device resolution to preserve
    # anti-aliased typography and curves when displayed at launcher sizes.
    supersampled = cairosvg.svg2png(url=str(source), output_width=pixels*4, output_height=pixels*4)
    with Image.open(BytesIO(supersampled)) as image:
        result = image.convert("RGBA").resize((pixels, pixels), Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        result.save(target, optimize=True)


def main() -> None:
    if not SOURCE.is_file():
        sys.exit(f"Missing master artwork: {SOURCE}")
    for density, size in DENSITIES.items():
        render(SOURCE, RES / f"mipmap-{density}" / "yarrmedia_launcher.png", size)
    make_adaptive_foreground(SOURCE, RES / "drawable" / "yarrmedia_launcher_foreground.xml")
    (RES / "values").mkdir(parents=True, exist_ok=True)
    (RES / "values" / "yarrmedia_launcher_colors.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<resources><color name="yarrmedia_launcher_background">#FFFFFF</color></resources>\n'
    )
    (RES / "mipmap-anydpi-v26").mkdir(parents=True, exist_ok=True)
    (RES / "mipmap-anydpi-v26" / "yarrmedia_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <background android:drawable="@color/yarrmedia_launcher_background" />\n'
        '  <foreground android:drawable="@drawable/yarrmedia_launcher_foreground" />\n'
        '</adaptive-icon>\n'
    )
    print("Created launcher mipmaps, adaptive icon layers, and color background")

if __name__ == "__main__":
    main()
