"""Private NUC-origin HLS compatibility transcoder.

Sessions only accept validated indexed files. The session ID is random; FFmpeg
writes to a bounded rolling directory under /data, and inactive jobs are killed.
Video routes live under /api/stream to honor the existing Worker stream block.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .media_probe import inspect_media
from .playback import _item, probe_duration
from .hardware import hardware_supported
from . import usage

router = APIRouter(prefix="/api/stream/hls")
FFPROBE = "/usr/bin/ffprobe"
FFMPEG = "/usr/bin/ffmpeg"
ROOT = Path(os.environ.get("HLS_CACHE_DIR", "/data/hls"))
ACTIVE = {}
LOCK = threading.RLock()
MAX_SESSIONS = 2
# A session nobody has touched for this long may be reclaimed when a new
# player needs a slot (abandoned by a crashed app, or paused for a long time).
RECLAIM_IDLE_SECONDS = 90
IDLE_SECONDS = 30 * 60
SESSION_SECONDS = 8 * 60 * 60
MIN_FREE_BYTES = 512 * 1024 * 1024
TOKEN = re.compile(r"^[a-f0-9]{32}$")
SEGMENT = re.compile(r"^(?:init\.mp4|segment_[0-9]{6}\.(?:ts|m4s))$")
CONTENT_TYPES = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t",
                 ".m4s": "video/iso.segment", ".mp4": "video/mp4"}


# Output presets. 720p is the long-standing default and keeps its exact settings.
# width/height bound the picture (letterboxed to that frame); crf drives CPU
# quality; the three bitrates are VAAPI target/max/buffer in kbit/s and the
# CPU path's cap/buffer.
QUALITIES = {
    # Quality-driven (CRF) tiers: size varies with the picture, capped at maxrate.
    "1080p": {"width": 1920, "height": 1080, "crf": 23, "target": 6000, "maxrate": 8000, "bufsize": 12000, "audio": 128},
    "720p": {"width": 1280, "height": 720, "crf": 26, "target": 2500, "maxrate": 3200, "bufsize": 5000, "audio": 128},
    # Data-saving tiers use a target bitrate (abr) so the data cost is predictable.
    "480p": {"width": 854, "height": 480, "abr": True, "target": 1000, "maxrate": 1300, "bufsize": 2000, "audio": 96},
    "360p": {"width": 640, "height": 360, "abr": True, "target": 600, "maxrate": 800, "bufsize": 1200, "audio": 96},
    "240p": {"width": 426, "height": 240, "abr": True, "target": 300, "maxrate": 400, "bufsize": 700, "audio": 64},
}
DEFAULT_QUALITY = "720p"
# "full" keeps the original video untouched (stream copy) and only converts the
# audio, so it loses nothing and costs the server almost no CPU. It needs video
# every browser can decode as it is.
FULL = "full"


@lru_cache(maxsize=512)
def _dolby_vision(path: str, size: int, mtime_ns: int):
    """True when the first video stream carries a Dolby Vision configuration."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream_side_data=side_data_type", "-of", "json", path],
            capture_output=True, text=True, timeout=8, check=False)
        found = json.loads(result.stdout or "{}") if not result.returncode else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return any("dovi" in str(item.get("side_data_type", "")).lower()
               for stream in found.get("streams") or [] for item in stream.get("side_data_list") or [])


def has_dolby_vision(file: Path):
    try:
        stat = file.stat()
    except OSError:
        return False
    return _dolby_vision(str(file), stat.st_size, stat.st_mtime_ns)


