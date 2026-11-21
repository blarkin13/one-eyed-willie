"""Encrypted backups of everyone's watch history to yarr.media, and restoring
them on a new or reinstalled server.

What's in a backup: watch progress and Continue Watching choices for every
person (Family, profiles, barnacles), household profiles and their PINs and
kids' limits, linked accounts, and each person's own playback/subtitle/TV
settings. Not media, not file contents, not integration keys or passwords.

Encryption: turning backups on shows the owner a recovery code once. The key
comes from that code (scrypt, with a random salt kept in the backup), and the
backup is AES-256-GCM encrypted on this server, so yarr.media only ever stores
bytes it can't read. The server keeps the derived key to back up nightly; a
reinstalled server needs the recovery code to restore.

Titles are matched by library name and the file's path inside its library, so
a reinstall with the same folders restores into the right media.
"""
import gzip
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import viewer as viewer_mod
from .library import db

router = APIRouter(prefix="/api/backup", tags=["backup"])

MAGIC = b"YRB1"
ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"   # no 0/O, 1/I/L, U
MAX_BYTES = 1_400_000
DAY = 24 * 3600
_lock = threading.Lock()


def _settings(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM app_settings WHERE key LIKE 'backup_%'")}


def _put(conn, key, value):
    if value is None:
        conn.execute("DELETE FROM app_settings WHERE key=?", (key,))
    else:
        conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, str(value)))


def _owner_only():
    if viewer_mod.current().restricted or viewer_mod.current().is_barnacle:
        raise HTTPException(403, "Only the owner can manage backups.")


# ---- Recovery code and encryption -------------------------------------------

def new_code():
    raw = "".join(secrets.choice(ALPHABET) for _ in range(25))
    return "-".join(raw[i:i + 5] for i in range(0, 25, 5))


def _clean_code(code):
    text = "".join(ch for ch in str(code or "").upper() if ch.isalnum())
    text = text.replace("O", "0").replace("I", "1")
    if len(text) != 25 or any(ch not in ALPHABET for ch in text):
        raise HTTPException(422, "A recovery code is 25 letters and numbers, like ABCDE-FGHJK-…")
    return text


def derive(code, salt):
    return hashlib.scrypt(_clean_code(code).encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def seal(payload, key, salt):
    nonce = secrets.token_bytes(12)
    body = gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0)
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, body, MAGIC + salt)


def open_sealed(blob, code):
    if len(blob) < 4 + 16 + 12 + 16 or blob[:4] != MAGIC:
        raise HTTPException(422, "That isn't a Yarr Media backup.")
    salt, nonce, sealed = blob[4:20], blob[20:32], blob[32:]
    try:
        body = AESGCM(derive(code, salt)).decrypt(nonce, sealed, MAGIC + salt)
    except InvalidTag:
        raise HTTPException(403, "That recovery code doesn't open this backup.")
    return json.loads(gzip.decompress(body)), salt


# ---- What goes in -----------------------------------------------------------

def _relative(path, root):
    try:
        return str(Path(path).relative_to(Path(root)))
    except ValueError:
        return None


