"""Server-local artwork cache. Browsers never fetch artwork from metadata providers.

Images are downloaded at most once per remote URL into /data/artwork, which is
mounted persistently outside the container. Only two fixed image CDNs are
permitted; redirects and private/network addresses are never followed.
"""
import hashlib
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Lock, Semaphore

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
Image.MAX_IMAGE_PIXELS = 40_000_000

from .library import db, MEDIA_ROOT

router = APIRouter(prefix="/api")
CACHE_DIR = Path(os.environ.get("ARTWORK_CACHE_DIR", "/data/artwork"))
THUMB_DIR = CACHE_DIR / "thumbs"
HEX = re.compile(r"^[0-9a-f]{64}$")
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 9
FAILED_RETRY_SECONDS = 60 * 60
_download_limit = Semaphore(3)
_lock_guard = Lock()
_item_locks = {}


def _locks_for(key):
    with _lock_guard:
        return _item_locks.setdefault(key, Lock())


def _table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS artwork_assets (
        digest TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
        mime TEXT, last_failed INTEGER NOT NULL DEFAULT 0
    )""")


def _trusted_remote(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.port not in (None, 443):
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        if parsed.hostname == "static.tvmaze.com":
            return parsed.path.startswith("/uploads/images/") and ".." not in parsed.path
        if parsed.hostname == "image.tmdb.org":
            return parsed.path.startswith("/t/p/") and ".." not in parsed.path
    except ValueError:
        pass
    return False


def _register(source, kind, version=""):
    digest = hashlib.sha256((kind + ":" + source + ":" + version).encode()).hexdigest()
    with db() as conn:
        _table(conn)
        conn.execute(
            "INSERT OR IGNORE INTO artwork_assets(digest,source,kind) VALUES(?,?,?)",
            (digest, source, kind),
        )
    return "/api/artwork/" + digest


def register_remote(url):
    if _trusted_remote(url):
        return _register(url, "remote")
    return None


RADARR_IMAGE = re.compile(
    r"^/MediaCover/[0-9]+/(poster|fanart)(?:-[0-9]+)?\.(jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)


def register_radarr(source):
    """Register a Radarr-hosted cover without passing API credentials to a browser."""
    if not isinstance(source, str):
        return None
    from .movies import _settings
    config = _settings()
    if not config:
        return None
    # Radarr also returns query parameters such as lastWrite; these do not
    # identify a different movie and are omitted for a stable cache key.
    parsed = urllib.parse.urlsplit(source)
    if parsed.scheme or parsed.netloc:
        candidate = parsed.scheme + "://" + parsed.netloc
        if candidate != config["url"]:
            return None
    path = parsed.path
    if not RADARR_IMAGE.fullmatch(path):
        return None
    return _register(config["url"] + path, "radarr")


def _radarr_bytes(source):
    from .movies import _settings
    config = _settings()
    if not config:
        raise ValueError("Radarr connection unavailable")
    if not source.startswith(config["url"] + "/MediaCover/"):
        raise ValueError("Unexpected Radarr artwork address")
    parsed = urllib.parse.urlsplit(source)
    if not RADARR_IMAGE.fullmatch(parsed.path):
        raise ValueError("Invalid Radarr artwork path")
    request = urllib.request.Request(source, headers={
        "X-Api-Key": config["api_key"],
        "Accept": "image/jpeg,image/png,image/webp",
        "User-Agent": "OneEyedWillie/0.8",
    })
    opener = urllib.request.build_opener(_SafeRedirect())
    with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        mime = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if mime not in IMAGE_CONTENT_TYPES:
            raise ValueError("Unsupported Radarr image")
        data = response.read(MAX_IMAGE_BYTES + 1)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Radarr image too large")
        return data, mime


def register_local(path):
    try:
        candidate = Path(path)
        if candidate.is_symlink():
            return None
        real = candidate.resolve(strict=True)
        if (not real.is_relative_to(MEDIA_ROOT) or not real.is_file()
                or real.stat().st_size > MAX_IMAGE_BYTES
                or real.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp")):
            return None
    except (OSError, ValueError):
        return None
    return _register(str(real), "local", str(real.stat().st_mtime_ns))


def local_show_poster(library_id, key):
    """Find optional poster.jpg alongside TV show files, safely in the media mount."""
    from .catalog import episode_info
    with db() as conn:
        lib = conn.execute("SELECT kind,path FROM libraries WHERE id=?", (library_id,)).fetchone()
        if lib is None or lib["kind"] != "tv":
            return None
        rows = conn.execute(
            "SELECT path,source_root FROM media WHERE library_id=? ORDER BY path", (library_id,)
        ).fetchall()
    root = Path(lib["path"])
    for row in rows:
        path = Path(row["path"])
        root = Path(row["source_root"] or lib["path"])
        try:
            parsed = episode_info(path, root)
            if parsed["key"] != key:
                continue
            relative = path.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) < 2:
            continue
        show_folder = root / relative.parts[0]
        for name in ("poster.jpg", "poster.png", "folder.jpg", "folder.png",
                     "cover.jpg", "cover.png"):
            poster = register_local(show_folder / name)
            if poster:
                return poster
        return None
    return None


def localize(value):
    """Return local artwork URLs; keep the metadata database provider-neutral."""
    if isinstance(value, list):
        return [localize(v) for v in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ("poster_url", "backdrop_url", "still_url", "logo_url"):
                result[key] = register_remote(item) if item else None
            else:
                result[key] = localize(item)
        return result
    return value


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _trusted_remote(newurl):
            return None
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _download(source):
    if not _trusted_remote(source):
        raise ValueError("Untrusted artwork source")
    request = urllib.request.Request(source, headers={
        "Accept": "image/jpeg,image/png,image/webp",
        "User-Agent": "OneEyedWillie/0.7 (local artwork cache)",
    })
    opener = urllib.request.build_opener(_SafeRedirect())
    with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        mime = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if mime not in IMAGE_CONTENT_TYPES:
            raise ValueError("Unsupported image content type")
        data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES or not data:
            raise ValueError("Artwork image too large or empty")
        return data, mime


def _bytes_for(source, kind):
    if kind == "remote":
        return _download(source)
    if kind == "radarr":
        return _radarr_bytes(source)
    if kind == "local":
        path = Path(source)
        if path.is_symlink():
            raise ValueError("Local symlink not allowed")
        real = path.resolve(strict=True)
        if not real.is_relative_to(MEDIA_ROOT):
            raise ValueError("Local artwork escaped media mount")
        mime = {".png": "image/png", ".webp": "image/webp",
                ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}.get(real.suffix.lower())
        if not mime or real.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Unsupported local artwork")
        data = real.read_bytes()
        if not data:
            raise ValueError("Empty local artwork")
        return data, mime
    raise ValueError("Unknown artwork kind")


def _save(digest, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".art-", dir=CACHE_DIR)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CACHE_DIR / digest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@router.get("/artwork/{digest}")
def artwork(digest: str):
    if not HEX.fullmatch(digest):
        raise HTTPException(404, "Artwork not found")
    with db() as conn:
        _table(conn)
        record = conn.execute(
            "SELECT source,kind,mime,last_failed FROM artwork_assets WHERE digest=?",
            (digest,),
        ).fetchone()
    if not record:
        raise HTTPException(404, "Artwork not found")
    path = CACHE_DIR / digest
    if not path.is_file():
        with _locks_for(digest):
            if not path.is_file():
                if time.time() - record["last_failed"] < FAILED_RETRY_SECONDS:
                    raise HTTPException(404, "Artwork temporarily unavailable")
                try:
                    with _download_limit:
                        data, mime = _bytes_for(record["source"], record["kind"])
                        _save(digest, data)
                    with db() as conn:
                        conn.execute(
                            "UPDATE artwork_assets SET mime=?,last_failed=0 WHERE digest=?",
                            (mime, digest),
                        )
                except (urllib.error.URLError, urllib.error.HTTPError,
                        OSError, ValueError, TimeoutError):
                    with db() as conn:
                        conn.execute(
                            "UPDATE artwork_assets SET last_failed=? WHERE digest=?",
                            (int(time.time()), digest),
                        )
                    raise HTTPException(404, "Artwork temporarily unavailable")
    with db() as conn:
        record = conn.execute(
            "SELECT mime FROM artwork_assets WHERE digest=?", (digest,)
        ).fetchone()
    return FileResponse(
        path, media_type=record["mime"] or "image/jpeg",
        headers={"Cache-Control": "private, max-age=604800",
                 "X-Content-Type-Options": "nosniff"},
    )


def warm_thumbnail(digest):
    """Ensure a small, persistent JPEG exists. Existing registered image stays authoritative."""
    if not HEX.fullmatch(digest):
        return False
    target = THUMB_DIR / (digest + ".jpg")
    if target.is_file():
        return True
    with _locks_for("thumb:" + digest):
        if target.is_file():
            return True
        # Reuse the existing validated source fetch and registration path.
        original = artwork(digest)
        source = Path(original.path)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".thumb-", suffix=".jpg", dir=THUMB_DIR)
        try:
            os.close(fd)
            with Image.open(source) as picture:
                picture = ImageOps.exif_transpose(picture)
                picture.thumbnail((360, 540), Image.Resampling.LANCZOS)
                if picture.mode != "RGB":
                    picture = picture.convert("RGB")
                picture.save(temp, "JPEG", quality=78, optimize=True)
            os.chmod(temp, 0o600)
            os.replace(temp, target)
            return True
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            return False
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


@router.get("/artwork/thumb/{digest}")
def artwork_thumbnail(digest: str):
    if not HEX.fullmatch(digest):
        raise HTTPException(404, "Thumbnail not found")
    if not warm_thumbnail(digest):
        # Preserve the full original poster when an unusual image cannot be resized.
        return artwork(digest)
    return FileResponse(
        THUMB_DIR / (digest + ".jpg"), media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=604800",
                 "X-Content-Type-Options": "nosniff"}
    )


def thumbnail_url(url):
    if isinstance(url, str) and re.fullmatch(r"/api/artwork/[a-f0-9]{64}", url):
        return url.replace("/api/artwork/", "/api/artwork/thumb/", 1)
    return url
