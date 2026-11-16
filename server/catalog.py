"""Background scanning and filename-based movie / series grouping."""
import os
import re
import time
import logging
import json
import threading
from pathlib import Path
from collections import defaultdict
from .library import db, scan_library, scan_lock, safe_folder

log = logging.getLogger(__name__)
INTERVAL = max(60, int(os.environ.get("SCAN_INTERVAL_SECONDS", "300")))
EPISODE = re.compile(r"(?i)(?:^|[ ._-])S(\d{1,2})[ ._-]*E(\d{1,3})(?:[ ._-]|$)")
YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


def pretty(raw):
    raw = re.sub(r"[._]+", " ", raw)
    raw = re.sub(r"(?i)\b(2160p|1080p|720p|480p|web[ -]?dl|bluray|brrip|x264|x265|hevc|h264|aac|dts|remux)\b.*$", "", raw)
    return re.sub(r"\s+", " ", raw).strip(" -()[]{}") or "Unknown"


def movie_info(path, root):
    filename = Path(path).stem
    folder = Path(path).parent
    # Prefer the containing folder name when files have generic names.
    source = folder.name if folder != Path(root) else filename
    match = YEAR.search(source) or YEAR.search(filename)
    title = pretty(source[:match.start()] if match and match.group() in source else source)
    year = int(match.group()) if match else None
    return {"key": f"{title.casefold()}:{year or ''}", "title": title, "year": year}


def episode_info(path, root):
    p = Path(path)
    match = EPISODE.search(p.stem)
    relative = p.relative_to(root)
    if len(relative.parts) > 1:
        show_name = relative.parts[0]
    elif match:
        show_name = p.stem[:match.start()]
    else:
        show_name = p.stem
    yearmatch = YEAR.search(show_name)
    year = int(yearmatch.group()) if yearmatch else None
    title = pretty(show_name[:yearmatch.start()] if yearmatch else show_name)
    return {"key": f"{title.casefold()}:{year or ''}", "title": title,
            "year": year, "season": int(match.group(1)) if match else None,
            "episode": int(match.group(2)) if match else None}


def title_sort_key(title):
    """Sort by the significant title, leaving the displayed title unchanged."""
    value = re.sub(r"^(?:the|an|a)\s+", "", str(title or "").strip(), flags=re.IGNORECASE)
    return value.casefold()


def _indexed_metadata(conn, library_ids):
    """Cached metadata only: no provider or disk requests while browsing."""
    if not library_ids:
        return {}
    from .poster_index import _table
    _table(conn)
    placeholders = ",".join("?" for _ in library_ids)
    metadata = {}
    for row in conn.execute(
        "SELECT kind,library_id,show_key,metadata_json FROM indexed_posters "
        f"WHERE library_id IN ({placeholders}) AND metadata_json IS NOT NULL", library_ids
    ):
        try:
            value = json.loads(row["metadata_json"])
            if isinstance(value, dict):
                metadata[(row["kind"], row["library_id"], row["show_key"])] = value
        except (TypeError, ValueError):
            continue
    return metadata