def collect():
    """Everything worth keeping, with titles named by library and relative path."""
    with db() as conn:
        libraries = {r["id"]: dict(r) for r in conn.execute("SELECT id,name,kind,path FROM libraries")}
        media = {}
        for r in conn.execute("SELECT m.id,m.library_id,m.path,m.source_root FROM media m "
                              "WHERE m.id IN (SELECT media_id FROM playback_progress)"):
            lib = libraries.get(r["library_id"])
            rel = _relative(r["path"], r["source_root"] or (lib or {}).get("path", ""))
            if lib and rel:
                media[r["id"]] = [lib["name"], lib["kind"], rel]
        progress = [[r["viewer"], *media[r["media_id"]], r["position_seconds"], r["duration_seconds"],
                     r["completed"], r["updated_at"]]
                    for r in conn.execute("SELECT * FROM playback_progress") if r["media_id"] in media]
        hidden = [[r["viewer"], r["kind"], libraries[r["library_id"]]["name"], r["media_key"]]
                  for r in conn.execute("SELECT * FROM continue_watching_hidden") if r["library_id"] in libraries]
        tables = {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        people = [dict(r) for r in conn.execute("SELECT * FROM profiles")] if "profiles" in tables else []
        accounts = ([dict(r) for r in conn.execute("SELECT * FROM household_accounts")]
                    if "household_accounts" in tables else [])
        settings = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key,value FROM app_settings WHERE key LIKE '%|%' OR key IN ('profile_secret','profile_parent_pin')")}
    lib_names = {lib["id"]: lib["name"] for lib in libraries.values()}
    for person in people:                                # kids' library limits, by name
        try:
            rules = json.loads(person.get("rules_json") or "null")
        except ValueError:
            rules = None
        if isinstance(rules, dict) and isinstance(rules.get("libraries"), list):
            rules["library_names"] = [lib_names[i] for i in rules["libraries"] if i in lib_names]
            person["rules_json"] = json.dumps(rules)
    return {"v": 1, "made_at": int(time.time()), "progress": progress, "hidden": hidden,
            "profiles": people, "accounts": accounts, "settings": settings}


def apply(data):
    """Merges a backup into this server: newer progress wins; nothing here is removed."""
    if not isinstance(data, dict) or data.get("v") != 1:
        raise HTTPException(422, "This backup is from a newer version of Yarr Media.")
    counts = {"progress": 0, "profiles": 0}
    with db() as conn:
        libraries = {(r["name"], r["kind"]): dict(r) for r in conn.execute("SELECT id,name,kind,path FROM libraries")}
        by_name = {r["name"]: r["id"] for r in libraries.values()}
        index = {}
        for r in conn.execute("SELECT m.id,m.path,m.source_root,l.name,l.kind,l.path AS root FROM media m JOIN libraries l ON l.id=m.library_id"):
            rel = _relative(r["path"], r["source_root"] or r["root"])
            if rel:
                index[(r["name"], r["kind"], rel)] = r["id"]
        for row in data.get("progress") or []:
            try:
                viewer, lib_name, kind, rel, position, duration, completed, updated = row
            except (TypeError, ValueError):
                continue
            media_id = index.get((lib_name, kind, rel))
            if media_id is None:
                continue
            changed = conn.execute(
                "INSERT INTO playback_progress(viewer,media_id,position_seconds,duration_seconds,completed,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(viewer,media_id) DO UPDATE SET "
                "position_seconds=excluded.position_seconds,duration_seconds=excluded.duration_seconds,"
                "completed=excluded.completed,updated_at=excluded.updated_at WHERE excluded.updated_at>playback_progress.updated_at",
                (str(viewer)[:80], media_id, float(position), float(duration), int(bool(completed)), str(updated)[:40])).rowcount
            counts["progress"] += changed
        for row in data.get("hidden") or []:
            try:
                viewer, kind, lib_name, key = row
            except (TypeError, ValueError):
                continue
            if lib_name in by_name:
                conn.execute("INSERT OR IGNORE INTO continue_watching_hidden(viewer,kind,library_id,media_key) VALUES(?,?,?,?)",
                             (str(viewer)[:80], str(kind)[:20], by_name[lib_name], str(key)[:300]))
        from . import profiles
        profiles._setup(conn)
        conn.execute("CREATE TABLE IF NOT EXISTS household_accounts(viewer_id TEXT PRIMARY KEY, name TEXT NOT NULL, last_seen REAL NOT NULL)")
        for person in data.get("profiles") or []:
            if not isinstance(person, dict) or not person.get("id"):
                continue
            rules = person.get("rules_json")
            try:
                parsed = json.loads(rules) if rules else None
            except ValueError:
                parsed = None
            if isinstance(parsed, dict) and "library_names" in parsed:
                parsed["libraries"] = [by_name[n] for n in parsed.pop("library_names") if n in by_name]
                rules = json.dumps(parsed)
            counts["profiles"] += conn.execute(
                "INSERT OR IGNORE INTO profiles(id,name,kind,color,pin_hash,is_owner,account_id,rules_json,sort,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (str(person["id"])[:40], str(person.get("name") or "?")[:30], person.get("kind") if person.get("kind") in ("family", "adult", "kid") else "adult",
                 str(person.get("color") or "#9B9B9B")[:7], person.get("pin_hash"), int(bool(person.get("is_owner"))),
                 person.get("account_id"), rules, int(person.get("sort") or 0), float(person.get("created_at") or time.time()))).rowcount
        for account in data.get("accounts") or []:
            if isinstance(account, dict) and account.get("viewer_id"):
                conn.execute("INSERT OR IGNORE INTO household_accounts(viewer_id,name,last_seen) VALUES(?,?,?)",
                             (str(account["viewer_id"])[:120], str(account.get("name") or "")[:80], float(account.get("last_seen") or 0)))
        for key, value in (data.get("settings") or {}).items():
            if isinstance(key, str) and isinstance(value, str) and ("|" in key or key in ("profile_secret", "profile_parent_pin")):
                conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (key[:200], value[:2000]))
    from . import profiles
    profiles._changed()
    return counts


# ---- Talking to yarr.media --------------------------------------------------

