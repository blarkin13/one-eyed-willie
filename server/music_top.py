"""Top songs for an artist, like YouTube Music's, from open data.

ListenBrainz (MetaBrainz, CC0 listening statistics) ranks an artist's
recordings by real listens. The artist is identified by their MusicBrainz ID,
from the files' own tags or, failing that, a MusicBrainz name search. The
ranking is matched to the songs in the library, so Top songs only ever lists
what can be played. Lookups are cached for a month.
"""
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

import httpx
from fastapi import APIRouter, Query
from mutagen import File as AudioFile, MutagenError

from . import music
from .library import db
from .viewer import current as current_viewer

router = APIRouter(prefix="/api/music", tags=["music"])
LISTENBRAINZ = "https://api.listenbrainz.org/1/popularity/top-recordings-for-artist/{mbid}"
MUSICBRAINZ = "https://musicbrainz.org/ws/2/artist"
USER_AGENT = "YarrMedia/1.0 ( https://yarr.media )"
FOUND_SECONDS = 30 * 86400
MISSING_SECONDS = 3 * 86400
MBID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_lock = threading.Lock()


def normalize(title):
    """A song title for matching: no accents, case, punctuation or "(Remastered 2015)"-style extras."""
    text = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    text = re.sub(r"\s+-\s+.*(remaster|live|version|edit|mix|mono|stereo|demo).*$", " ", text)
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _setup(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS music_artist_top (
        artist_key TEXT PRIMARY KEY, mbid TEXT, titles TEXT, fetched_at REAL NOT NULL)""")


def _get(url, params=None):
    response = httpx.get(url, params=params, timeout=8.0,
                         headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def _mbid_from_tags(paths):
    for path in paths[:4]:
        try:
            audio = AudioFile(str(path), easy=True)
        except (OSError, ValueError, MutagenError):
            continue
        for key in ("musicbrainz_albumartistid", "musicbrainz_artistid"):
            value = (audio.get(key) if audio else None) or []
            for item in value:
                for part in str(item).replace(";", "/").split("/"):
                    if MBID.match(part.strip().lower()):
                        return part.strip().lower()
    return None


def _mbid_from_search(name):
    data = _get(MUSICBRAINZ, {"query": 'artist:"' + name.replace('"', "") + '"', "fmt": "json", "limit": "3"})
    for artist in data.get("artists") or []:
        if int(artist.get("score") or 0) >= 95 and normalize(artist.get("name")) == normalize(name):
            mbid = str(artist.get("id") or "")
            if MBID.match(mbid):
                return mbid
    return None


def _ranking(name, paths):
    """Normalized titles, most-listened first (cached)."""
    key = name.casefold()
    with db() as conn:
        _setup(conn)
        row = conn.execute("SELECT mbid,titles,fetched_at FROM music_artist_top WHERE artist_key=?", (key,)).fetchone()
    if row:
        titles = json.loads(row["titles"] or "[]")
        if time.time() - row["fetched_at"] < (FOUND_SECONDS if titles else MISSING_SECONDS):
            return titles
    with _lock:
        mbid, titles = None, []
        try:
            mbid = _mbid_from_tags(paths) or _mbid_from_search(name)
            if mbid:
                data = _get(LISTENBRAINZ.format(mbid=mbid))
                titles = [normalize(r.get("recording_name")) for r in data if isinstance(r, dict)][:200]
                titles = [t for t in titles if t]
        except (httpx.HTTPError, ValueError, TypeError):
            if row:                      # keep the old answer when the internet is away
                return json.loads(row["titles"] or "[]")
            return []                    # try again next time
        with db() as conn:
            _setup(conn)
            conn.execute("INSERT OR REPLACE INTO music_artist_top(artist_key,mbid,titles,fetched_at) VALUES(?,?,?,?)",
                         (key, mbid, json.dumps(titles), time.time()))
        return titles


@router.get("/artist-top")
def artist_top(name: str = Query(min_length=1, max_length=200), limit: int = Query(5, ge=1, le=20)):
    """The artist's most popular songs that are in the library (track ids, best first)."""
    who = current_viewer()
    rows = [r for r in music._files() if who.can_see(r["library_id"]) and
            str(r["artist"] or "").casefold() == name.casefold()]
    if not rows:
        return {"tracks": [], "source": None}
    by_title = {}
    for r in rows:
        by_title.setdefault(normalize(r["title"]), r["id"])
    ranking = _ranking(name, [Path(r["path"]) for r in rows])
    picked = []
    for title in ranking:
        track = by_title.get(title)
        if track is not None and track not in picked:
            picked.append(track)
            if len(picked) >= limit:
                break
    return {"tracks": picked, "source": "ListenBrainz" if picked else None}
