"""Household profiles: Family, the owner and everyone else, each with their own
watch history and TV settings.

One person on the server: nothing changes, there is no picker. Once the owner
adds someone, the apps and browsers open on "Who's watching?" (/who). Picking
a profile stores a signed token in a cookie (apps, browsers at home) or, for
app.yarr.media, in a header its service worker adds. No PIN is needed to
watch; a profile can have an optional PIN, and an optional parent PIN keeps a
kid profile from switching away and protects these settings.

Viewer ids: Family keeps "" (the history the server already had); everyone
else is "p:<profile id>". Adults have the owner's role. Kids are limited like
barnacles (barnacle_access allowlist) plus their rating rules (kid_rules.py).

Security note: profiles organise a household; they are not accounts. Anyone
at home can pick an adult profile without a PIN unless one is set.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import barnacle_access, library
from . import viewer as viewer_mod
from .library import db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

COOKIE = "yarr_profile"
HEADER = "x-yarr-profile"
SET_HEADER = "x-yarr-profile-set"
FAMILY = "family"
COLORS = ("#C62838", "#9B9B9B", "#E07B39", "#D4A72C", "#3E9C6B", "#2F86A6", "#7457C6", "#C2417F")
KINDS = ("family", "adult", "kid")
PIN = re.compile(r"\d{4,8}")
# Paths anyone may load before choosing a profile.
OPEN_PATHS = {"/who", "/health", "/favicon.ico", "/favicon.png", "/app.webmanifest",
              "/api/profiles", "/api/profiles/choose", "/api/server/info", "/api/viewer"}
OPEN_PREFIXES = ("/assets/", "/api/device/", "/remote/")

_lock = threading.Lock()
_cache = {"version": -1, "data": None, "path": None}
_version = [0]
_attempts = {}      # profile id -> (failures, locked until)


def _setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS profiles(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, color TEXT NOT NULL,
        pin_hash TEXT, is_owner INTEGER NOT NULL DEFAULT 0, account_id TEXT,
        rules_json TEXT, sort INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)""")


def _changed():
    with _lock:
        _version[0] += 1


class Profile:
    __slots__ = ("id", "name", "kind", "color", "pin_hash", "is_owner", "account_id", "rules", "sort")

    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.kind = row["kind"]
        self.color = row["color"]
        self.pin_hash = row["pin_hash"]
        self.is_owner = bool(row["is_owner"])
        self.account_id = row["account_id"]
        try:
            self.rules = json.loads(row["rules_json"] or "{}")
        except ValueError:
            self.rules = {}
        self.sort = row["sort"]

    @property
    def viewer_id(self):
        return "" if self.id == FAMILY else "p:" + self.id

    def viewer(self):
        if self.kind == "kid":
            from . import kid_rules
            rules = kid_rules.KidRules.from_json(self.rules)
            return viewer_mod.Viewer(id=self.viewer_id, role="kid", name=self.name, profile=self.id,
                                     color=self.color, libraries=rules.libraries, rules=rules)
        return viewer_mod.Viewer(id=self.viewer_id, role="owner", name=self.name, profile=self.id, color=self.color)

    def public(self):
        return {"id": self.id, "name": self.name, "kind": self.kind, "color": self.color,
                "has_pin": bool(self.pin_hash), "is_owner": self.is_owner}


class Household:
    """A cached snapshot of the profiles and the signing secret."""

    def __init__(self, rows, secret, parent_pin):
        self.profiles = [Profile(r) for r in rows]
        self.by_id = {p.id: p for p in self.profiles}
        self.secret = secret
        self.parent_pin = parent_pin

    @property
    def people(self):
        return [p for p in self.profiles if p.kind != "family"]

    @property
    def active(self):
        return len(self.people) >= 2

    def token(self, profile_id):
        body = profile_id + "." + str(int(time.time()))
        return body + "." + _sign(self.secret, body)

    def verify(self, token):
        """The profile a token names, or None."""
        if not token or len(token) > 200:
            return None
        body, _, signature = token.rpartition(".")
        if not body or not hmac.compare_digest(_sign(self.secret, body), signature):
            return None
        return self.by_id.get(body.partition(".")[0])


