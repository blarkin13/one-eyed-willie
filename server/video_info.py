"""Read-only video format badges derived from the actual local media file.

Never infer Dolby Vision or HDR10+ from movie metadata. The cached ffprobe result
is tied to the file size and mtime and only exposed for server-indexed paths.
"""
import json
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=2048)
def _probe(path: str, size: int, modified_ns: int):
    try:
        result = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_streams", "-of", "json", path],
            capture_output=True, text=True, timeout=9, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 150_000:
            return {}
        streams = json.loads(result.stdout).get("streams") or []
        video = streams[0] if streams else {}
        return video if isinstance(video, dict) else {}
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError):
        return {}


def video_format(file: str | Path):
    """Return only confidently detected display badges."""
    try:
        path = Path(file)
        stat = path.stat()
        stream = _probe(str(path), stat.st_size, stat.st_mtime_ns)
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
    except (OSError, ValueError, TypeError):
        return {}
    if width <= 0 or height <= 0:
        return {}
    long_side, short_side = max(width, height), min(width, height)
    if long_side >= 3800 or short_side >= 2000:
        quality = "4K"
    elif long_side >= 2500 or short_side >= 1400:
        quality = "1440p"
    elif long_side >= 1900 or short_side >= 1000:
        quality = "1080p"
    elif long_side >= 1200 or short_side >= 680:
        quality = "720p"
    else:
        quality = "SD"

    transfer = str(stream.get("color_transfer") or "").lower()
    profile = str(stream.get("profile") or "").lower()
    side_data = stream.get("side_data_list") or []
    side_text = " ".join(
        str(item.get("side_data_type") or "").lower()
        for item in side_data if isinstance(item, dict)
    )
    dolby = ("dovi" in side_text or "dolby vision" in side_text or
             "dvhe" in profile or "dvh1" in profile)
    dynamic_hdr = ("smpte2094-40" in side_text or
                   "smpte 2094-40" in side_text or
                   "hdr10+" in side_text)
    if dolby:
        hdr = "Dolby Vision"
    elif dynamic_hdr:
        hdr = "HDR10+"
    elif transfer in ("smpte2084", "smpte-st-2084"):
        hdr = "HDR10" if "bt2020" in str(stream.get("color_primaries") or "").lower() else "HDR"
    elif transfer in ("arib-std-b67", "arib_std_b67"):
        hdr = "HLG"
    else:
        hdr = None
    result = {"resolution": quality, "width": width, "height": height}
    if hdr:
        result["hdr"] = hdr
    return result
