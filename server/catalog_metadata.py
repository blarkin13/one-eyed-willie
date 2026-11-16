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
}
RESCAN_SECONDS = 15 * 60


def _has_metadata(info):
    return bool(info.get("genres")) or info.get("runtime") is not None or info.get("rating") is not None


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
                if not _has_metadata(incoming):
                    # Existing movie detail resolver also reads local NFO sidecars,
                    # manual TMDB matches, and cached TMDB metadata.
                    incoming = _safe_metadata(
                        movies._details(library_id, key, snapshot=films, enrich=True))
            else:
                matched = _matching_series(title, year, series)
                incoming = _safe_metadata(matched)
                if not _has_metadata(incoming):
                    incoming = _safe_metadata(tv.show_metadata(title, year, library_id, key))
            changed = _persist(kind, library_id, key, incoming)
        except Exception:
            log.exception("Could not index metadata for %s %s", kind, key)
            changed = False
        with _lock:
            _state["processed"] += 1
            if changed:
                _state["updated"] += 1
                _state["revision"] += 1
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
    with _lock:
        if _state["running"]:
            return False
        cooldown = 10 if _state["total"] == 0 else RESCAN_SECONDS
        if not force and time.time() - _state["last_finished"] < cooldown:
            return False
        _state["running"] = True
        _state["error"] = ""
    threading.Thread(target=_worker, daemon=True, name="catalog-metadata-sync").start()
    return True


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
