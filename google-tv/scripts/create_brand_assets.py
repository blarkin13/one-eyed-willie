#!/usr/bin/env python3
"""Recreate bundled Android TV brand art from the user-supplied ship logo.

The packed grayscale bitmap is a compact reproduction of the supplied PNG,
not a stock graphic or remotely loaded logo. No external dependencies.
"""
import base64
import struct
import zlib
from pathlib import Path

PACKED = """
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
"""

SOURCE_SIZE = 192
DATA = zlib.decompress(base64.b64decode("".join(PACKED.split())))
assert len(DATA) == SOURCE_SIZE * SOURCE_SIZE // 4
PIXELS = [((DATA[(y*SOURCE_SIZE+x)//4] >> (6-2*(x%4))) & 3) * 85
          for y in range(SOURCE_SIZE) for x in range(SOURCE_SIZE)]


def png_gray(path, width, height, pixel):
    raw = b"".join(b"\x00" + bytes(pixel(x, y) for x in range(width))
                   for y in range(height))
    def chunk(tag, value):
        return (struct.pack(">I", len(value)) + tag + value
                + struct.pack(">I", zlib.crc32(tag + value) & 0xffffffff))
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def logo(x, y, width, height):
    return PIXELS[min(SOURCE_SIZE-1, y * SOURCE_SIZE // height)*SOURCE_SIZE
                  + min(SOURCE_SIZE-1, x * SOURCE_SIZE // width)]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "app/src/main/res"
    # Icon and in-app logo preserve the uploaded black/white composition.
    png_gray(root/"drawable-nodpi/willie_logo.png", 384, 384,
             lambda x, y: logo(x, y, 384, 384))
    png_gray(root/"mipmap-nodpi/ic_launcher.png", 384, 384,
             lambda x, y: logo(x, y, 384, 384))
    # Google TV's 16:9 leanback banner uses the same supplied artwork.
    png_gray(root/"drawable-nodpi/willie_banner.png", 320, 180,
             lambda x, y: logo(x-70, y, 180, 180) if 70 <= x < 250 else 0)
