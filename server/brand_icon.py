"""Raster and favicon versions of Yarr Media's source-of-truth SVG mark."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

_SOURCE = Path(__file__).with_name("logo.svg")


@lru_cache(maxsize=1)
def _artwork() -> Image.Image:
    root = ET.parse(_SOURCE).getroot()
    shape = next(node for node in root if node.tag.endswith("path"))
    image = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for segment in re.findall(r"M([^Z]+)Z", shape.attrib["d"]):
        points = [tuple(map(int, item.split(","))) for item in segment.split()]
        draw.polygon(points, fill=(255, 255, 255, 255))
    return image


@lru_cache(maxsize=8)
def brand_png(size: int) -> bytes:
    if size not in (128, 180, 192, 512):
        raise ValueError("Unsupported icon size")
    image = _artwork().resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


@lru_cache(maxsize=1)
def brand_ico() -> bytes:
    output = BytesIO()
    _artwork().save(output, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    return output.getvalue()
