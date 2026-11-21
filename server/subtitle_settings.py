"""Shared browser-player subtitle appearance preferences.

These preferences apply only to browser playback; native Google TV uses
per-TV local caption settings exposed in its Playback Settings page.
"""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from .library import db
from . import personal_settings

router = APIRouter(prefix="/api/settings/subtitle-appearance", tags=["appearance"])


class SubtitleAppearance(BaseModel):
    background: Literal["none", "25", "50", "75", "100"] = "none"
    size: Literal["small", "normal", "large"] = "normal"
    color: Literal["white", "yellow"] = "white"
    outline: bool = True


@router.get("")
def get_subtitle_appearance():
    values = SubtitleAppearance().model_dump()
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings "
                     "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        saved = personal_settings.read(
            conn, ["subtitle_background", "subtitle_size", "subtitle_color", "subtitle_outline"])
    for key in values:
        value = saved.get("subtitle_" + key)
        if value is None:
            continue
        values[key] = (value == "true") if key == "outline" else value
    try:
        return SubtitleAppearance.model_validate(values).model_dump()
    except ValueError:
        return SubtitleAppearance().model_dump()


@router.put("")
def save_subtitle_appearance(settings: SubtitleAppearance):
    values = settings.model_dump()
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings "
                     "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(personal_settings.key("subtitle_" + key), ("true" if value else "false") if isinstance(value, bool)
              else value) for key, value in values.items()]
        )
    return values
