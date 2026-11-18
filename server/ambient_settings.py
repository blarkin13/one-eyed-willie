"""Server-wide optional ambient browsing effects.

A small setting stored in the existing SQLite app_settings table; never runs
during playback. Default Off so deployments do not surprise existing users.
"""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from .library import db

router = APIRouter(prefix="/api/settings/ambient", tags=["appearance"])


class AmbientPreferences(BaseModel):
    effect: Literal["off", "snow", "rain", "leaves", "fireflies"] = "off"
    intensity: int = Field(default=10, ge=10, le=100)
    speed: Literal["slow", "normal", "fast"] = "normal"
    layer: Literal["foreground", "background"] = "foreground"


def _table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings "
                 "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")


@router.get("")
def get_ambient():
    defaults = AmbientPreferences().model_dump()
    with db() as conn:
        _table(conn)
        rows = conn.execute(
            "SELECT key,value FROM app_settings WHERE key IN "
            "('ambient_effect','ambient_intensity','ambient_speed','ambient_layer')"
        ).fetchall()
    saved = {row["key"]: row["value"] for row in rows}
    proposal = {key: saved.get("ambient_" + key, value)
                for key, value in defaults.items()}
    try:
        return AmbientPreferences.model_validate(proposal).model_dump()
    except ValueError:
        # Be resilient to corrupt/obsolete settings; never crash browsing.
        return defaults


@router.put("")
def save_ambient(preferences: AmbientPreferences):
    values = preferences.model_dump()
    with db() as conn:
        _table(conn)
        conn.executemany(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [("ambient_" + key, str(value)) for key, value in values.items()]
        )
    return values
