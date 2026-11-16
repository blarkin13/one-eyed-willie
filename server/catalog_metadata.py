"""Independent catalog metadata indexing for genre, rating, and runtime sorting.

Uses existing Radarr/Sonarr connections first (one bulk read each), then
resolved local/TMDB/TV metadata for titles not covered by a media manager.
No network requests occur in the catalog endpoint itself.
"""
import json
import logging
import threading
import time

from fastapi import APIRouter

from .library import db
from .poster_index import _collect, _safe_metadata, _table

router = APIRouter(prefix="/api/catalog/metadata")
log = logging.getLogger(__name__)
_lock = threading.Lock()
_state = {
    "running": False, "processed": 0, "total": 0, "updated": 0,
    "revision": 0, "last_finished": 0, "error": "",
    "available": 0, "missing": 0, "last_signature": None,
}
# Retry incomplete metadata automatically; completed catalogs can refresh less often.
RESCAN_SECONDS = 6 * 60 * 60
MISSING_RETRY_SECONDS = 5 * 60


def _has_metadata(info):
    return bool(info.get("genres")) or info.get("runtime") is not None or info.get("rating") is not None


def _complete(info):
    """A rating alone must not prevent fetching missing genres or runtime."""
    return bool(info.get("genres")) and info.get("runtime") is not None and info.get("rating") is not None


def _combine(primary, additional):
    """Prefer manager values but fill each missing field from resolved metadata."""
    return {
        "genres": primary["genres"] or additional["genres"],
        "rating": primary["rating"] if primary["rating"] is not None else additional["rating"],
        "runtime": primary["runtime"] if primary["runtime"] is not None else additional["runtime"],
    }


def _library_signature():
    # Detect library scans and additions without enumerating folders or media
    # on the request path. A successful scan may replace the newest item.
    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count,COALESCE(MAX(id),0) AS newest,"
            "COALESCE(MAX(mtime_ns),0) AS newest_mtime FROM media"
        ).fetchone()
        libs = conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
    return (row["count"], row["newest"], row["newest_mtime"], libs)


def _matching_movie(title, year, snapshot):
    from .movies import _movie_match
    return _movie_match(title, year, snapshot)


def _matching_series(title, year, snapshot):
    from .metadata import _simple
    normalized = _simple(title)
    choices = [entry for entry in snapshot
               if isinstance(entry, dict) and _simple(entry.get("title")) == normalized]
    if year:
        choices = [entry for entry in choices
                   if not entry.get("year") or abs(int(entry["year"]) - int(year)) <= 1]
    return choices[0] if len(choices) == 1 else {}


def _persist(kind, library_id, key, incoming):
    """Merge useful fields without losing an existing poster or previous metadata."""
    incoming = _safe_metadata(incoming)
    with db() as conn:
        _table(conn)
        row = conn.execute(
            "SELECT metadata_json FROM indexed_posters WHERE kind=? AND library_id=? AND show_key=?",
            (kind, library_id, key),
        ).fetchone()
        existing = {}
        if row and row["metadata_json"]:
            try:
                existing = json.loads(row["metadata_json"])
            except (ValueError, TypeError):
                pass
        existing = _safe_metadata(existing)
        merged = {
            "genres": incoming["genres"] or existing["genres"],
            "rating": incoming["rating"] if incoming["rating"] is not None else existing["rating"],
            "runtime": incoming["runtime"] if incoming["runtime"] is not None else existing["runtime"],
        }
        if merged == existing:
            return False
        conn.execute(
            "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at,metadata_json) "
            "VALUES(?,?,?,NULL,0,?) "
            "ON CONFLICT(kind,library_id,show_key) DO UPDATE SET metadata_json=excluded.metadata_json",
            (kind, library_id, key, json.dumps(merged)),
        )
        return True


