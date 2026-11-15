"""Validated local and embedded text subtitles for the browser player.

No arbitrary path input: every subtitle is discovered beside an indexed video
or from its ffprobe subtitle streams. The NUC converts text to WebVTT and caches
it in private /data storage; video files remain read-only.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .playback import _item

router = APIRouter(prefix="/api/stream/subtitles")
CACHE = Path(os.environ.get("SUBTITLE_CACHE_DIR", "/data/subtitles"))
LOCK = threading.RLock()
EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa"}
TEXT_CODECS = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}
TRACK = re.compile(r"^(external|embedded)-([0-9]{1,3})$")
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_VTT_BYTES = 12 * 1024 * 1024


def _sidecars(video):
    matches = []
    for candidate in sorted(video.parent.iterdir(), key=lambda p: p.name.lower()):
        if candidate.suffix.lower() not in EXTENSIONS:
            continue
        # E.g. Goonies.en.srt, Goonies.forced.srt, Goonies.srt
        if candidate.stem != video.stem and not candidate.name.lower().startswith(video.stem.lower()+"."):
            continue
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if not candidate.resolve(strict=True).is_relative_to(video.parent.resolve(strict=True)):
                continue
            if candidate.stat().st_size > MAX_SOURCE_BYTES:
                continue
        except OSError:
            continue
        matches.append(candidate)
    return matches[:30]


def _embedded(video):
    try:
        output = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-select_streams", "s",
             "-show_entries", "stream=index,codec_name:stream_tags=language,title",
             "-of", "json", str(video)],
            capture_output=True, text=True, timeout=8, check=False,
        )
        result = json.loads(output.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    entries = []
    for stream in result.get("streams", []):
        if not isinstance(stream, dict) or stream.get("codec_name") not in TEXT_CODECS:
            continue
        index = stream.get("index")
        if not isinstance(index, int) or index < 0:
            continue
        tags = stream.get("tags") or {}
        entries.append({"stream_index": index,
                        "label": (str(tags.get("title") or tags.get("language") or
                                      "Embedded subtitles"))[:80]})
    return entries[:30]


def subtitle_list(media_id):
    _, video = _item(media_id)
    items = [
        {"id": f"external-{i}", "label": file.stem[len(video.stem):].strip(".") or "Subtitles",
         "kind": "external"}
        for i, file in enumerate(_sidecars(video))
    ]
    items.extend(
        {"id": f"embedded-{i}", "label": entry["label"], "kind": "embedded"}
        for i, entry in enumerate(_embedded(video))
    )
    return {"tracks": items}


@router.get("/{media_id}")
def list_subtitles(media_id: int):
    return subtitle_list(media_id)


@router.get("/{media_id}/{track_id}.vtt")
def subtitle_file(media_id: int, track_id: str):
    _, video = _item(media_id)
    match = TRACK.fullmatch(track_id)
    if not match:
        raise HTTPException(404, "Subtitle track unavailable")
    kind, index_str = match.groups()
    index = int(index_str)
    if kind == "external":
        files = _sidecars(video)
        if index >= len(files):
            raise HTTPException(404, "Subtitle track unavailable")
        source = files[index]
        selected = ["-i", str(source), "-map", "0:s:0"]
        salt = f"{source.resolve()}:{source.stat().st_mtime_ns}:{source.stat().st_size}"
    else:
        streams = _embedded(video)
        if index >= len(streams):
            raise HTTPException(404, "Subtitle track unavailable")
        selected = ["-i", str(video), "-map", f"0:{streams[index]['stream_index']}"]
        salt = f"embedded:{streams[index]['stream_index']}"
    stat = video.stat()
    digest = hashlib.sha256(
        f"{video.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{salt}".encode()
    ).hexdigest()
    dest = CACHE / (digest + ".vtt")
    with LOCK:
        if not dest.is_file():
            CACHE.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".subtitle-", suffix=".vtt", dir=CACHE)
            os.close(fd)
            try:
                result = subprocess.run(
                    ["/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-y",
                     *selected, "-c:s", "webvtt", "-f", "webvtt", temp],
                    capture_output=True, timeout=35, check=False,
                )
                if result.returncode != 0 or not Path(temp).stat().st_size:
                    raise HTTPException(422, "This subtitle track cannot be converted")
                if Path(temp).stat().st_size > MAX_VTT_BYTES:
                    raise HTTPException(413, "Subtitle track is too large")
                os.chmod(temp, 0o600)
                os.replace(temp, dest)
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(503, "Subtitle conversion timed out") from exc
            except OSError as exc:
                raise HTTPException(503, "Subtitle conversion unavailable") from exc
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
    return FileResponse(dest, media_type="text/vtt",
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff"})
