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

from .playback import _item, probe_duration

router = APIRouter(prefix="/api/stream/hls")
FFMPEG = "/usr/bin/ffmpeg"
ROOT = Path(os.environ.get("HLS_CACHE_DIR", "/data/hls"))
ACTIVE = {}
LOCK = threading.RLock()
MAX_SESSIONS = 2
IDLE_SECONDS = 180
SESSION_SECONDS = 8 * 60 * 60
MIN_FREE_BYTES = 512 * 1024 * 1024
TOKEN = re.compile(r"^[a-f0-9]{32}$")
SEGMENT = re.compile(r"^segment_[0-9]{6}\.ts$")


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


def hardware_available():
    return (
        os.environ.get("WILLIE_HW_ACCEL", "auto").lower() in ("auto", "vaapi")
        and Path("/dev/dri/renderD128").exists()
        and os.access("/dev/dri/renderD128", os.R_OK | os.W_OK)
    )


def _command(file, directory, start, hardware=False):
    args = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-re", "-ss", str(start), "-i", str(file), "-map", "0:v:0", "-map", "0:a:0?"]
    if hardware:
        # Decoding remains on CPU; Intel/VAAPI performs H.264 encoding.
        args += ["-vf", "scale=w=1280:h=720:force_original_aspect_ratio=decrease,"
                 "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=nv12,hwupload",
                 "-vaapi_device", "/dev/dri/renderD128", "-c:v", "h264_vaapi",
                 "-b:v", "2500k", "-maxrate", "3200k", "-bufsize", "5000k"]
    else:
        args += ["-vf", "scale=w=1280:h=720:force_original_aspect_ratio=decrease,"
                 "pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                 "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
                 "-pix_fmt", "yuv420p", "-crf", "26",
                 "-maxrate", "3200k", "-bufsize", "5000k"]
    args += ["-c:a", "aac", "-ac", "2", "-b:a", "128k", "-ar", "48000",
             "-force_key_frames", "expr:gte(t,n_forced*4)",
             "-sc_threshold", "0", "-f", "hls", "-hls_time", "4",
             "-hls_list_size", "8",
             "-hls_delete_threshold", "2",
             "-hls_flags", "delete_segments+temp_file+independent_segments",
             "-hls_segment_filename", str(directory / "segment_%06d.ts"),
             str(directory / "index.m3u8")]
    return args


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
def start_hls(media_id: int, start: float = Query(0, ge=0, le=10000000)):
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
        if len(ACTIVE) >= MAX_SESSIONS:
            raise HTTPException(429, "Two streams are already active")
        token = secrets.token_hex(16)
        directory = ROOT / token
        directory.mkdir(mode=0o700)
        hardware = hardware_available()
        try:
            command = _command(file, directory, start, hardware)
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
            )
        except OSError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(503, "Unable to start transcoder") from exc
        now = time.monotonic()
        session = Session(token, directory, process, now, now, media_id,
                          "Intel VAAPI" if hardware else "CPU", probe_duration(file), start)
        ACTIVE[token] = session
        return {"session": token,
                "playlist": f"/api/stream/hls/{token}/index.m3u8",
                "engine": session.acceleration,
                "duration": session.duration, "start": start}


@router.get("/{token}/status")
def stream_status(token: str):
    session = _get_session(token)
    playlist = session.directory / "index.m3u8"
    code = session.process.poll()
    if code is not None and code != 0 and not playlist.exists():
        # Some driver/codec combinations cannot use VAAPI; restart with CPU.
        if session.acceleration == "Intel VAAPI":
            with LOCK:
                if ACTIVE.get(token) is session:
                    try:
                        session.process = subprocess.Popen(
                            _command(_item(session.media_id)[1], session.directory,
                                     session.start, False),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True,
                        )
                        session.acceleration = "CPU fallback"
                        code = None
                    except OSError:
                        pass
        if code is not None:
            raise HTTPException(422, "Transcoder could not decode this video")
    return {"ready": playlist.is_file(), "engine": session.acceleration,
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