def sync_once():
    """Run one complete metadata sync, recording incremental progress."""
    from . import arr, metadata, movies, tv

    titles = _collect()
    with _lock:
        _state["total"] = len(titles)
        _state["processed"] = 0
        _state["updated"] = 0

    try:
        films = movies._snapshot()
    except Exception:
        log.exception("Radarr catalog metadata unavailable")
        films = []

    series = []
    setting = arr._settings("sonarr")
    if setting:
        try:
            raw = arr._request("sonarr", setting, "series")
            series = raw if isinstance(raw, list) else []
        except Exception:
            log.exception("Sonarr catalog metadata unavailable")

    providers = {"radarr": bool(films), "sonarr": bool(series),
                 "tmdb": bool(metadata.token_status())}
    with _lock:
        _state["sources"] = providers

    # Resolve movies first, rather than inheriting the poster worker's TV-first priority.
    for (kind, library_id, key), (title, year) in sorted(
        titles.items(), key=lambda entry: entry[0][0] != "movies"
    ):
        try:
            if kind == "movies":
                matched = _matching_movie(title, year, films)
                incoming = _safe_metadata(matched)
                if not _complete(incoming):
                    # Existing movie detail resolver also reads local NFO sidecars,
                    # manual TMDB matches, and cached TMDB metadata.
                    incoming = _combine(incoming, _safe_metadata(
                        movies._details(library_id, key, snapshot=films, enrich=True, include_video_format=False)))
            else:
                matched = _matching_series(title, year, series)
                incoming = _safe_metadata(matched)
                if not _complete(incoming):
                    incoming = _combine(incoming, _safe_metadata(
                        tv.show_metadata(title, year, library_id, key)))
            changed = _persist(kind, library_id, key, incoming)
        except Exception:
            log.exception("Could not index metadata for %s %s", kind, key)
            changed = False
        with _lock:
            _state["processed"] += 1
            if changed:
                _state["updated"] += 1
                _state["revision"] += 1
    # Count cached coverage, not just updates in this particular pass.
    # This also distinguishes a completed no-change refresh from failure.
    with db() as conn:
        _table(conn)
        cached = {
            (row["kind"], row["library_id"], row["show_key"]): row["metadata_json"]
            for row in conn.execute(
                "SELECT kind,library_id,show_key,metadata_json FROM indexed_posters "
                "WHERE metadata_json IS NOT NULL"
            )
        }
    available = 0
    for identity in titles:
        try:
            info = _safe_metadata(json.loads(cached.get(identity) or "{}"))
            available += int(_has_metadata(info))
        except (TypeError, ValueError):
            pass
    with _lock:
        _state["available"] = available
        _state["missing"] = len(titles) - available
    return dict(_state)


def _worker():
    try:
        sync_once()
        with _lock:
            _state["error"] = ""
    except Exception:
        log.exception("Catalog metadata indexing failed")
        with _lock:
            _state["error"] = "Metadata indexing failed. Check the connected providers."
    finally:
        with _lock:
            _state["last_finished"] = time.time()
            _state["running"] = False


def start_refresh(force=False):
    try:
        signature = _library_signature()
    except Exception:
        log.exception("Could not inspect catalog indexing state")
        return False
    with _lock:
        if _state["running"]:
            return False
        changed = signature != _state["last_signature"]
        cooldown = (10 if _state["total"] == 0 else
                    MISSING_RETRY_SECONDS if _state["missing"] else RESCAN_SECONDS)
        if not force and not changed and time.time() - _state["last_finished"] < cooldown:
            return False
        _state["running"] = True
        _state["last_signature"] = signature
        _state["error"] = ""
    threading.Thread(target=_worker, daemon=True, name="catalog-metadata-sync").start()
    return True


def automatic_refresh_loop(stop):
    """Recover from provider outages and index new titles without user clicks."""
    if stop.wait(25):
        return
    while not stop.is_set():
        try:
            start_refresh()
        except Exception:
            log.exception("Automatic catalog metadata refresh failed")
        stop.wait(60)


@router.get("/status")
def status():
    with _lock:
        result = dict(_state)
    result["last_finished"] = int(result["last_finished"])
    return result


@router.post("/refresh")
def refresh():
    started = start_refresh(force=True)
    return {"started": started, **status()}
