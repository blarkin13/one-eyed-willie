"""Downloads for watching offline in the phone app (a Pro feature).

The phone asks for a title at a quality. The server prepares one phone-ready
MP4 (H.264/HEVC video, AAC stereo audio, moov atom first) in the background,
and the phone downloads it with byte ranges, so an interrupted download
resumes. Prepared files are shared by everyone who downloads the same title at
the same quality, and removed a few days after their last download.

Pro: yarr.media tells the server whether its owner has Pro (heartbeat reply).
People the owner shares with (Barnacles) download through the owner's Pro and
only from the libraries shared with them. Original files are never changed.
"""
import os
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from . import hls, yarr_pairing
from .library import db
from .media_probe import inspect_media
from .playback import _item, probe_duration
from .viewer import current as current_viewer

router = APIRouter(prefix="/api/downloads", tags=["downloads"])
ROOT = Path(os.environ.get("DOWNLOADS_DIR", "/data/downloads"))
ORIGINAL = "original"
TIERS = ("1080p", "720p", "480p", "360p")
KEEP_SECONDS = 3 * 86400            # prepared copies live this long after their last download
FAILED_SECONDS = 86400
MAX_TOTAL_BYTES = int(float(os.environ.get("DOWNLOADS_MAX_GB", "60")) * 1024 ** 3)
PHONE_VIDEO = {"h264", "hevc"}
JOB_ID = r"[a-f0-9]{32}"
_lock = threading.Lock()
_wake = threading.Event()
_running = {}                       # job id -> subprocess.Popen


# ---- Access --------------------------------------------------------------------
def access():
    """(allowed, reason). Reason: not_connected | pro_required."""
    record = yarr_pairing.pro_state()
    if not record["paired"]:
        return False, "not_connected"
    if not record["owner_pro"]:
        return False, "pro_required"
    return True, None


def _require_access():
    allowed, reason = access()
    if not allowed:
        raise HTTPException(403, {"error": reason})


@router.get("/status")
def download_status():
    allowed, reason = access()
    return {"allowed": allowed, "reason": reason}


