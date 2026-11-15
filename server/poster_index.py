"""Persistent background poster index and prepared grid-sized artwork.

Metadata providers are consulted only by the background poster worker, never
by the catalog or home endpoints. Existing detail pages remain authoritative.
"""
import logging
import os
import threading
import time

from .library import db

log = logging.getLogger(__name__)
LOCK = threading.Lock()
BATCH = 8
RETRY_SECONDS = 3600


def _table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS indexed_posters (
        kind TEXT NOT NULL, library_id INTEGER NOT NULL, show_key TEXT NOT NULL,
        poster_url TEXT, checked_at INTEGER NOT NULL,
        PRIMARY KEY(kind, library_id, show_key)
    )""")


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
        media = conn.execute("SELECT library_id,path FROM media ORDER BY library_id,path")
        found = {}
        for row in media:
            lib = libs.get(row["library_id"])
            if not lib:
                continue
            try:
                info = (episode_info(row["path"], lib["path"]) if lib["kind"] == "tv"
                        else movie_info(row["path"], lib["path"]))
            except (OSError, ValueError):
                continue
            identity = (lib["kind"], row["library_id"], info["key"])
            if identity not in found:
                found[identity] = (info["title"], info["year"])
    return found


def _resolve(kind, library_id, key, title, year):
    if kind == "tv":
        from .tv import show_metadata
        from .artwork import local_show_poster, register_remote
        local = local_show_poster(library_id, key)
        if local:
            return local
        meta = show_metadata(title, year, library_id, key)
        return register_remote(meta.get("poster_url")) if meta else None
    from .movies import _details, _snapshot
    try:
        detail = _details(library_id, key, snapshot=_snapshot(), enrich=False)
    except Exception:
        log.exception("Poster lookup failed for movie %s", key)
        return None
    return detail.get("poster_url")


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
                if identity not in cached or (
                    not cached[identity]["poster_url"]
                    and now - cached[identity]["checked_at"] >= RETRY_SECONDS)]
        processed = 0
        for (kind, library_id, key), (title, year) in todo[:limit]:
            try:
                url = _resolve(kind, library_id, key, title, year)
                if url:
                    _prepare(url)
                with db() as conn:
                    _table(conn)
                    conn.execute(
                        "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
                        "VALUES(?,?,?,?,?) ON CONFLICT(kind,library_id,show_key) DO UPDATE SET "
                        "poster_url=excluded.poster_url,checked_at=excluded.checked_at",
                        (kind, library_id, key, url, int(time.time()))
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
        stop.wait(25 if completed else 180)