def _sign(secret, body):
    digest = hmac.new(secret, body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode().rstrip("=")


def household():
    with _lock:
        version = _version[0]
        if _cache["version"] == version and _cache["data"] is not None and _cache["path"] == library.DB_PATH:
            return _cache["data"]
    with db() as conn:
        _setup(conn)
        rows = conn.execute("SELECT * FROM profiles ORDER BY CASE kind WHEN 'family' THEN 0 ELSE 1 END, "
                            "is_owner DESC, sort, created_at").fetchall()
        secret = conn.execute("SELECT value FROM app_settings WHERE key='profile_secret'").fetchone()
        if secret is None:
            value = secrets.token_hex(32)
            conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('profile_secret',?)", (value,))
            secret = conn.execute("SELECT value FROM app_settings WHERE key='profile_secret'").fetchone()
        parent = conn.execute("SELECT value FROM app_settings WHERE key='profile_parent_pin'").fetchone()
    data = Household(rows, bytes.fromhex(secret["value"]), parent["value"] if parent else None)
    with _lock:
        if _version[0] == version:
            _cache.update(version=version, data=data, path=library.DB_PATH)
    return data


# ---- PINs ------------------------------------------------------------------

def _hash_pin(pin):
    salt = secrets.token_bytes(16)
    return salt.hex() + "$" + hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def _pin_matches(stored, pin):
    if not stored or not pin or not PIN.fullmatch(pin):
        return False
    salt, _, digest = stored.partition("$")
    try:
        check = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex()
    except ValueError:
        return False
    return hmac.compare_digest(check, digest)


def _check_pin(slot, stored, pin):
    """Raises 403 for a wrong PIN; a few wrong tries lock that PIN for a while."""
    failures, until = _attempts.get(slot, (0, 0))
    if until > time.time():
        raise HTTPException(429, f"Too many wrong PINs. Try again in {int(until - time.time()) + 1} seconds.")
    if _pin_matches(stored, pin):
        _attempts.pop(slot, None)
        return
    failures += 1
    _attempts[slot] = (failures, time.time() + 30 if failures >= 5 else 0)
    raise HTTPException(403, "pin_required" if not pin else "Wrong PIN.")


def _require_parent(pin):
    """Changes to profiles need the parent PIN when one is set."""
    home = household()
    if home.parent_pin:
        _check_pin("parent", home.parent_pin, pin)


def _manager():
    """Only adults (not kids or barnacles) manage profiles."""
    if viewer_mod.current().restricted:
        raise HTTPException(403, "Only adults can change profiles.")


# ---- API -------------------------------------------------------------------

@router.get("")
def list_profiles():
    """Who's watching: every profile and which one this device is using."""
    home = household()
    who = viewer_mod.current()
    if who.is_barnacle:
        return {"active": False, "current": None, "profiles": [], "parent_pin": False, "locked": False}
    current = home.by_id.get(who.profile) if home.active else None
    return {"active": home.active, "current": current.public() if current else None,
            "profiles": [p.public() for p in home.profiles] if home.active else [],
            "parent_pin": bool(home.parent_pin),
            "locked": bool(current and current.kind == "kid" and home.parent_pin),
            "can_manage": not who.restricted}


class Choice(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    pin: str | None = Field(None, max_length=8)


@router.post("/choose")
def choose(choice: Choice, request: Request, response: Response):
    home = household()
    if viewer_mod.current().is_barnacle:
        raise HTTPException(403, "Profiles are for the server's household.")
    target = home.by_id.get(choice.id)
    if target is None or not home.active:
        raise HTTPException(404, "No such profile.")
    current = home.by_id.get(viewer_mod.current().profile)
    if current and current.kind == "kid" and home.parent_pin and target.id != current.id:
        # A kid profile stays put without the parent PIN.
        _check_pin("parent", home.parent_pin, choice.pin)
    elif target.pin_hash and not (current and current.id == target.id):
        try:
            _check_pin(target.id, target.pin_hash, choice.pin)
        except HTTPException:
            if not (home.parent_pin and _pin_matches(home.parent_pin, choice.pin)):
                raise
    token = home.token(target.id)
    _set_token(response, request, token)
    return {"profile": target.public(), "token": token}


def _set_token(response, request, token):
    secure = "; Secure" if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" else ""
    if token:
        response.headers.append("set-cookie", f"{COOKIE}={token}; Path=/; Max-Age=34560000; HttpOnly; SameSite=Lax{secure}")
    else:
        response.headers.append("set-cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}")
    response.headers[SET_HEADER] = token


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    kind: str = Field("adult", pattern="^(adult|kid)$")
    color: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")


class Setup(BaseModel):
    owner_name: str = Field(min_length=1, max_length=30)
    person: Person


def _clean(name):
    name = " ".join(str(name).split())
    if not name:
        raise HTTPException(422, "Enter a name.")
    return name[:30]


def _next_color(conn):
    used = {row["color"] for row in conn.execute("SELECT color FROM profiles")}
    return next((c for c in COLORS if c not in used), COLORS[len(used) % len(COLORS)])


def _insert(conn, pid, name, kind, color=None, is_owner=False, rules=None):
    conn.execute("INSERT INTO profiles(id,name,kind,color,is_owner,rules_json,sort,created_at) VALUES(?,?,?,?,?,?,?,?)",
                 (pid, name, kind, color or _next_color(conn), int(is_owner),
                  json.dumps(rules) if rules is not None else None,
                  (conn.execute("SELECT COALESCE(MAX(sort),0)+1 FROM profiles").fetchone()[0]), time.time()))


def _default_rules():
    from . import kid_rules
    return kid_rules.KidRules().to_json()


@router.post("/setup")
def setup(body: Setup, x_yarr_parent_pin: str | None = Header(None)):
    """Turns profiles on: Family (the shared history), the owner and one more person."""
    _manager()
    _require_parent(x_yarr_parent_pin)
    with db() as conn:
        _setup(conn)
        if conn.execute("SELECT COUNT(*) FROM profiles WHERE kind!='family'").fetchone()[0] >= 2:
            raise HTTPException(409, "Profiles are already set up.")
        if conn.execute("SELECT 1 FROM profiles WHERE id=?", (FAMILY,)).fetchone() is None:
            _insert(conn, FAMILY, "Family", "family", COLORS[0])
        if conn.execute("SELECT 1 FROM profiles WHERE is_owner=1").fetchone() is None:
            _insert(conn, secrets.token_hex(5), _clean(body.owner_name), "adult", is_owner=True)
        _insert(conn, secrets.token_hex(5), _clean(body.person.name), body.person.kind, body.person.color,
                rules=_default_rules() if body.person.kind == "kid" else None)
    _changed()
    return list_profiles()


@router.post("")
def add_person(person: Person, x_yarr_parent_pin: str | None = Header(None)):
    _manager()
    _require_parent(x_yarr_parent_pin)
    if not household().active:
        raise HTTPException(409, "Set up profiles first.")
    pid = secrets.token_hex(5)
    with db() as conn:
        _setup(conn)
        if conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= 20:
            raise HTTPException(409, "A server can have up to 20 profiles.")
        _insert(conn, pid, _clean(person.name), person.kind, person.color,
                rules=_default_rules() if person.kind == "kid" else None)
    _changed()
    return household().by_id[pid].public()


class Edit(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=30)
    color: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    kind: str | None = Field(None, pattern="^(adult|kid)$")


@router.put("/{pid}")
def edit_person(pid: str, edit: Edit, x_yarr_parent_pin: str | None = Header(None)):
    _manager()
    _require_parent(x_yarr_parent_pin)
    profile = household().by_id.get(pid)
    if profile is None:
        raise HTTPException(404, "No such profile.")
    if edit.kind and (profile.kind == "family" or profile.is_owner) and edit.kind != profile.kind:
        raise HTTPException(409, "Family and the owner stay adult profiles.")
    with db() as conn:
        if edit.name is not None:
            conn.execute("UPDATE profiles SET name=? WHERE id=?", (_clean(edit.name), pid))
        if edit.color is not None:
            conn.execute("UPDATE profiles SET color=? WHERE id=?", (edit.color.upper(), pid))
        if edit.kind is not None and edit.kind != profile.kind:
            conn.execute("UPDATE profiles SET kind=?, rules_json=COALESCE(rules_json,?) WHERE id=?",
                         (edit.kind, json.dumps(_default_rules()), pid))
    _changed()
    return household().by_id[pid].public()


@router.delete("/{pid}")
def remove_person(pid: str, forget: bool = False, x_yarr_parent_pin: str | None = Header(None)):
    """Removes a person. Their watch history is kept unless forget=true."""
    _manager()
    _require_parent(x_yarr_parent_pin)
    profile = household().by_id.get(pid)
    if profile is None:
        raise HTTPException(404, "No such profile.")
    if profile.kind == "family" or profile.is_owner:
        raise HTTPException(409, "Family and the owner's profile can't be removed.")
    with db() as conn:
        conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
        if forget:
            vid = "p:" + pid
            conn.execute("DELETE FROM playback_progress WHERE viewer=?", (vid,))
            conn.execute("DELETE FROM continue_watching_hidden WHERE viewer=?", (vid,))
            conn.execute("DELETE FROM app_settings WHERE key LIKE ?", (vid + "|%",))
    _changed()
    return {"removed": pid}


class PinChange(BaseModel):
    pin: str | None = Field(None, max_length=8)


@router.put("/{pid}/pin")
def set_pin(pid: str, change: PinChange, x_yarr_parent_pin: str | None = Header(None)):
    """Sets (or with null, removes) a profile's PIN."""
    _manager()
    _require_parent(x_yarr_parent_pin)
    if pid not in household().by_id:
        raise HTTPException(404, "No such profile.")
    if change.pin is not None and not PIN.fullmatch(change.pin):
        raise HTTPException(422, "A PIN is 4 to 8 digits.")
    with db() as conn:
        conn.execute("UPDATE profiles SET pin_hash=? WHERE id=?",
                     (_hash_pin(change.pin) if change.pin else None, pid))
    _attempts.pop(pid, None)
    _changed()
    return household().by_id[pid].public()


@router.put("/parent-pin/set")
def set_parent_pin(change: PinChange, x_yarr_parent_pin: str | None = Header(None)):
    """The parent PIN keeps kid profiles from switching away and protects these settings."""
    _manager()
    _require_parent(x_yarr_parent_pin)
    if change.pin is not None and not PIN.fullmatch(change.pin):
        raise HTTPException(422, "A PIN is 4 to 8 digits.")
    with db() as conn:
        _setup(conn)
        if change.pin:
            conn.execute("INSERT INTO app_settings(key,value) VALUES('profile_parent_pin',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_hash_pin(change.pin),))
        else:
            conn.execute("DELETE FROM app_settings WHERE key='profile_parent_pin'")
    _attempts.pop("parent", None)
    _changed()
    return {"parent_pin": bool(change.pin)}


@router.post("/parent-pin/check")
def check_parent_pin(change: PinChange):
    """Lets the People page ask for the parent PIN once before showing edits."""
    _manager()
    home = household()
    if home.parent_pin:
        _check_pin("parent", home.parent_pin, change.pin)
    return {"ok": True}


# ---- Who's watching, per request --------------------------------------------

def _token(headers):
    token = headers.get(HEADER)
    if token:
        return token.strip()
    for part in headers.get("cookie", "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value
    return None


def _is_open(path):
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


async def _reply(send, status, headers, body=b""):
    await send({"type": "http.response.start", "status": status,
                "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers]})
    await send({"type": "http.response.body", "body": body})


class ProfileMiddleware:
    """Turns the owner into the household profile this device chose."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or viewer_mod.current() is not viewer_mod.OWNER:
            return await self.app(scope, receive, send)
        home = household()
        if not home.active:
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        profile = home.verify(_token(headers))
        if profile is None:
            if _is_open(path):
                return await self.app(scope, receive, send)
            if method in ("GET", "HEAD") and not path.startswith("/api/") and "text/html" in headers.get("accept", ""):
                target = path + ("?" + scope["query_string"].decode("latin-1") if scope.get("query_string") else "")
                return await _reply(send, 303, [("location", "/who?next=" + quote(target, safe="")),
                                                ("cache-control", "no-store")])
            # Older apps' native requests carry no profile: they count as Family,
            # unless Family has a PIN.
            family = home.by_id.get(FAMILY)
            if family is not None and family.pin_hash:
                return await _reply(send, 401, [("content-type", "application/json"), ("cache-control", "no-store")],
                                    b'{"detail":"choose_profile"}')
            return await self.app(scope, receive, send)
        who = profile.viewer()
        if who.restricted:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            if not await asyncio.to_thread(barnacle_access.allowed, who, method, path, query):
                if method == "GET" and not path.startswith("/api/") and "text/html" in headers.get("accept", ""):
                    return await _reply(send, 303, [("location", "/"), ("cache-control", "no-store")])
                return await _reply(send, 403, [("content-type", "application/json"), ("cache-control", "no-store")],
                                    b'{"detail":"Not available on this profile."}')
        token = viewer_mod.use(who)
        try:
            return await self.app(scope, receive, send)
        finally:
            viewer_mod.reset(token)
