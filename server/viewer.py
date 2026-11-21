"""Who is watching this request: the owner (or a household profile), or a barnacle.

Requests from the home network, and remote requests with an owner pass, are
the owner. A remote request with a barnacle pass (someone the owner shares
with through yarr.media) is that barnacle: they see only the libraries the
owner chose and have their own watch history. Set per request by
RemotePassMiddleware; endpoints read it with current().

Household profiles (server/profiles.py) refine the owner: Family keeps the
owner's id "" (the history the server already had); everyone else is
"p:<profile id>". Adults have the owner's role; kids are limited like
barnacles, plus their rating rules.
"""
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Viewer:
    id: str = ""                       # "" = the owner; "u:<account id>" = a barnacle
    role: str = "owner"
    name: str = ""
    libraries: frozenset | None = None  # None = every library
    profile: str = ""                  # household profile id ("" = no profiles in use)
    color: str = ""
    rules: object = None               # kids: profiles.KidRules

    @property
    def is_barnacle(self):
        return self.role == "barnacle"

    @property
    def restricted(self):
        """Barnacles and kids only watch and listen (barnacle_access allowlist)."""
        return self.role in ("barnacle", "kid")

    def can_see(self, library_id):
        return self.libraries is None or library_id in self.libraries

    def public(self):
        return {"role": self.role, "name": self.name,
                "libraries": None if self.libraries is None else sorted(self.libraries),
                "profile": {"id": self.profile, "name": self.name, "color": self.color} if self.profile else None}


OWNER = Viewer()
_current = ContextVar("yarr_viewer", default=OWNER)


def current():
    return _current.get()


def use(viewer):
    """Set the viewer for the rest of this request; returns a token for reset()."""
    return _current.set(viewer)


def reset(token):
    _current.reset(token)


def from_claims(claims):
    """The viewer a verified pass describes."""
    if claims.get("role") != "barnacle":
        return OWNER
    libs = frozenset(n for n in claims.get("lib") or [] if isinstance(n, int) and not isinstance(n, bool) and n > 0)
    name = str(claims.get("nm") or "")[:40]
    return Viewer(id="u:" + str(claims["sub"]), role="barnacle", name=name, libraries=libs)