def full_quality_support(profile, hevc=0):
    """(available, reason) for passing the original video straight through.

    [hevc] is the deepest HEVC the viewer's browser says it can decode: 0 none,
    8 (Main) or 10 (Main 10). Without it only 8-bit H.264 can be copied.
    """
    profile = profile or {}
    codec = str(profile.get("video_codec") or "")
    pixel = profile.get("pixel_format") or "yuv420p"
    if not codec:
        return False, "The video format could not be read."
    if codec == "h264":
        if pixel != "yuv420p":
            return False, "This video uses a colour format browsers cannot play; choose 1080p."
    elif codec == "hevc":
        if hevc not in (8, 10):
            return False, "HEVC video must be converted for browsers; choose 1080p."
        if pixel not in ("yuv420p", "yuv420p10le"):
            return False, "This video uses a colour format browsers cannot play; choose 1080p."
        if pixel == "yuv420p10le" and hevc < 10:
            return False, "This browser cannot play 10-bit video; choose 1080p."
        if profile.get("dolby_vision"):
            return False, "Dolby Vision video would look wrong unconverted; choose 1080p."
    else:
        return False, f"{codec.upper()} video must be converted for browsers; choose 1080p."
    if (profile.get("hdr_transfer") or "") in ("smpte2084", "arib-std-b67"):
        return False, "HDR video would look washed out unconverted; choose 1080p."
    return True, ""


def full_quality_for(file: Path, hevc=0):
    """full_quality_support for a file, including checks that need a second probe."""
    profile = dict(inspect_media(file) or {})
    if profile.get("video_codec") == "hevc" and hevc in (8, 10):
        profile["dolby_vision"] = has_dolby_vision(file)
    available, reason = full_quality_support(profile, hevc)
    return available, reason, profile


def hevc_depth(value):
    """Sanitise the client's claim of what HEVC it can decode (0, 8 or 10)."""
    return value if isinstance(value, int) and value in (8, 10) else 0


def normalize_quality(value):
    """Unknown or missing values fall back to the default instead of failing."""
    return value if isinstance(value, str) and (value in QUALITIES or value == FULL) else DEFAULT_QUALITY


@dataclass
class Session:
    token: str
    directory: Path
    process: subprocess.Popen
    created: float
    last_access: float
    media_id: int
    acceleration: str
    duration: float
    start: float
    quality: str = DEFAULT_QUALITY
    viewing: str = ""
    audio: int = 0


CHANNEL_NAMES = {1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1"}
LANGUAGE_NAMES = {"eng": "English", "spa": "Spanish", "fra": "French", "fre": "French",
                  "deu": "German", "ger": "German", "ita": "Italian", "por": "Portuguese",
                  "jpn": "Japanese", "kor": "Korean", "zho": "Chinese", "chi": "Chinese",
                  "rus": "Russian", "hin": "Hindi", "ara": "Arabic", "nld": "Dutch",
                  "dut": "Dutch", "swe": "Swedish", "pol": "Polish", "tur": "Turkish"}


@lru_cache(maxsize=512)
def _audio_tracks(path: str, size: int, mtime_ns: int):
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=codec_name,channels:stream_tags=language,title:stream_disposition=default",
             "-of", "json", path],
            capture_output=True, text=True, timeout=8, check=False)
        streams = json.loads(result.stdout or "{}").get("streams") or [] if not result.returncode else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ()
    tracks = []
    for index, stream in enumerate(streams[:32]):
        tags = stream.get("tags") or {}
        code = str(tags.get("language") or "").lower()[:3]
        language = LANGUAGE_NAMES.get(code) or (code.upper() if code and code != "und" else "")
        channels = int(stream.get("channels") or 0)
        title = str(tags.get("title") or "").strip()[:60]
        parts = [language or f"Track {index + 1}"]
        if title and title.lower() != language.lower():
            parts.append(title)
        parts.append(CHANNEL_NAMES.get(channels, f"{channels} ch" if channels else ""))
        parts.append(str(stream.get("codec_name") or "").upper())
        tracks.append({"id": index, "language": code if code != "und" else "",
                       "label": " · ".join(part for part in parts if part),
                       "default": bool((stream.get("disposition") or {}).get("default"))})
    return tuple(tuple(sorted(track.items())) for track in tracks)


def list_audio_tracks(file: Path):
    """The audio streams of [file], in file order (ids are positions among audio streams)."""
    try:
        stat = file.stat()
    except OSError:
        return []
    return [dict(track) for track in _audio_tracks(str(file), stat.st_size, stat.st_mtime_ns)]


def hardware_available():
    return hardware_supported()


