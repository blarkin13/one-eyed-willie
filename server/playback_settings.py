"""Shared playback preferences, persisted on the One-Eyed Willie server."""
from fastapi import APIRouter
from pydantic import BaseModel
from .library import db

router = APIRouter(prefix="/api/settings/playback")

class PlaybackPreferences(BaseModel):
    auto_play_next: bool

def _settings_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

@router.get("")
def get_preferences():
    with db() as conn:
        _settings_table(conn)
        row = conn.execute("SELECT value FROM app_settings WHERE key='auto_play_next'").fetchone()
    return {"auto_play_next": row is not None and row["value"] == "true"}

@router.put("")
def update_preferences(preferences: PlaybackPreferences):
    with db() as conn:
        _settings_table(conn)
        conn.execute("INSERT INTO app_settings(key,value) VALUES('auto_play_next',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     ("true" if preferences.auto_play_next else "false",))
        conn.commit()
    return {"auto_play_next": preferences.auto_play_next}
