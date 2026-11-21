"""Persist ordered, visible sidebar destinations without exposing arbitrary links."""
import json
import io
import time
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Literal
from .library import db
from . import personal_settings

router = APIRouter(prefix="/api/settings")
NAV = (
    ("home", "Home"),
    ("movies", "Movies"),
    ("tv", "TV Shows"),
    ("music", "Music"),
    ("connections", "Integrations"),
)
ALWAYS_VISIBLE = {"home", "settings"}
ICON_NAMES = ("home", "movies", "tv", "sabnzbd", "settings")

# Shared TV focus appearance: one setting for all TV clients, editable on web.
DEFAULT_SELECTION_COLOR = "#A61E1E"
SelectionColor = Literal["#A61E1E", "#8B5CF6", "#3B82F6", "#14B8A6", "#22C55E",
                         "#F59E0B", "#EC4899", "#EF4444", "#FFFFFF"]


class TvAppearanceRequest(BaseModel):
    selection_color: SelectionColor = DEFAULT_SELECTION_COLOR


@router.get("/tv-appearance")
def get_tv_appearance():
    with db() as conn:
        _settings_table(conn)
        selected = personal_settings.read(conn, ["tv_selection_color"]).get(
            "tv_selection_color", DEFAULT_SELECTION_COLOR)
    if selected not in SelectionColor.__args__:
        selected = DEFAULT_SELECTION_COLOR
    return {"selection_color": selected}


@router.put("/tv-appearance")
def save_tv_appearance(preferences: TvAppearanceRequest):
    with db() as conn:
        _settings_table(conn)
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (personal_settings.key("tv_selection_color"), preferences.selection_color),
        )
    return preferences.model_dump()



class SidebarRequest(BaseModel):
    order: list[str] = Field(max_length=150)
    hidden: list[str] = Field(max_length=150)


def _settings_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


# Per-integration display choices are independent of actual connectivity.
# Hiding a service from Integrations must never remove its credentials or disable its APIs.
CONNECTION_SERVICE_IDS = ("radarr", "sonarr", "lidarr", "bazarr", "sabnzbd", "plex", "opensubtitles", "time-adrift", "clock", "weather", "news", "ambient")
CONNECTION_HIDDEN_KEY = "connections_hub_hidden"


class ConnectionVisibilityRequest(BaseModel):
    service: Literal["radarr", "sonarr", "lidarr", "bazarr", "sabnzbd", "plex", "opensubtitles", "time-adrift", "clock", "weather", "news", "ambient"]
    visible: bool


def _connection_hidden(conn):
    return set(_read(conn, CONNECTION_HIDDEN_KEY)) & set(CONNECTION_SERVICE_IDS)


@router.get("/connections/visibility")
def get_connection_visibility():
    with db() as conn:
        _settings_table(conn)
        hidden = _connection_hidden(conn)
    return {"visible": {name: name not in hidden for name in CONNECTION_SERVICE_IDS}}


@router.put("/connections/visibility")
def save_connection_visibility(payload: ConnectionVisibilityRequest):
    with db() as conn:
        _settings_table(conn)
        hidden = _connection_hidden(conn)
        if payload.visible:
            hidden.discard(payload.service)
        else:
            hidden.add(payload.service)
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (CONNECTION_HIDDEN_KEY, json.dumps(sorted(hidden))),
        )
    return get_connection_visibility()


def _available(conn):
    # Standard library destinations exist only after a corresponding library
    # has been configured. Keep Settings available for adding the first one.
    kinds = {row["kind"] for row in conn.execute("SELECT DISTINCT kind FROM libraries")}
    entries = [{"id": key, "name": name, "kind": "system"} for key, name in NAV
               if key not in ("movies", "tv", "music") or key in kinds]
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
        # Migrate pre-Integrations layouts without losing the user's saved order.
        old_order = _read(conn, "sidebar_order")
        saved = list(dict.fromkeys(
            "connections" if item in ("sabnzbd", "services") else item
            for item in old_order
        ))
        old_hidden = set(_read(conn, "sidebar_hidden"))
        # The former Download Services link was often hidden by default.
        # Its visibility must not hide the replacement for the SABnzbd link.
        old_hidden.discard("services")
        hidden = set("connections" if item == "sabnzbd" else item
                     for item in old_hidden)
        hidden.update(item["id"] for item in entries if item.get("sidebar_hidden"))
        # Discard visibility settings for removed library types or deleted libraries.
        # Otherwise a future Settings save would submit now-invalid sidebar IDs.
        hidden.intersection_update(by_id)
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

def _icon_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sidebar_custom_icons (
        name TEXT PRIMARY KEY, png BLOB NOT NULL, revision INTEGER NOT NULL
    )""")


@router.get("/sidebar/icons")
def sidebar_icons_status():
    with db() as conn:
        _icon_table(conn)
        rows = conn.execute("SELECT name,revision FROM sidebar_custom_icons").fetchall()
        revisions = {r["name"]: r["revision"] for r in rows}
    return {"icons": [
        {"name": name, "custom": name in revisions,
         "url": f"/assets/sidebar-icon-{name}.png?v={revisions.get(name, 'pirate-v3')}"}
        for name in ICON_NAMES
    ]}


def sidebar_icon_bytes(name: str):
    """Return the customized icon or its built-in default, with revision."""
    if name not in ICON_NAMES:
        raise HTTPException(404, "Unknown sidebar icon")
    with db() as conn:
        _icon_table(conn)
        row = conn.execute(
            "SELECT png,revision FROM sidebar_custom_icons WHERE name=?", (name,)
        ).fetchone()
    if row:
        return bytes(row["png"]), str(row["revision"])
    from .sidebar_default_icons import default_icon_png
    return default_icon_png(name), "pirate-v3"


@router.put("/sidebar/icons/{name}")
async def upload_sidebar_icon(name: str, request: Request):
    if name not in ICON_NAMES:
        raise HTTPException(404, "Unknown sidebar icon")
    if request.headers.get("content-type", "").split(";")[0] not in (
            "image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "Use a PNG, JPEG, or WebP image")
    raw = await request.body()
    if not raw or len(raw) > 3_000_000:
        raise HTTPException(413, "Icon must be smaller than 3 MB")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            original.verify()
        with Image.open(io.BytesIO(raw)) as original:
            if original.width > 4096 or original.height > 4096:
                raise ValueError("Image dimensions exceed limit")
            icon = original.convert("RGBA")
            icon.thumbnail((256, 256), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            icon.save(output, format="PNG", optimize=True)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, "Invalid or oversized image")
    revision = time.time_ns()
    with db() as conn:
        _icon_table(conn)
        conn.execute("""INSERT INTO sidebar_custom_icons(name,png,revision)
            VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET
            png=excluded.png, revision=excluded.revision""",
            (name, output.getvalue(), revision))
    return {"name": name, "custom": True,
            "url": f"/assets/sidebar-icon-{name}.png?v={revision}"}


@router.delete("/sidebar/icons/{name}")
def restore_sidebar_icon(name: str):
    if name not in ICON_NAMES:
        raise HTTPException(404, "Unknown sidebar icon")
    with db() as conn:
        _icon_table(conn)
        conn.execute("DELETE FROM sidebar_custom_icons WHERE name=?", (name,))
    return {"name": name, "custom": False,
            "url": f"/assets/sidebar-icon-{name}.png?v=pirate-v3"}
