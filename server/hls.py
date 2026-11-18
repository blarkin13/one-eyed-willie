"""Private NUC-origin HLS compatibility transcoder.

Sessions only accept validated indexed files. The session ID is random; FFmpeg
writes to a bounded rolling directory under /data, and inactive jobs are killed.
Video routes live under /api/stream to honor the existing Worker stream block.
"""
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .media_probe import inspect_media
from .playback import _item, probe_duration
from .hardware import hardware_supported

router = APIRouter(prefix="/api/stream/hls")
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
SEGMENT = re.compile(r"^segment_[0-9]{6}\.ts$")


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


def normalize_quality(value):
    """Unknown or missing values fall back to the default instead of failing."""
    return value if isinstance(value, str) and value in QUALITIES else DEFAULT_QUALITY


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


def hardware_available():
    return hardware_supported()


def _command(file, directory, start, hardware=False, quality=DEFAULT_QUALITY):
    # Keep generated segments available for replay and seeking. The old
    # sliding playlist deleted segments while viewers were still watching.
    # Read slightly ahead of real-time without encoding the entire file at once.
    preset = QUALITIES[normalize_quality(quality)]
    width, height = preset["width"], preset["height"]
    args = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error"]
    if hardware:
        # Decode in software, upload frames for GPU encoding. Forcing VAAPI
        # decoding of every source causes needless fallback for unsupported inputs.
        args += ["-vaapi_device", "/dev/dri/renderD128"]
    args += ["-readrate", "1.5", "-ss", str(start), "-i", str(file),
             "-map", "0:v:0", "-map", "0:a:0?"]
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
              quality: str = Query(DEFAULT_QUALITY)):
    quality = normalize_quality(quality)
    _, file = _item(media_id)
    if not os.path.isfile(FFMPEG):
        raise HTTPException(503, "Video transcoder is not installed")
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
        hardware = hardware_available()
        try:
            process = _spawn(_command(file, directory, start, hardware, quality), directory)
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Unable to start transcoder") from exc
        now = time.monotonic()
        session = Session(token, directory, process, now, now, media_id,
                          "Intel VAAPI encode" if hardware else "CPU", probe_duration(file), start,
                          quality)
        ACTIVE[token] = session
        return {"session": token,
                "playlist": f"/api/stream/hls/{token}/index.m3u8",
                "engine": session.acceleration, "quality": quality,
                "duration": session.duration, "start": start}


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
def data_estimates(media_id: int):
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
    return {
        "duration_seconds": seconds,
        "original": {"bytes": size,
                     "kbps": int(size * 8 / 1000 / seconds) if seconds and size else 0},
        "qualities": options,
        "default": DEFAULT_QUALITY,
    }


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
                                     session.start, False, session.quality),
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
    return FileResponse(
        file, media_type=("application/vnd.apple.mpegurl"
                          if filename.endswith(".m3u8") else "video/mp2t"),
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
