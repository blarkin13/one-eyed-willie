"""What a kid profile may watch: a highest rating, whether unrated titles show,
which libraries, and per-title exceptions both ways.

Movie (MPAA) and TV (US TV Parental Guidelines) ratings share one scale, so a
single "Up to" choice covers both:

    0 TV-Y  ·  1 TV-Y7  ·  2 G / TV-G  ·  3 PG / TV-PG  ·  4 PG-13 / TV-14  ·  5 R / TV-MA  ·  6 NC-17
"""
from dataclasses import dataclass, field
import re

LEVELS = {
    "TV-Y": 0, "TV-Y7": 1, "TV-Y7-FV": 1, "G": 2, "TV-G": 2, "PG": 3, "TV-PG": 3,
    "PG-13": 4, "TV-14": 4, "R": 5, "TV-MA": 5, "NC-17": 6, "X": 6,
}
CHOICES = [  # (level, label) for the "Up to" setting
    (0, "TV-Y (little kids)"), (1, "TV-Y7"), (2, "G / TV-G"), (3, "PG / TV-PG"),
    (4, "PG-13 / TV-14"), (5, "R / TV-MA"),
]
_UNRATED = {"", "NR", "UR", "NOT RATED", "UNRATED", "N/A", "NONE"}


def normalize(rating):
    """A rating string as used on the scale (e.g. 'Rated PG-13' -> 'PG-13'), or ''."""
    text = re.sub(r"\s+", " ", str(rating or "")).strip().upper()
    text = re.sub(r"^(RATED|US:|US )\s*", "", text).strip()
    text = text.replace("TV Y", "TV-Y").replace("TVY", "TV-Y").replace("TV14", "TV-14").replace("TVMA", "TV-MA")
    text = text.replace("TVPG", "TV-PG").replace("TVG", "TV-G").replace("PG13", "PG-13").replace("NC17", "NC-17")
    return "" if text in _UNRATED else text if text in LEVELS else ""


def level(rating):
    """Where a rating sits on the shared scale, or None when unrated/unknown."""
    return LEVELS.get(normalize(rating))


def title_id(kind, library_id, key):
    """How exceptions name a title: 'movies:3:the matrix (1999)'."""
    return f"{kind}:{int(library_id)}:{key}"


@dataclass(frozen=True)
class KidRules:
    max_level: int = 3                      # PG / TV-PG
    allow_unrated: bool = False
    libraries: frozenset | None = None      # None = every library
    allow: frozenset = field(default_factory=frozenset)   # title ids always allowed
    block: frozenset = field(default_factory=frozenset)   # title ids never allowed

    @classmethod
    def from_json(cls, data):
        data = data if isinstance(data, dict) else {}
        try:
            top = min(6, max(0, int(data.get("max_level", 3))))
        except (TypeError, ValueError):
            top = 3
        libs = data.get("libraries")
        libs = None if libs is None else frozenset(
            n for n in libs if isinstance(n, int) and not isinstance(n, bool) and n > 0)
        ids = lambda name: frozenset(str(x)[:300] for x in (data.get(name) or [])[:2000] if isinstance(x, str))
        return cls(max_level=top, allow_unrated=bool(data.get("allow_unrated", False)),
                   libraries=libs, allow=ids("allow"), block=ids("block"))

    def to_json(self):
        return {"max_level": self.max_level, "allow_unrated": self.allow_unrated,
                "libraries": None if self.libraries is None else sorted(self.libraries),
                "allow": sorted(self.allow), "block": sorted(self.block)}

    def allows(self, kind, library_id, key, rating):
        """May the kid see this title? Exceptions win over the rating."""
        if self.libraries is not None and library_id not in self.libraries:
            return False
        if kind == "music":
            return True
        ident = title_id(kind, library_id, key)
        if ident in self.block:
            return False
        if ident in self.allow:
            return True
        where = level(rating)
        if where is None:
            return self.allow_unrated
        return where <= self.max_level


# ---- Ratings of the titles in the libraries ---------------------------------
# Filled by the catalog metadata sync (server/catalog_metadata.py) from Radarr,
# Sonarr, NFO files and TMDB. Kept apart from the poster metadata.

import threading as _threading
import time as _time

_cache = {"at": 0.0, "path": None, "data": None}
_cache_lock = _threading.Lock()
_CACHE_SECONDS = 120


def _table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS title_ratings(
        kind TEXT NOT NULL, library_id INTEGER NOT NULL, show_key TEXT NOT NULL,
        rating TEXT NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(kind, library_id, show_key))""")


def store(kind, library_id, key, rating):
    """Remembers a title's rating (an unknown rating never replaces a known one)."""
    from .library import db
    value = normalize(rating)
    if not value:
        return False
    with db() as conn:
        _table(conn)
        row = conn.execute("SELECT rating FROM title_ratings WHERE kind=? AND library_id=? AND show_key=?",
                           (kind, library_id, key)).fetchone()
        if row and row["rating"] == value:
            return False
        conn.execute("INSERT INTO title_ratings(kind,library_id,show_key,rating,updated_at) VALUES(?,?,?,?,?) "
                     "ON CONFLICT(kind,library_id,show_key) DO UPDATE SET rating=excluded.rating, updated_at=excluded.updated_at",
                     (kind, library_id, key, value, _time.time()))
    with _cache_lock:
        _cache["data"] = None
    return True


def ratings():
    """{(kind, library_id, key): rating} for every rated title (cached briefly)."""
    from . import library
    with _cache_lock:
        if (_cache["data"] is not None and _cache["path"] == library.DB_PATH
                and _time.time() - _cache["at"] < _CACHE_SECONDS):
            return _cache["data"]
    with library.db() as conn:
        _table(conn)
        data = {(r["kind"], r["library_id"], r["show_key"]): r["rating"]
                for r in conn.execute("SELECT kind,library_id,show_key,rating FROM title_ratings")}
    with _cache_lock:
        _cache.update(at=_time.time(), path=library.DB_PATH, data=data)
    return data


def rating_of(kind, library_id, key):
    return ratings().get((kind, library_id, key), "")


def title_of_media(media_id):
    """(kind, library_id, title key) for a media id, or None."""
    from .library import db
    from .catalog import movie_info, episode_info
    with db() as conn:
        row = conn.execute("SELECT m.path, m.source_root, m.library_id, l.kind, l.path AS root FROM media m "
                           "JOIN libraries l ON l.id=m.library_id WHERE m.id=?", (media_id,)).fetchone()
    if row is None:
        return None
    if row["kind"] == "music":
        return ("music", row["library_id"], "")
    try:
        parse = movie_info if row["kind"] == "movies" else episode_info
        return (row["kind"], row["library_id"], parse(row["path"], row["source_root"] or row["root"])["key"])
    except (ValueError, OSError):
        return None


def viewer_allows(viewer, kind, library_id, key):
    """May this viewer see this title? (library limits for everyone, ratings for kids)."""
    if not viewer.can_see(library_id):
        return False
    rules = viewer.rules
    if rules is None:
        return True
    return rules.allows(kind, library_id, key, rating_of(kind, library_id, key))


def viewer_allows_media(viewer, media_id):
    if viewer.rules is None:
        from .barnacle_access import media_library
        return viewer.can_see(media_library(media_id))
    title = title_of_media(media_id)
    return title is not None and viewer_allows(viewer, *title)