def _command(file, directory, start, hardware=False, quality=DEFAULT_QUALITY, audio=0, fmp4=False):
    # Keep generated segments available for replay and seeking. The old
    # sliding playlist deleted segments while viewers were still watching.
    # Read slightly ahead of real-time without encoding the entire file at once.
    if normalize_quality(quality) == FULL:
        # Copy the video; -noaccurate_seek keeps audio and video starting together
        # at the keyframe at or before [start]. Copying is far cheaper than
        # encoding, so read well ahead of real time to make forward seeks cheap.
        # HEVC must travel in fragmented MP4 (what browsers and Safari accept for it),
        # tagged hvc1; H.264 keeps the simpler MPEG-TS packaging.
        packaging = (["-tag:v", "hvc1"] if fmp4 else [])
        container = (["-hls_segment_type", "fmp4", "-hls_fmp4_init_filename", "init.mp4",
                      "-hls_segment_filename", str(directory / "segment_%06d.m4s")] if fmp4 else
                     ["-hls_segment_filename", str(directory / "segment_%06d.ts")])
        return [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error",
                "-readrate", "4", "-noaccurate_seek", "-ss", str(start), "-i", str(file),
                "-map", "0:v:0", "-map", f"0:a:{int(audio)}?", "-c:v", "copy", *packaging,
                "-c:a", "aac", "-ac", "2", "-b:a", "192k", "-ar", "48000",
                "-f", "hls", "-hls_time", "4", "-hls_playlist_type", "event",
                "-hls_list_size", "0", "-hls_flags", "temp_file+independent_segments",
                *container, str(directory / "index.m3u8")]
    preset = QUALITIES[normalize_quality(quality)]
    width, height = preset["width"], preset["height"]
    args = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error"]
    if hardware:
        # Decode in software, upload frames for GPU encoding. Forcing VAAPI
        # decoding of every source causes needless fallback for unsupported inputs.
        args += ["-vaapi_device", "/dev/dri/renderD128"]
    args += ["-readrate", "1.5", "-ss", str(start), "-i", str(file),
             "-map", "0:v:0", "-map", f"0:a:{int(audio)}?"]
    if hardware:
        args += ["-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=nv12,hwupload",
                 "-c:v", "h264_vaapi",
                 "-b:v", f"{preset['target']}k", "-maxrate", f"{preset['maxrate']}k",
                 "-bufsize", f"{preset['bufsize']}k"]
    else:
        args += ["-vf", f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                 "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
                 "-pix_fmt", "yuv420p"]
        if preset.get("abr"):
            args += ["-b:v", f"{preset['target']}k"]
        else:
            args += ["-crf", str(preset["crf"])]
        args += ["-maxrate", f"{preset['maxrate']}k", "-bufsize", f"{preset['bufsize']}k"]
    args += ["-c:a", "aac", "-ac", "2", "-b:a", f"{preset['audio']}k", "-ar", "48000",
             "-force_key_frames", "expr:gte(t,n_forced*4)",
             "-sc_threshold", "0", "-f", "hls", "-hls_time", "4",
             "-hls_playlist_type", "event", "-hls_list_size", "0",
             "-hls_flags", "temp_file+independent_segments",
             "-hls_segment_filename", str(directory / "segment_%06d.ts"),
             str(directory / "index.m3u8")]
    return args


LOG_NAME = "ffmpeg.log"


def _spawn(command, directory):
    """Start FFmpeg, keeping its error output so failures can be explained."""
    with open(directory / LOG_NAME, "ab") as log:
        return subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=log, close_fds=True,
        )


def _log_tail(directory, limit=240):
    """Last meaningful FFmpeg error line, trimmed; never raises."""
    try:
        lines = (directory / LOG_NAME).read_text(errors="replace").strip().splitlines()
    except OSError:
        return ""
    return lines[-1][-limit:] if lines else ""


def _reclaim_idle_session(now=None):
    """Free one slot by stopping the longest-idle session, if it is stale."""
    now = now or time.monotonic()
    stale = [(s.last_access, key) for key, s in ACTIVE.items()
             if now - s.last_access > RECLAIM_IDLE_SECONDS]
    if not stale:
        return False
    _, key = min(stale)
    _terminate(ACTIVE.pop(key))
    return True


def _terminate(session):
    if session.process.poll() is None:
        session.process.terminate()
        try:
            session.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=2)
    shutil.rmtree(session.directory, ignore_errors=True)


