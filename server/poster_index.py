"""Persistent background poster index and prepared grid-sized artwork.

Metadata providers are consulted only by the background poster worker, never
by the catalog or home endpoints. Existing detail pages remain authoritative.
"""
import logging
import json
import math
import os
import threading
import time

from .library import db

log = logging.getLogger(__name__)
LOCK = threading.Lock()
BATCH = 24
RETRY_SECONDS = 3600
# While titles are still waiting to be indexed, come back quickly; once the
# library is fully indexed fall back to a slow idle poll. The previous 12 titles
# per 15s left a few-thousand-title library partly unindexed for over an hour,
# and every unindexed poster is resolved on demand when it scrolls into view.
BUSY_WAIT_SECONDS = 6
IDLE_WAIT_SECONDS = 180


def _table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS indexed_posters (
        kind TEXT NOT NULL, library_id INTEGER NOT NULL, show_key TEXT NOT NULL,
        poster_url TEXT, checked_at INTEGER NOT NULL,
        PRIMARY KEY(kind, library_id, show_key)
    )""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(indexed_posters)")}
    if "metadata_json" not in columns:
        conn.execute("ALTER TABLE indexed_posters ADD COLUMN metadata_json TEXT")


def indexed_urls(entries):
    """Look up all poster references in one SQLite read, never external APIs."""
    if not entries:
        return {}
    with db() as conn:
        _table(conn)
        ids = sorted({int(item["library_id"]) for item in entries})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            "SELECT kind,library_id,show_key,poster_url FROM indexed_posters "
            f"WHERE library_id IN ({placeholders}) AND poster_url IS NOT NULL", ids
        )
        return {(r["kind"], r["library_id"], r["show_key"]): r["poster_url"] for r in rows}


def attach_posters(items):
    from .artwork import thumbnail_url
    posters = indexed_urls(items)
    for item in items:
        item["poster_url"] = thumbnail_url(posters.get((item["kind"], item["library_id"], item["key"])))
    return items


def remember(kind, library_id, key, poster_url):
    """Save poster data already resolved by a detail page for instant Home loading."""
    if not isinstance(poster_url, str) or not poster_url.startswith("/api/artwork/"):
        return
    from .artwork import HEX
    if not HEX.fullmatch(poster_url.rsplit("/", 1)[-1]):
        return
    with db() as conn:
        _table(conn)
        conn.execute(
            "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(kind,library_id,show_key) DO UPDATE SET "
            "poster_url=excluded.poster_url,checked_at=excluded.checked_at",
            (kind, library_id, key, poster_url, int(time.time()))
        )


def invalidate(kind, library_id, key):
    with db() as conn:
        _table(conn)
        conn.execute("DELETE FROM indexed_posters WHERE kind=? AND library_id=? AND show_key=?",
                     (kind, library_id, key))


def _collect():
    """Collect unique library titles from local indexed files with no provider calls."""
    from .catalog import episode_info, movie_info
    with db() as conn:
        libs = {r["id"]: r for r in conn.execute("SELECT id,kind,path FROM libraries")}
        # Prefetch TV first, newest additions first, so Home posters appear
        # without waiting for every movie in the collection.
        media = conn.execute("""
            SELECT m.library_id,m.path,m.source_root FROM media m
            JOIN libraries l ON l.id=m.library_id
            WHERE l.kind IN ('movies','tv')
            ORDER BY CASE WHEN l.kind='tv' THEN 0 ELSE 1 END,
                     m.added_at DESC,m.id DESC
        """)
        found = {}
        for row in media:
            lib = libs.get(row["library_id"])
            if not lib:
                continue
            try:
                info = (episode_info(row["path"], row["source_root"] or lib["path"]) if lib["kind"] == "tv"
                        else movie_info(row["path"], row["source_root"] or lib["path"]))
            except (OSError, ValueError):
                continue
            identity = (lib["kind"], row["library_id"], info["key"])
            if identity not in found:
                found[identity] = (info["title"], info["year"])
    return found


def _safe_metadata(meta):
    """Small sortable metadata fields; never persist provider credentials or paths."""
    meta = meta if isinstance(meta, dict) else {}
    genres = meta.get("genres")
    genres = [str(x).strip()[:60] for x in genres[:20]
              if isinstance(x, str) and x.strip()] if isinstance(genres, list) else []
    rating = meta.get("rating")
    if isinstance(rating, dict):
        rating = rating.get("value", rating.get("average"))
    if rating is None:
        rating = meta.get("tmdb_rating")
    if rating is None:
        ratings = meta.get("ratings") or {}
        for source in ("tmdb", "imdb"):
            value = ratings.get(source) if isinstance(ratings, dict) else None
            if isinstance(value, dict):
                rating = value.get("value")
                if rating is not None:
                    break
    try:
        rating = float(rating)
        if not math.isfinite(rating) or not 0 <= rating <= 10:
            rating = None
    except (ValueError, TypeError):
        rating = None
    runtime = meta.get("runtime")
    if not runtime:
        runtime = meta.get("episode_run_time")
        if isinstance(runtime, list):
            runtime = next((v for v in runtime if isinstance(v, int) and v > 0), None)
    try:
        runtime = int(runtime)
        if runtime <= 0 or runtime > 1000:
            runtime = None
    except (TypeError, ValueError):
        runtime = None
    return {"genres": genres, "rating": rating, "runtime": runtime}


