"""Persist ordered, visible sidebar destinations without exposing arbitrary links."""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .library import db

router = APIRouter(prefix="/api/settings")
NAV = (
    ("home", "Home"),
    ("movies", "Movies"),
    ("tv", "TV Shows"),
    ("radarr", "Radarr"),
    ("sonarr", "Sonarr"),
    ("sabnzbd", "SABnzbd"),
    ("services", "Download services"),
)
ALWAYS_VISIBLE = {"home", "settings"}


class SidebarRequest(BaseModel):
    order: list[str] = Field(max_length=150)
    hidden: list[str] = Field(max_length=150)


def _settings_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _available(conn):
    entries = [{"id": key, "name": name, "kind": "system"} for key, name in NAV]
    for row in conn.execute("SELECT id,name,sidebar_hidden FROM libraries ORDER BY sort_order,id"):
        entries.append({"id": f'library:{row["id"]}', "name": row["name"], "kind": "library",
                        "sidebar_hidden": bool(row["sidebar_hidden"])})
    entries.append({"id": "settings", "name": "Settings", "kind": "system"})
    return entries


def _read(conn, key):
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    if row:
        try:
            result = json.loads(row["value"])
            return result if isinstance(result, list) else []
        except (TypeError, ValueError):
            pass
    return []


@router.get("/sidebar")
def get_sidebar():
    with db() as conn:
        _settings_table(conn)
        entries = _available(conn)
        by_id = {item["id"]: item for item in entries}
        saved = _read(conn, "sidebar_order")
        hidden = set(_read(conn, "sidebar_hidden"))
        hidden.update(item["id"] for item in entries if item.get("sidebar_hidden"))
        order = list(dict.fromkeys(key for key in saved if key in by_id))
        # New libraries and newly-added destinations are appended before Settings.
        index = order.index("settings") if "settings" in order else len(order)
        for entry in entries:
            if entry["id"] not in order and entry["id"] != "settings":
                order.insert(index, entry["id"])
                index += 1
        if "settings" in order:
            order.remove("settings")
        order.append("settings")
        return {"items": [
            {**by_id[key], "visible": key not in hidden or key in ALWAYS_VISIBLE}
            for key in order
        ], "order": order,
            "hidden": sorted(hidden - ALWAYS_VISIBLE)}


@router.put("/sidebar")
def update_sidebar(payload: SidebarRequest):
    with db() as conn:
        _settings_table(conn)
        entries = _available(conn)
        valid = {entry["id"] for entry in entries}
        if (len(set(payload.order)) != len(payload.order) or
            set(payload.order) != valid or
            payload.order[-1:] != ["settings"] or
            len(set(payload.hidden)) != len(payload.hidden) or
            not set(payload.hidden).issubset(valid) or
            set(payload.hidden) & ALWAYS_VISIBLE):
            raise HTTPException(422, "Invalid sidebar items, order or visibility")
        conn.execute("INSERT INTO app_settings(key,value) VALUES('sidebar_order',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (json.dumps(payload.order),))
        builtin_hidden = [key for key in payload.hidden if not key.startswith("library:")]
        conn.execute("INSERT INTO app_settings(key,value) VALUES('sidebar_hidden',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (json.dumps(builtin_hidden),))
        for entry in entries:
            if entry["kind"] == "library":
                conn.execute("UPDATE libraries SET sidebar_hidden=? WHERE id=?",
                             (int(entry["id"] in payload.hidden),
                              int(entry["id"].split(":")[1])))
    return get_sidebar()