def _purge(now=None):
    now = now or time.monotonic()
    expired = [
        key for key, session in ACTIVE.items()
        if now - session.last_access > IDLE_SECONDS or now - session.created > SESSION_SECONDS
    ]
    for key in expired:
        _terminate(ACTIVE.pop(key))


def cleanup_loop(stop):
    while not stop.wait(35):
        with LOCK:
            _purge()


def init_cache():
    ROOT.mkdir(parents=True, exist_ok=True)
    # Previous-process sessions are not usable and must not fill the NUC disk.
    with LOCK:
        for path in ROOT.iterdir():
            if path.is_dir() and TOKEN.fullmatch(path.name):
                shutil.rmtree(path, ignore_errors=True)


def _get_session(token):
    if not TOKEN.fullmatch(token):
        raise HTTPException(404, "Stream not found")
    with LOCK:
        _purge()
        session = ACTIVE.get(token)
        if session is None:
            raise HTTPException(404, "Stream expired")
        session.last_access = time.monotonic()
        return session


@router.post("/start/{media_id}")
def start_hls(media_id: int, start: float = Query(0, ge=0, le=10000000),
              quality: str = Query(DEFAULT_QUALITY),
              viewing: str = Query("", max_length=64),
              audio: int = Query(0, ge=0, le=31),
              hevc: int = Query(0)):
    quality = normalize_quality(quality)
    _, file = _item(media_id)
    audio = audio if isinstance(audio, int) else 0     # direct calls skip FastAPI's defaults
    if audio:
        tracks = list_audio_tracks(file)
        if audio >= len(tracks):
            raise HTTPException(400, "That audio track does not exist in this video")
    if not os.path.isfile(FFMPEG):
        raise HTTPException(503, "Video transcoder is not installed")
    fmp4 = False
    if quality == FULL:
        available, reason, profile = full_quality_for(file, hevc_depth(hevc))
        if not available:
            raise HTTPException(409, "Full quality is not available for this file. " + reason)
        fmp4 = profile.get("video_codec") == "hevc"
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(ROOT)
    except OSError as exc:
        raise HTTPException(503, "Transcoding directory unavailable") from exc
    if disk.free < MIN_FREE_BYTES:
        raise HTTPException(507, "Not enough free disk space for transcoding")
    with LOCK:
        _purge()
        if len(ACTIVE) >= MAX_SESSIONS and not _reclaim_idle_session():
            raise HTTPException(429, "Two streams are already in use by other players. "
                                     "Stop one of them and try again.")
        token = secrets.token_hex(16)
        directory = ROOT / token
        directory.mkdir(mode=0o700)
        hardware = hardware_available() and quality != FULL
        try:
            process = _spawn(_command(file, directory, start, hardware, quality, audio, fmp4), directory)
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Unable to start transcoder") from exc
        now = time.monotonic()
        session = Session(token, directory, process, now, now, media_id,
                          "Original video (no re-encode)" if quality == FULL
                          else "Intel VAAPI encode" if hardware else "CPU",
                          probe_duration(file), start, quality, usage.valid(viewing) or "", audio)
        ACTIVE[token] = session
        return {"session": token,
                "playlist": f"/api/stream/hls/{token}/index.m3u8",
                "engine": session.acceleration, "quality": quality,
                "duration": session.duration, "start": start, "audio": audio}


@router.get("/qualities")
def list_qualities():
    return {"default": DEFAULT_QUALITY,
            "qualities": [{"id": key, "height": value["height"],
                           "max_kbps": value["maxrate"]} for key, value in QUALITIES.items()]}


# MPEG-TS packaging and HTTP headers add a few percent on top of the media bitrate.
PACKAGING_OVERHEAD = 1.07


def estimate_kbps(preset, hardware):
    """(kbit/s including audio, "about" | "up_to") for one quality preset.

    Hardware encodes and the data-saving tiers are bitrate-targeted, so the
    figure is close to what will be used. CRF encodes are only capped, so the
    cap is the honest ceiling ("up to").
    """
    if hardware or preset.get("abr"):
        return preset["target"] + preset["audio"], "about"
    return preset["maxrate"] + preset["audio"], "up_to"


