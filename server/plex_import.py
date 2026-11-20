"""Import Plex watched flags to local playback history; Plex is never modified."""
import ipaddress
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .catalog import episode_info, movie_info
from .library import db

router = APIRouter(prefix="/api/plex")
LOCK = RLock()
CONFIG = Path(os.environ.get("PLEX_SETTINGS_PATH", "/data/plex-settings.json"))
MAX_ITEMS = 50000
PAGE_SIZE = 250

class PlexConnection(BaseModel):
    url: str = Field(min_length=10, max_length=180)
    token: str = Field(min_length=6, max_length=512)

def _base_url(value):
    parts = urllib.parse.urlsplit(value.strip())
    try:
        host = (parts.hostname or "").lower()
        port = parts.port
        if parts.scheme != "http" or port != 32400 or parts.username or parts.password:
            raise ValueError
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError
        if host not in ("localhost", "host.docker.internal", "plex"):
            addr = ipaddress.ip_address(host)
            if not isinstance(addr, ipaddress.IPv4Address):
                raise ValueError
            if not (addr.is_private or addr.is_loopback) or addr.is_link_local:
                raise ValueError
            if addr.is_unspecified or addr.is_multicast or addr.is_reserved:
                raise ValueError
        return "http://" + host + ":32400"
    except (ValueError, TypeError) as error:
        raise HTTPException(422, "Use a local Plex address on port 32400 (for example http://host.docker.internal:32400)") from error

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(_NoRedirect)

def _plex_get(url, token, path, params=None):
    params = dict(params or {})
    start = params.pop("X-Plex-Container-Start", None)
    size = params.pop("X-Plex-Container-Size", None)
    query = urllib.parse.urlencode(params)
    target = url + path + ("?" + query if query else "")
    headers = {
        "Accept": "application/json",
        "X-Plex-Token": token,
        "X-Plex-Client-Identifier": "one-eyed-willie-plex-import",
        "User-Agent": "OneEyedWillie/1.0",
    }
    if start is not None:
        headers["X-Plex-Container-Start"] = str(start)
    if size is not None:
        headers["X-Plex-Container-Size"] = str(size)
    request = urllib.request.Request(target, headers=headers)
    try:
        with OPENER.open(request, timeout=12) as response:
            raw = response.read(8_000_000)
            content_type = response.headers.get("Content-Type", "")
        if "json" in content_type or raw.lstrip().startswith(b"{"):
            return json.loads(raw)["MediaContainer"]
        # Plex may still reply with XML when JSON is not negotiated.
        root = ET.fromstring(raw)
        def elem(node):
            result = dict(node.attrib)
            if node.tag == "Directory" or node.tag == "Video":
                result["type"] = node.get("type", "")
            return result
        return {"size": root.get("size"), "totalSize": root.get("totalSize"),
                "Directory": [elem(n) for n in root.findall("Directory")],
                "Metadata": [elem(n) for n in list(root) if n.tag in ("Video", "Directory")]}
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(401, "Plex rejected the authentication token. Verify that you copied only the token value, or generate a fresh Plex token.") from None
        if error.code in (301, 302, 307, 308):
            raise HTTPException(502, "Plex redirected the local connection. Check Plex Settings → Network → Secure connections and whether the local server address is correct.") from None
        raise HTTPException(502, "Plex responded with HTTP " + str(error.code) + " while reading its library.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HTTPException(502, "Cannot reach Plex from the Yarr Media server. Check that Plex is running, its LAN address and port 32400, and Docker network access.") from None
    except (ValueError, ET.ParseError, KeyError, TypeError):
        raise HTTPException(502, "Plex returned an unreadable library response. Check that the address points to your Plex Media Server.") from None

def _read():
    try:
        data = json.loads(CONFIG.read_text())
        return {"url": _base_url(data["url"]), "token": str(data["token"])}
    except FileNotFoundError:
        raise HTTPException(409, "Connect Plex in Settings → Integrations first")
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise HTTPException(500, "Plex connection settings are invalid") from error

def _require_config():
    with LOCK:
        return _read()

@router.get("/settings")
def get_settings():
    try:
        setting = _require_config()
    except HTTPException as error:
        if error.status_code == 409:
            return {"connected": False, "address": ""}
        raise
    return {"connected": True, "address": setting["url"]}

@router.put("/settings")
def save_settings(payload: PlexConnection):
    url = _base_url(payload.url)
    token = payload.token.strip()
    _plex_get(url, token, "/library/sections")
    with LOCK:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".plex-", dir=CONFIG.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"url": url, "token": token}, stream)
                stream.write("\n")
            os.chmod(temp, 0o600)
            os.replace(temp, CONFIG)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return {"connected": True, "address": url}