def catalog(kind=None, search="", limit=60, offset=0, sort="title", library_id=None, genre=""):
    with db() as conn:
        libs = conn.execute("SELECT id,kind,path FROM libraries").fetchall()
        applicable = [lib for lib in libs if
                      (not kind or lib["kind"] == kind) and
                      (library_id is None or lib["id"] == library_id)]
        cached_metadata = _indexed_metadata(conn, [lib["id"] for lib in applicable])
        groups = {}
        completed_ids = {row["media_id"] for row in conn.execute(
            "SELECT media_id FROM playback_progress WHERE completed=1"
        )}
        in_progress_ids = {row["media_id"] for row in conn.execute(
            "SELECT media_id FROM playback_progress WHERE completed=0 AND position_seconds>=30"
        )}
        for lib in applicable:
            rows = conn.execute("SELECT id,path,size,added_at,mtime_ns FROM media WHERE library_id=? ORDER BY path", (lib["id"],)).fetchall()
            for row in rows:
                try:
                    parsed = movie_info(row["path"], lib["path"]) if lib["kind"] == "movies" else episode_info(row["path"], lib["path"])
                except (ValueError, OSError):
                    continue
                if search and search.casefold() not in parsed["title"].casefold():
                    continue
                key = (lib["kind"], lib["id"], parsed["key"])
                if key not in groups:
                    groups[key] = {"kind": lib["kind"], "library_id": lib["id"],
                                   "key": parsed["key"], "title": parsed["title"],
                                   "year": parsed["year"], "files": 0, "seasons": set(),
                                   "added_at": row["added_at"],
                                   "recent_mtime": row["mtime_ns"],
                                   "recent_id": row["id"],
                                   "media_id": row["id"],
                                   "watched_files": 0, "in_progress_files": 0,
                                   "episodes": []}
                g = groups[key]
                g["files"] += 1
                if row["id"] in completed_ids:
                    g["watched_files"] += 1
                if row["id"] in in_progress_ids:
                    g["in_progress_files"] += 1
                if (row["added_at"] or "", row["mtime_ns"], row["id"]) > (
                    g["added_at"] or "", g["recent_mtime"], g["recent_id"]
                ):
                    g["added_at"] = row["added_at"]
                    g["recent_mtime"] = row["mtime_ns"]
                    g["recent_id"] = row["id"]
                    g["media_id"] = row["id"]
                if lib["kind"] == "tv":
                    if parsed["season"] is not None:
                        g["seasons"].add(parsed["season"])
                    g["episodes"].append({"id": row["id"], "season": parsed["season"],
                                          "episode": parsed["episode"], "filename": Path(row["path"]).name,
                                          "watched": row["id"] in completed_ids})
        results = []
        for group in groups.values():
            group["watched"] = group["files"] > 0 and group["watched_files"] == group["files"]
            group["partially_watched"] = group["watched_files"] > 0 or group["in_progress_files"] > 0
            group["seasons"] = sorted(group["seasons"])
            group["episodes"].sort(key=lambda e: (e["season"] if e["season"] is not None else 999,
                                                 e["episode"] if e["episode"] is not None else 999))
            results.append(group)
        available_genres = set()
        for group in results:
            metadata = cached_metadata.get((group["kind"], group["library_id"], group["key"]), {})
            raw_genres = metadata.get("genres") or []
            group["genres"] = [g for g in raw_genres if isinstance(g, str)]
            group["runtime"] = metadata.get("runtime")
            group["rating"] = metadata.get("rating")
            available_genres.update(group["genres"])
        genres = sorted(available_genres, key=str.casefold)
        if genre:
            results = [g for g in results if genre.casefold() in
                       {name.casefold() for name in g["genres"]}]
        if sort in ("recent", "added"):
            results.sort(key=lambda g: (g["added_at"] or "", g["recent_mtime"],
                                        g["recent_id"]), reverse=True)
        elif sort == "length":
            results.sort(key=lambda g: (g["runtime"] is None,
                                        -(g["runtime"] or 0), title_sort_key(g["title"])))
        elif sort == "rating":
            results.sort(key=lambda g: (g["rating"] is None,
                                        -(g["rating"] or 0), title_sort_key(g["title"])))
        elif sort == "year":
            results.sort(key=lambda g: (g["year"] or 0, title_sort_key(g["title"])), reverse=True)
        else:
            results.sort(key=lambda g: (title_sort_key(g["title"]),
                                        g["year"] or 0, g["title"].casefold()))
        from .poster_index import attach_posters
        page = results[offset:offset + limit]
        attach_posters(page)
        for item in page:
            item.pop("recent_mtime", None)
            item.pop("recent_id", None)
        return {"total": len(results), "items": page, "genres": genres}


def periodic_scan(stop):
    # Give the server time to start; scan in the background.
    if stop.wait(15):
        return
    while not stop.is_set():
        try:
            with db() as conn:
                libraries = [row["id"] for row in conn.execute("SELECT id FROM libraries").fetchall()]
            for library_id in libraries:
                if stop.is_set():
                    break
                # scan_library manages its own lock, so skip if a user scan is active.
                if scan_lock.locked():
                    continue
                try:
                    result = scan_library(library_id)
                    log.info("Automatic scan library=%s files=%s errors=%s",
                             library_id, result["found"], result["errors"])
                except Exception:
                    log.exception("Automatic library scan failed: %s", library_id)
        except Exception:
            log.exception("Automatic library scan scheduler failed")
        stop.wait(INTERVAL)


def start_background_scans():
    stop = threading.Event()
    thread = threading.Thread(target=periodic_scan, args=(stop,), daemon=True, name="library-scanner")
    thread.start()
    return stop, thread
