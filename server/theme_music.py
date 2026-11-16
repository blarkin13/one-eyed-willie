"""Local theme playback and on-demand personal TV theme downloads.

TelevisionTunes provides public, personal-listening MP3 downloads. This module
fetches only an exact show match on first use, never bulk crawls the site and
never sends the site's recordings to third parties.
"""
import hashlib
import time
import html
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .library import MEDIA_ROOT
from .playback import _item

router = APIRouter(prefix="/api/themes")
EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav")
MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".flac": "audio/flac", ".wav": "audio/wav"}
MAX_BYTES = 50 * 1024 * 1024
_lock = threading.RLock()
_failures = {}  # short-lived failure diagnostics; do not retry every page view
FAILURE_TTL = 120


def theme_for_media(media_id):
    item, video = _item(media_id)
    root = Path(item["root"]).resolve(strict=True)
    if item["kind"] == "tv":
        relative = video.relative_to(root)
        if len(relative.parts) < 2:
            return None
        folder = root / relative.parts[0]
    elif item["kind"] == "movies":
        folder = video.parent
        if folder == root:
            return None
    else:
        return None
    try:
        folder = folder.resolve(strict=True)
        if not folder.is_dir() or not folder.is_relative_to(root):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    for extension in EXTENSIONS:
        candidate = folder / ("theme" + extension)
        try:
            if candidate.is_symlink():
                continue
            resolved = candidate.resolve(strict=True)
            if (resolved.is_relative_to(folder) and resolved.is_relative_to(MEDIA_ROOT)
                    and resolved.is_file() and 0 < resolved.stat().st_size <= MAX_BYTES):
                return resolved
        except (OSError, ValueError, RuntimeError):
            continue
    return None


class _ThemePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h1 = False
        self.heading = ""
        self.links = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "h1":
            self.in_h1 = True
        if tag == "a" and attrs.get("href", "").startswith(
                ("/download.php?", "https://televisiontunes.com/download.php?",
                 "https://www.televisiontunes.com/download.php?")):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_h1:
            self.heading += data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url, accept, max_length):
    request = urllib.request.Request(url, headers={
        "User-Agent": "OneEyedWillie/1.0 (personal listening)",
        "Accept": accept})
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=8) as response:
        if response.status != 200:
            raise ValueError("Unexpected response")
        data = response.read(max_length + 1)
        if len(data) > max_length:
            raise ValueError("Response too large")
        return data, response.headers.get("Content-Type", "").lower()


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _download_theme(media_id):
    from .catalog import episode_info
    item, video = _item(media_id)
    if item["kind"] != "tv":
        return None, "tv_only_source"
    title = str(episode_info(str(video), item["root"]).get("title") or "").strip()
    if not title:
        return None, "title_not_recognized"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    candidates = [slug]
    if title.casefold().startswith("the "):
        tail = re.sub(r"[^A-Za-z0-9]+", "_", title[4:]).strip("_")
        candidates.insert(0, tail + "_(The)")
    directory = Path(os.environ.get("THEME_CACHE_DIR", "/data/theme-cache"))
    key = hashlib.sha256(title.casefold().encode()).hexdigest()
    cached = directory / (key + ".mp3")
    with _lock:
        if cached.is_file() and not cached.is_symlink() and 0 < cached.stat().st_size <= MAX_BYTES:
            _failures.pop(key, None)
            return cached, None
        previous = _failures.get(key)
        if previous and previous[0] > time.monotonic():
            return None, previous[1]

        failure = "not_available_from_source"
        for candidate in dict.fromkeys(candidates):
            page_url = "https://televisiontunes.com/" + urllib.parse.quote(candidate, safe="_()") + ".html"
            try:
                page_bytes, kind = _fetch(page_url, "text/html", 750_000)
                if "html" not in kind:
                    failure = "unexpected_source_response"
                    continue
                page = _ThemePage()
                page.feed(page_bytes.decode("utf-8", "replace"))
                # The site has presented both "The Big Bang Theory" and
                # "The Big Bang Theory - Theme Song" as H1 text.
                heading = html.unescape(page.heading).strip()
                normalized = _norm(heading)
                if normalized not in (_norm(title), _norm(title + " - Theme Song")):
                    failure = "source_title_mismatch"
                    continue
                download_url = None
                for href in page.links:
                    url = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, html.unescape(href)))
                    if (url.scheme != "https" or url.hostname not in
                            ("televisiontunes.com", "www.televisiontunes.com")
                            or url.path != "/download.php"):
                        continue
                    if urllib.parse.parse_qs(url.query).get("f") == [candidate]:
                        download_url = urllib.parse.urlunsplit(url)
                        break
                if not download_url:
                    failure = "source_download_link_unrecognized"
                    continue
                audio, content_type = _fetch(download_url, "audio/mpeg", MAX_BYTES)
                if not (content_type.startswith("audio/mpeg")
                        or content_type.startswith("application/octet-stream")):
                    failure = "unexpected_source_response"
                    continue
                if not audio.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                    failure = "unexpected_source_response"
                    continue
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd, tmp = tempfile.mkstemp(prefix=".theme-", dir=directory)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(audio)
                    os.chmod(tmp, 0o600)
                    os.replace(tmp, cached)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                _failures.pop(key, None)
                return cached, None
            except urllib.error.HTTPError as error:
                if error.code in (401, 403, 429):
                    # Respect the site's decision; do not rotate hosts or user
                    # agents to work around access restrictions.
                    failure = "source_access_denied"
                    break
                if error.code not in (404, 410):
                    failure = "source_unreachable"
            except (urllib.error.URLError, OSError, ValueError):
                failure = "source_unreachable"
        _failures[key] = (time.monotonic() + FAILURE_TTL, failure)
        return None, failure

@router.get("/{media_id}/info")
def theme_info(media_id: int):
    local = theme_for_media(media_id)
    if local:
        return {"available": True, "source": "local",
                "url": f"/api/themes/{media_id}/audio"}
    downloaded, reason = _download_theme(media_id)
    return {"available": bool(downloaded),
            "source": "televisiontunes" if downloaded else None,
            "reason": reason,
            "url": f"/api/themes/{media_id}/audio" if downloaded else None}


@router.get("/{media_id}/audio")
def theme_audio(media_id: int):
    audio = theme_for_media(media_id)
    if not audio:
        audio, _ = _download_theme(media_id)
    if not audio:
        raise HTTPException(404, "No theme music available for this title")
    return FileResponse(audio, media_type=MIME[audio.suffix.lower()],
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff",
                                 "Content-Disposition": "inline"})
