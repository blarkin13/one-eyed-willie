"""Cached read-only FFprobe metadata for deciding playback before opening a stream."""
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path

FFPROBE = "/usr/bin/ffprobe"


@lru_cache(maxsize=2048)
def _inspect(path: str, size: int, mtime_ns: int):
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries",
             "format=duration,bit_rate:stream=codec_type,codec_name,profile,width,height,"
             "pix_fmt,channels,sample_rate,bit_rate,color_transfer,color_primaries",
             "-of", "json", path],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if result.returncode or len(result.stdout) > 200_000:
            return {}
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        if not video:
            return {}
        fmt = payload.get("format") or {}
        duration = float(fmt.get("duration") or 0)
        if not math.isfinite(duration) or duration < 0:
            duration = 0
        return {
            "container": Path(path).suffix.lower().lstrip("."),
            "video_codec": str(video.get("codec_name") or "").lower(),
            "audio_codec": str(audio.get("codec_name") or "").lower(),
            "video_profile": str(video.get("profile") or ""),
            "pixel_format": str(video.get("pix_fmt") or ""),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "audio_channels": int(audio.get("channels") or 0),
            "bitrate": int(fmt.get("bit_rate") or 0),
            "duration": duration,
            "hdr_transfer": str(video.get("color_transfer") or ""),
        }
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired, OverflowError):
        return {}


def inspect_media(file: Path):
    """Cache by the actual indexed file's size and modification time."""
    try:
        stat = file.stat()
        return _inspect(str(file), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return {}