@router.delete("/settings")
def remove_settings():
    with LOCK:
        CONFIG.unlink(missing_ok=True)
    return {"connected": False}

def _number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

def _watched(entry):
    return (_number(entry.get("viewCount")) or 0) > 0 or bool(_number(entry.get("lastViewedAt")))

def _plex_items(url, token):
    sections = _plex_get(url, token, "/library/sections").get("Directory") or []
    output = []
    for section in sections:
        kind = section.get("type")
        if kind not in ("movie", "show"):
            continue
        section_id = _number(section.get("key"))
        if section_id is None:
            continue
        # For shows fetch episodes (type 4), not show-level watched markers.
        params = {"type": 1 if kind == "movie" else 4}
        for offset in range(0, MAX_ITEMS, PAGE_SIZE):
            batch = _plex_get(url, token, "/library/sections/" + str(section_id) + "/all",
                              {**params, "X-Plex-Container-Start": offset,
                               "X-Plex-Container-Size": PAGE_SIZE})
            rows = batch.get("Metadata") or []
            if not isinstance(rows, list):
                break
            for row in rows:
                if isinstance(row, dict) and _watched(row):
                    output.append((kind, row))
            total = _number(batch.get("totalSize"))
            if not rows or (total is not None and offset + len(rows) >= total) or len(rows) < PAGE_SIZE:
                break
    return output

def _local_catalog():
    movies = defaultdict(list)
    episodes = defaultdict(list)
    with db() as conn:
        libraries = conn.execute("SELECT id,kind,path FROM libraries").fetchall()
        for library in libraries:
            entries = conn.execute(
                "SELECT m.id,m.path,p.completed FROM media m "
                "LEFT JOIN playback_progress p ON p.media_id=m.id AND p.viewer='' WHERE m.library_id=?",
                (library["id"],),
            ).fetchall()
            for entry in entries:
                try:
                    parsed = (movie_info(entry["path"], library["path"])
                              if library["kind"] == "movies" else episode_info(entry["path"], library["path"]))
                except (ValueError, OSError):
                    continue
                base = {"id": entry["id"], "watched": bool(entry["completed"]),
                        "year": parsed["year"]}
                if library["kind"] == "movies":
                    movies[_norm(parsed["title"])].append(base)
                elif parsed["season"] is not None and parsed["episode"] is not None:
                    episodes[(_norm(parsed["title"]), parsed["season"], parsed["episode"])].append(base)
    return movies, episodes

def _matches():
    setting = _require_config()
    plex = _plex_items(setting["url"], setting["token"])
    movies, episodes = _local_catalog()
    matched, ambiguous, unmatched = set(), 0, 0
    for kind, item in plex:
        if kind == "movie":
            title = item.get("title")
            candidates = movies.get(_norm(title), [])
            year = _number(item.get("year"))
            if year is not None:
                candidates = [c for c in candidates if c["year"] == year]
            # An unyearned local title cannot safely match multiple editions.
        else:
            title = item.get("grandparentTitle")
            season = _number(item.get("parentIndex"))
            number = _number(item.get("index"))
            candidates = episodes.get((_norm(title), season, number), [])
        if len(candidates) != 1:
            if candidates:
                ambiguous += 1
            else:
                unmatched += 1
            continue
        if not candidates[0]["watched"]:
            matched.add(candidates[0]["id"])
    return matched, {"plex_watched": len(plex), "new_matches": len(matched),
                     "unmatched": unmatched, "ambiguous": ambiguous}

@router.get("/import/preview")
def preview_import():
    _, summary = _matches()
    return summary

class ImportRequest(BaseModel):
    confirm: bool

@router.post("/import")
def import_watched(payload: ImportRequest):
    if not payload.confirm:
        raise HTTPException(422, "Confirm the watched import before applying it")
    with LOCK:
        matched, summary = _matches()
        if matched:
            with db() as conn:
                conn.executemany(
                    "INSERT INTO playback_progress "
                    "(viewer,media_id,position_seconds,duration_seconds,completed,updated_at) "
                    "VALUES('',?,0,0,1,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(viewer,media_id) DO UPDATE SET "
                    "completed=1,updated_at=CURRENT_TIMESTAMP",
                    [(id,) for id in sorted(matched)],
                )
                conn.commit()
        summary["imported"] = len(matched)
        return summary