# ---- Jobs ----------------------------------------------------------------------
def _setup(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS download_jobs (
        id TEXT PRIMARY KEY, media_id INTEGER NOT NULL, quality TEXT NOT NULL,
        audio INTEGER NOT NULL DEFAULT 0, source_mtime INTEGER NOT NULL,
        status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, bytes INTEGER,
        direct INTEGER NOT NULL DEFAULT 0, error TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL, accessed_at REAL NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS download_jobs_key ON download_jobs(media_id,quality,audio,source_mtime)")


def _row(job_id):
    with db() as conn:
        _setup(conn)
        return conn.execute("SELECT * FROM download_jobs WHERE id=?", (job_id,)).fetchone()


def _update(job_id, **fields):
    fields["updated_at"] = time.time()
    with db() as conn:
        conn.execute("UPDATE download_jobs SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                     (*fields.values(), job_id))


def _public(row):
    return {"id": row["id"], "media_id": row["media_id"], "quality": row["quality"], "audio": row["audio"],
            "status": row["status"], "progress": round(row["progress"] or 0, 3), "bytes": row["bytes"],
            "error": row["error"],
            "file_url": f"/api/downloads/jobs/{row['id']}/file" if row["status"] == "ready" else None}


def _part(job_id):
    return ROOT / f"{job_id}.part.mp4"


def _done(job_id):
    return ROOT / f"{job_id}.mp4"


def _profile(file):
    profile = inspect_media(file) or {}
    return (str(profile.get("video_codec") or "").lower(), str(profile.get("audio_codec") or "").lower(),
            float(profile.get("duration") or 0) or probe_duration(file))


def _original_mode(file):
    """("direct" | "remux" | None, reason)."""
    video, audio, _ = _profile(file)
    if video not in PHONE_VIDEO:
        return None, "Pick a quality: this video's format needs converting for phones."
    if hls.has_dolby_vision(file):
        return None, "Pick a quality: Dolby Vision video needs converting for phones."
    if file.suffix.lower() in (".mp4", ".m4v") and audio in ("aac", "mp3") and video == "h264":
        return "direct", None
    return "remux", None


def _command(file, out, quality, audio, hardware):
    base = [hls.FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y"]
    if quality == ORIGINAL:
        video_codec, _, _ = _profile(file)
        return base + ["-i", str(file), "-map", "0:v:0", "-map", f"0:a:{int(audio)}?",
                       "-c:v", "copy", *(["-tag:v", "hvc1"] if video_codec == "hevc" else []),
                       "-c:a", "aac", "-ac", "2", "-b:a", "192k", "-ar", "48000",
                       "-movflags", "+faststart", "-f", "mp4", str(out)]
    preset = hls.QUALITIES[quality]
    width, height = preset["width"], preset["height"]
    args = list(base)
    if hardware:
        args += ["-vaapi_device", "/dev/dri/renderD128"]
    args += ["-i", str(file), "-map", "0:v:0", "-map", f"0:a:{int(audio)}?"]
    if hardware:
        args += ["-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,format=nv12,hwupload",
                 "-c:v", "h264_vaapi", "-b:v", f"{preset['target']}k",
                 "-maxrate", f"{preset['maxrate']}k", "-bufsize", f"{preset['bufsize']}k"]
    else:
        # Downloads aren't watched live: a slower preset gives a smaller file.
        args += ["-vf", f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease:force_divisible_by=2",
                 "-c:v", "libx264", "-preset", "faster", "-threads", "2", "-pix_fmt", "yuv420p"]
        args += (["-b:v", f"{preset['target']}k"] if preset.get("abr") else ["-crf", str(preset["crf"])])
        args += ["-maxrate", f"{preset['maxrate']}k", "-bufsize", f"{preset['bufsize']}k"]
    return args + ["-c:a", "aac", "-ac", "2", "-b:a", f"{preset['audio']}k", "-ar", "48000",
                   "-movflags", "+faststart", "-f", "mp4", str(out)]


def _free_bytes():
    try:
        return shutil.disk_usage(ROOT).free
    except OSError:
        return 0


def _run(job_id):
    row = _row(job_id)
    if row is None or row["status"] != "queued":
        return
    try:
        _, file = _item(row["media_id"])
    except HTTPException:
        _update(job_id, status="failed", error="The file is no longer available.")
        return
    if _free_bytes() < hls.MIN_FREE_BYTES * 4:
        _update(job_id, status="failed", error="The server is low on disk space.")
        return
    _, _, duration = _profile(file)
    out = _part(job_id)
    _update(job_id, status="preparing", progress=0)
    for hardware in ([True, False] if row["quality"] != ORIGINAL and hls.hardware_available() else [False]):
        command = _command(file, out, row["quality"], row["audio"], hardware)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _running[job_id] = process
        last = 0.0
        for line in process.stdout:
            if line.startswith("out_time_us=") and duration:
                try:
                    done = min(0.99, int(line.split("=", 1)[1]) / 1e6 / duration)
                except ValueError:
                    continue
                if done - last >= 0.01:
                    last = done
                    _update(job_id, progress=done)
        error = (process.stderr.read() or "")[-400:]
        code = process.wait()
        _running.pop(job_id, None)
        if code == 0 and out.is_file() and out.stat().st_size > 0:
            os.replace(out, _done(job_id))
            _update(job_id, status="ready", progress=1, bytes=_done(job_id).stat().st_size)
            return
        out.unlink(missing_ok=True)
        if _row(job_id) is None:   # removed while running
            return
    _update(job_id, status="failed", error=(error.strip() or "Preparing the download failed.")[:400])


def worker_loop(stop):
    """One download is prepared at a time, so streaming stays smooth."""
    ROOT.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        _setup(conn)
        # A restart interrupts preparation: queue those again.
        conn.execute("UPDATE download_jobs SET status='queued',progress=0 WHERE status='preparing'")
    while not stop.is_set():
        with db() as conn:
            row = conn.execute("SELECT id FROM download_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if row:
            try:
                _run(row["id"])
            except Exception as error:   # never let one bad file stop the queue
                _update(row["id"], status="failed", error=str(error)[:400])
            continue
        cleanup()
        _wake.wait(60)
        _wake.clear()


def cleanup(now=None):
    now = now or time.time()
    with db() as conn:
        _setup(conn)
        stale = conn.execute(
            "SELECT id,direct FROM download_jobs WHERE (status='ready' AND accessed_at<?) OR "
            "(status='failed' AND updated_at<?)", (now - KEEP_SECONDS, now - FAILED_SECONDS)).fetchall()
        ready = conn.execute("SELECT id,bytes FROM download_jobs WHERE status='ready' AND direct=0 "
                             "ORDER BY accessed_at DESC").fetchall()
    doomed = [r["id"] for r in stale]
    total = 0
    for r in ready:                       # keep the most recently used copies under the size cap
        total += r["bytes"] or 0
        if total > MAX_TOTAL_BYTES and r["id"] not in doomed:
            doomed.append(r["id"])
    for job_id in doomed:
        _done(job_id).unlink(missing_ok=True)
        _part(job_id).unlink(missing_ok=True)
    if doomed:
        with db() as conn:
            conn.executemany("DELETE FROM download_jobs WHERE id=?", [(j,) for j in doomed])
    return len(doomed)


# ---- API -----------------------------------------------------------------------
@router.get("/options/{media_id}")
def download_options(media_id: int):
    row, file = _item(media_id)
    if row["kind"] not in ("movies", "tv"):
        raise HTTPException(404, "Only movies and TV episodes are downloaded here")
    allowed, reason = access()
    _, _, seconds = _profile(file)
    size = file.stat().st_size
    mode, why = _original_mode(file)
    hardware = hls.hardware_available()
    options = [{"quality": ORIGINAL, "label": "Original quality", "available": mode is not None,
                "reason": why, "bytes": size, "kind": "about"}]
    for tier in TIERS:
        kbps, kind = hls.estimate_kbps(hls.QUALITIES[tier], hardware)
        options.append({"quality": tier, "label": tier, "available": True, "reason": None,
                        "bytes": int(kbps * 1000 / 8 * seconds * 1.01) if seconds else 0, "kind": kind})
    return {"media_id": media_id, "allowed": allowed, "reason": reason, "duration_seconds": seconds,
            "audio_tracks": hls.list_audio_tracks(file), "default": "720p", "options": options}


@router.post("/prepare/{media_id}")
def prepare_download(media_id: int, quality: str = Query("720p"), audio: int = Query(0, ge=0, le=64)):
    _require_access()
    row, file = _item(media_id)
    if row["kind"] not in ("movies", "tv"):
        raise HTTPException(404, "Only movies and TV episodes are downloaded here")
    if quality != ORIGINAL and quality not in TIERS:
        raise HTTPException(422, "Unknown quality")
    mtime = file.stat().st_mtime_ns
    direct = False
    if quality == ORIGINAL:
        mode, why = _original_mode(file)
        if mode is None:
            raise HTTPException(409, why)
        direct = mode == "direct" and audio == 0
    now = time.time()
    with _lock, db() as conn:
        _setup(conn)
        existing = conn.execute(
            "SELECT * FROM download_jobs WHERE media_id=? AND quality=? AND audio=? AND source_mtime=? "
            "AND status IN ('queued','preparing','ready') ORDER BY created_at DESC LIMIT 1",
            (media_id, quality, audio, mtime)).fetchone()
        if existing:
            conn.execute("UPDATE download_jobs SET accessed_at=? WHERE id=?", (now, existing["id"]))
            return _public(existing)
        job_id = secrets.token_hex(16)
        status = "ready" if direct else "queued"
        conn.execute("INSERT INTO download_jobs(id,media_id,quality,audio,source_mtime,status,progress,bytes,direct,"
                     "created_at,updated_at,accessed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (job_id, media_id, quality, audio, mtime, status, 1 if direct else 0,
                      file.stat().st_size if direct else None, 1 if direct else 0, now, now, now))
        created = conn.execute("SELECT * FROM download_jobs WHERE id=?", (job_id,)).fetchone()
    _wake.set()
    return _public(created)


def _visible_job(job_id):
    row = _row(job_id)
    if row is None:
        raise HTTPException(404, "Download not found")
    with db() as conn:
        media = conn.execute("SELECT library_id FROM media WHERE id=?", (row["media_id"],)).fetchone()
    if media is None or not current_viewer().can_see(media["library_id"]):
        raise HTTPException(404, "Download not found")
    return row


@router.get("/jobs/{job_id}")
def download_job(job_id: str):
    if not _valid_id(job_id):
        raise HTTPException(404, "Download not found")
    return _public(_visible_job(job_id))


@router.get("/jobs/{job_id}/file")
@router.head("/jobs/{job_id}/file")
def download_file(job_id: str):
    if not _valid_id(job_id):
        raise HTTPException(404, "Download not found")
    _require_access()
    row = _visible_job(job_id)
    if row["status"] != "ready":
        raise HTTPException(409, "Not ready yet")
    if row["direct"]:
        _, path = _item(row["media_id"])
    else:
        path = _done(job_id)
        if not path.is_file():
            raise HTTPException(410, "Prepare it again")
    with db() as conn:
        conn.execute("UPDATE download_jobs SET accessed_at=? WHERE id=?", (time.time(), job_id))
    # FileResponse answers Range requests, so an interrupted download resumes.
    return FileResponse(path, media_type="video/mp4", filename=None,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Accept-Ranges": "bytes"})


@router.get("/music/{track_id}")
@router.head("/music/{track_id}")
def download_music(track_id: int):
    """A song for offline use: the original file, resumable. Pro, like video downloads."""
    _require_access()
    from . import music
    path = music._safe_track(track_id)
    with db() as conn:
        row = conn.execute("SELECT library_id FROM media WHERE id=?", (track_id,)).fetchone()
    if row is None or not current_viewer().can_see(row["library_id"]):
        raise HTTPException(404, "Track not found")
    return FileResponse(path, media_type="application/octet-stream", filename=None,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Accept-Ranges": "bytes"})


def _valid_id(job_id):
    return len(job_id) == 32 and all(c in "0123456789abcdef" for c in job_id)