def estimate_bytes(kbps, seconds):
    return int(kbps * 1000 / 8 * max(0.0, seconds) * PACKAGING_OVERHEAD)


@router.get("/estimates/{media_id}")
def data_estimates(media_id: int, hevc: int = Query(0)):
    """What watching this title costs in data at each quality (whole title)."""
    _, file = _item(media_id)
    profile = inspect_media(file)
    seconds = float(profile.get("duration") or 0) or probe_duration(file)
    try:
        size = file.stat().st_size
    except OSError:
        size = 0
    hardware = hardware_available()
    options = []
    for key, preset in QUALITIES.items():
        kbps, kind = estimate_kbps(preset, hardware)
        options.append({"id": key, "kbps": kbps, "kind": kind,
                        "bytes": estimate_bytes(kbps, seconds) if seconds else 0})
    available, reason, _ = full_quality_for(file, hevc_depth(hevc))
    return {
        "duration_seconds": seconds,
        "original": {"bytes": size,
                     "kbps": int(size * 8 / 1000 / seconds) if seconds and size else 0},
        # The video is copied as-is, so the stream is about the size of the file
        # (its audio is re-encoded, which changes that by a few percent).
        "full": {"available": available, "reason": reason,
                 "bytes": int(size * PACKAGING_OVERHEAD) if available else 0, "kind": "about"},
        "qualities": options,
        "default": DEFAULT_QUALITY,
    }


@router.get("/audio/{media_id}")
def audio_tracks(media_id: int):
    """Audio tracks of a title, so the viewer can choose a language."""
    _, file = _item(media_id)
    return {"tracks": list_audio_tracks(file)}


@router.get("/usage/{viewing}")
def viewing_usage(viewing: str):
    """Bytes the server has sent for one viewing (direct play + HLS)."""
    if not usage.valid(viewing):
        raise HTTPException(404, "Invalid viewing")
    return {"bytes": usage.total(viewing)}


@router.get("/{token}/status")
def stream_status(token: str):
    session = _get_session(token)
    playlist = session.directory / "index.m3u8"
    code = session.process.poll()
    if code is not None and code != 0 and not playlist.exists():
        # Some driver/codec combinations cannot use VAAPI; restart with CPU.
        if session.acceleration == "Intel VAAPI encode":
            with LOCK:
                if ACTIVE.get(token) is session:
                    try:
                        session.process = _spawn(
                            _command(_item(session.media_id)[1], session.directory,
                                     session.start, False, session.quality, session.audio),
                            session.directory,
                        )
                        session.acceleration = "CPU fallback"
                        code = None
                    except OSError:
                        pass
        if code is not None:
            reason = _log_tail(session.directory)
            raise HTTPException(422, "Transcoder could not decode this video"
                                + (f": {reason}" if reason else ""))
    if code is not None and code != 0:
        reason = _log_tail(session.directory)
        raise HTTPException(422, "Transcoder stopped unexpectedly"
                            + (f": {reason}" if reason else ""))
    return {"ready": playlist.is_file(), "engine": session.acceleration,
            "quality": session.quality,
            "playlist": f"/api/stream/hls/{token}/index.m3u8",
            "duration": session.duration, "start": session.start}


@router.get("/{token}/{filename}")
def stream_file(token: str, filename: str):
    if filename != "index.m3u8" and not SEGMENT.fullmatch(filename):
        raise HTTPException(404, "Invalid stream file")
    session = _get_session(token)
    if shutil.disk_usage(ROOT).free < MIN_FREE_BYTES // 2:
        with LOCK:
            ACTIVE.pop(token, None)
            _terminate(session)
        raise HTTPException(507, "Transcoding stopped: disk space low")
    file = session.directory / filename
    if not file.is_file() or file.is_symlink():
        raise HTTPException(404, "Segment not ready")
    return usage.CountingFileResponse(
        file, viewing=session.viewing,
        media_type=CONTENT_TYPES[Path(filename).suffix],
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{token}")
def stop_hls(token: str):
    if not TOKEN.fullmatch(token):
        raise HTTPException(404, "Invalid session")
    with LOCK:
        session = ACTIVE.pop(token, None)
        if session:
            _terminate(session)
    return {"stopped": bool(session)}