def _resolve(kind, library_id, key, title, year):
    if kind == "tv":
        from .tv import show_metadata
        from .artwork import local_show_poster, register_remote
        meta = show_metadata(title, year, library_id, key) or {}
        local = local_show_poster(library_id, key)
        return local or register_remote(meta.get("poster_url")), _safe_metadata(meta)
    from .movies import _details, _snapshot
    try:
        detail = _details(library_id, key, snapshot=_snapshot(), enrich=True)
    except Exception:
        log.exception("Poster/metadata lookup failed for movie %s", key)
        return None, {}
    return detail.get("poster_url"), _safe_metadata(detail)


def _prepare(url):
    """Materialize and resize artwork before the UI needs it."""
    from .artwork import warm_thumbnail
    if url and url.startswith("/api/artwork/"):
        try:
            warm_thumbnail(url.rsplit("/", 1)[-1])
        except Exception:
            log.exception("Failed preparing artwork thumbnail")


def prepare_batch(limit=BATCH):
    if not LOCK.acquire(blocking=False):
        return 0
    try:
        all_titles = _collect()
        now = int(time.time())
        with db() as conn:
            _table(conn)
            cached = {
                (r["kind"], r["library_id"], r["show_key"]): dict(r)
                for r in conn.execute("SELECT * FROM indexed_posters")
            }
        # Missing images retry hourly; confirmed posters are kept until an
        # explicit metadata match changes or their media is removed.
        todo = [(identity, info) for identity, info in all_titles.items()
                if identity not in cached or cached[identity].get("metadata_json") is None or (
                    not cached[identity]["poster_url"]
                    and now - cached[identity]["checked_at"] >= RETRY_SECONDS)]
        # Keep TV first even for indexes populated before the priority change.
        todo.sort(key=lambda task: task[0][0] != "tv")
        processed = 0
        for (kind, library_id, key), (title, year) in todo[:limit]:
            try:
                resolved = _resolve(kind, library_id, key, title, year)
                url, metadata = resolved if isinstance(resolved, tuple) else (resolved, {})
                if url:
                    _prepare(url)
                # Do not replace useful catalog metadata with an empty poster
                # lookup result (e.g. when an external provider is unavailable).
                incoming = _safe_metadata(metadata)
                previous = cached.get((kind, library_id, key)) or {}
                try:
                    old_metadata = _safe_metadata(json.loads(previous.get("metadata_json") or "{}"))
                except (ValueError, TypeError):
                    old_metadata = {}
                incoming = {
                    "genres": incoming.get("genres") or old_metadata.get("genres") or [],
                    "runtime": incoming.get("runtime") or old_metadata.get("runtime"),
                    "rating": incoming["rating"] if incoming.get("rating") is not None
                              else old_metadata.get("rating"),
                }
                with db() as conn:
                    _table(conn)
                    # The metadata synchronizer may have updated this title
                    # after the batch snapshot. Merge the current DB row.
                    live = conn.execute(
                        "SELECT metadata_json FROM indexed_posters "
                        "WHERE kind=? AND library_id=? AND show_key=?",
                        (kind, library_id, key),
                    ).fetchone()
                    if live:
                        try:
                            existing = _safe_metadata(json.loads(live["metadata_json"] or "{}"))
                        except (ValueError, TypeError):
                            existing = {}
                        incoming = {
                            "genres": incoming["genres"] or existing.get("genres") or [],
                            "runtime": incoming["runtime"] or existing.get("runtime"),
                            "rating": incoming["rating"] if incoming["rating"] is not None
                                      else existing.get("rating"),
                        }
                    conn.execute(
                        "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at,metadata_json) "
                        "VALUES(?,?,?,?,?,?) ON CONFLICT(kind,library_id,show_key) DO UPDATE SET "
                        "poster_url=COALESCE(excluded.poster_url,indexed_posters.poster_url),"
                        "checked_at=excluded.checked_at,metadata_json=excluded.metadata_json",
                        (kind, library_id, key, url, int(time.time()),
                         json.dumps(incoming))
                    )
                processed += 1
            except Exception:
                log.exception("Background poster preparation failed for %s", key)
        # Remove indexed title references for deleted catalog groups; do not
        # delete image files, which may be shared across shows.
        if not todo:
            with db() as conn:
                _table(conn)
                for identity in set(cached) - set(all_titles):
                    conn.execute("DELETE FROM indexed_posters WHERE kind=? AND library_id=? AND show_key=?",
                                 identity)
        return processed
    finally:
        LOCK.release()


def poster_loop(stop):
    # Start after initial library scanning. Subsequent batches are deliberately
    # limited to avoid slowing down streams on the NUC.
    if stop.wait(30):
        return
    while not stop.is_set():
        try:
            completed = prepare_batch()
        except Exception:
            log.exception("Background poster indexing failed")
            completed = 0
        stop.wait(BUSY_WAIT_SECONDS if completed else IDLE_WAIT_SECONDS)
