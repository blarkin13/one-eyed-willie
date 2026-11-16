"""Shared playback preferences, persisted on the One-Eyed Willie server."""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from .library import db

router = APIRouter(prefix="/api/settings/playback")


class PlaybackPreferences(BaseModel):
    auto_play_next: bool = False
    tv_theme_music: bool = True
    movie_theme_music: bool = True
    theme_volume: int = Field(default=25, ge=0, le=100)
    theme_loop: bool = True
    theme_fade: bool = True


def _settings_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


@router.get("")
def get_preferences():
    defaults = PlaybackPreferences().model_dump()
    with db() as conn:
        _settings_table(conn)
        rows = conn.execute(
            "SELECT key,value FROM app_settings WHERE key IN "
            "('auto_play_next','tv_theme_music','movie_theme_music','theme_volume',"
            "'theme_loop','theme_fade')"
        ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    for key in defaults:
        if key not in values:
            continue
        if key == "theme_volume":
            try:
                defaults[key] = min(100, max(0, int(values[key])))
            except (ValueError, TypeError):
                pass
        else:
            defaults[key] = values[key] == "true"
    return defaults


@router.put("")
def update_preferences(preferences: PlaybackPreferences):
    values = preferences.model_dump()
    with db() as conn:
        _settings_table(conn)
        conn.executemany(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(key, str(value) if key == "theme_volume" else
              ("true" if value else "false"))
             for key, value in values.items()]
        )
        conn.commit()
    return values
