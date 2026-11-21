"""Online lyrics (LRCLIB): an opt-in integration the server owner turns on.

When enabled, songs without lyrics in their own files (sidecar .lrc or tags)
are looked up on LRCLIB (https://lrclib.net), a free community lyrics
database. Only the song's artist, title, album and length are sent. Results,
including "not found", are cached per file so each song is asked once.
"""
import json
import time

from urllib.parse import urlparse

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from .library import db

router = APIRouter(prefix="/api/lyrics-online", tags=["lyrics"])
DEFAULT_SERVER = "https://lrclib.net"
USER_AGENT = "Yarr Media (https://yarr.media)"
MISS_RETRY_SECONDS = 14 * 86400   # ask again for songs LRCLIB didn't have, after two weeks
TIMEOUT = 6.0


class OnlineLyricsSettings(BaseModel):
    enabled: bool = False
    # Your own LRCLIB (it's open source) or the public one.
    server: str = Field(DEFAULT_SERVER, max_length=200)

    @field_validator("server")
    @classmethod
    def _server(cls, value):
        value = (value or "").strip().rstrip("/") or DEFAULT_SERVER
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment \
                or parsed.username or parsed.password:
            raise ValueError("Enter an address like https://lrclib.net or http://192.168.1.20:3300")
        return value


def _setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS lyrics_online_cache (
        media_id INTEGER PRIMARY KEY, mtime_ns INTEGER, found INTEGER NOT NULL,
        body TEXT, fetched_at REAL NOT NULL)""")


def _saved():
    with db() as conn:
        _setup(conn)
        rows = conn.execute("SELECT key,value FROM app_settings WHERE key IN "
                            "('lyrics_online_enabled','lyrics_online_server')").fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return values.get("lyrics_online_enabled") == "true", values.get("lyrics_online_server") or DEFAULT_SERVER


def enabled():
    return _saved()[0]


@router.get("/settings")
def get_settings():
    on, server = _saved()
    return {"enabled": on, "server": server, "default_server": DEFAULT_SERVER, "provider": "LRCLIB"}


@router.put("/settings")
def save_settings(settings: OnlineLyricsSettings):
    old_server = _saved()[1]
    with db() as conn:
        _setup(conn)
        conn.executemany("INSERT INTO app_settings(key,value) VALUES(?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         [("lyrics_online_enabled", "true" if settings.enabled else "false"),
                          ("lyrics_online_server", settings.server)])
        if settings.server != old_server:
            # A different lyrics server may know songs the old one didn't.
            conn.execute("DELETE FROM lyrics_online_cache WHERE found=0")
    return get_settings()


def _ask_lrclib(server, artist, title, album, duration):
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = str(round(duration))
    try:
        response = httpx.get(server + "/api/get", params=params, timeout=TIMEOUT,
                             headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    except httpx.HTTPError:
        return None, False          # network trouble: don't remember a miss
    if response.status_code == 404:
        return None, True
    if response.status_code != 200:
        return None, False
    try:
        data = response.json()
    except ValueError:
        return None, False
    if not isinstance(data, dict):
        return None, True
    if data.get("instrumental"):
        return {"instrumental": True}, True
    synced = data.get("syncedLyrics") if isinstance(data.get("syncedLyrics"), str) else ""
    plain = data.get("plainLyrics") if isinstance(data.get("plainLyrics"), str) else ""
    text = synced or plain
    return ({"text": text[:64 * 1024]} if text.strip() else None), True


def lookup(media_id, mtime_ns, artist, title, album, duration):
    """Cached LRCLIB result for one file: {"text": ...}, {"instrumental": True} or None."""
    on, server = _saved()
    if not on or not artist or not title:
        return None
    with db() as conn:
        _setup(conn)
        row = conn.execute("SELECT mtime_ns,found,body,fetched_at FROM lyrics_online_cache WHERE media_id=?",
                           (media_id,)).fetchone()
    if row and row["mtime_ns"] == mtime_ns:
        if row["found"]:
            return json.loads(row["body"])
        if time.time() - row["fetched_at"] < MISS_RETRY_SECONDS:
            return None
    result, definite = _ask_lrclib(server, artist, title, album, duration)
    if definite:
        with db() as conn:
            _setup(conn)
            conn.execute("INSERT OR REPLACE INTO lyrics_online_cache(media_id,mtime_ns,found,body,fetched_at) "
                         "VALUES(?,?,?,?,?)", (media_id, mtime_ns, 1 if result else 0,
                                                json.dumps(result) if result else None, time.time()))
    return result