def _credential():
    from . import yarr_pairing
    with yarr_pairing.LOCK:
        record = yarr_pairing._read()
    if record.get("status") != "paired" or not record.get("poll_secret"):
        raise HTTPException(409, "Connect this server to Yarr first (Settings → Remote Access).")
    return yarr_pairing.ACCOUNT_URL, record["poll_secret"]


def _cloud(method, path, body=None, *, raw=False):
    base, secret = _credential()
    headers = {"Authorization": "Bearer " + secret, "User-Agent": "YarrServerBackup/1",
               "Accept": "application/octet-stream" if raw else "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/octet-stream"
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise HTTPException(404, "No backup found.")
        if error.code in (401, 403):
            raise HTTPException(401, "This server's Yarr connection is no longer authorized.")
        raise HTTPException(502, "yarr.media didn't accept the backup.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(503, "yarr.media can't be reached right now.")
    return data if raw else json.loads(data or b"{}")


def back_up_now():
    """Encrypts and uploads a backup. Returns its size; raises HTTPException on failure."""
    with _lock:
        with db() as conn:
            saved = _settings(conn)
        if not saved.get("backup_key"):
            raise HTTPException(409, "Backups are off.")
        blob = seal(collect(), bytes.fromhex(saved["backup_key"]), bytes.fromhex(saved["backup_salt"]))
        if len(blob) > MAX_BYTES:
            raise HTTPException(413, "The backup is too large.")
        try:
            _cloud("PUT", "/api/connection/backup", blob)
        except HTTPException as error:
            with db() as conn:
                _put(conn, "backup_error", error.detail)
            raise
        with db() as conn:
            _put(conn, "backup_last", int(time.time()))
            _put(conn, "backup_size", len(blob))
            _put(conn, "backup_error", None)
        return len(blob)


def nightly_loop(stop):
    """Backs up once a day while backups are on; never affects playback."""
    if stop.wait(120):
        return
    while not stop.is_set():
        try:
            with db() as conn:
                saved = _settings(conn)
            if saved.get("backup_key") and time.time() - float(saved.get("backup_last") or 0) >= DAY:
                back_up_now()
        except Exception:
            pass
        stop.wait(3600)


# ---- API --------------------------------------------------------------------

@router.get("")
def status():
    _owner_only()
    with db() as conn:
        saved = _settings(conn)
    from . import yarr_pairing
    return {"enabled": bool(saved.get("backup_key")), "paired": yarr_pairing.pro_state()["paired"],
            "last_backup": int(saved["backup_last"]) if saved.get("backup_last") else None,
            "size": int(saved["backup_size"]) if saved.get("backup_size") else None,
            "error": saved.get("backup_error")}


@router.post("/enable")
def enable():
    """Turns backups on and returns the recovery code (shown once; not stored)."""
    _owner_only()
    _credential()
    code = new_code()
    salt = secrets.token_bytes(16)
    with db() as conn:
        _settings(conn)
        _put(conn, "backup_key", derive(code, salt).hex())
        _put(conn, "backup_salt", salt.hex())
        _put(conn, "backup_last", None)
    try:
        back_up_now()
    except HTTPException:
        pass
    return {"recovery_code": code, **status()}


@router.post("/disable")
def disable():
    """Stops backups and deletes the copy on yarr.media."""
    _owner_only()
    with db() as conn:
        _settings(conn)
        for key in ("backup_key", "backup_salt", "backup_last", "backup_size", "backup_error"):
            _put(conn, key, None)
    try:
        _cloud("DELETE", "/api/connection/backup")
    except HTTPException:
        pass
    return status()


@router.post("/now")
def now():
    _owner_only()
    size = back_up_now()
    return {"size": size, **status()}


@router.get("/available")
def available():
    """Backups saved by this owner's servers (including old installs)."""
    _owner_only()
    return _cloud("GET", "/api/connection/backups")


class Restore(BaseModel):
    id: str = Field(min_length=8, max_length=64, pattern="^[A-Za-z0-9-]+$")
    code: str = Field(min_length=10, max_length=60)


@router.post("/restore")
def restore(body: Restore):
    """Downloads a backup, opens it with the recovery code and merges it in.
    Backups then continue under the same recovery code."""
    _owner_only()
    blob = _cloud("GET", "/api/connection/backups/" + body.id, raw=True)
    data, salt = open_sealed(blob, body.code)
    counts = apply(data)
    with db() as conn:
        _settings(conn)
        _put(conn, "backup_key", derive(body.code, salt).hex())
        _put(conn, "backup_salt", salt.hex())
    return {"restored": counts, **status()}
