"""Per-person preferences: each profile (or barnacle) keeps its own value of a
setting once they change it; until then the server-wide value applies.

Stored in app_settings as "<viewer id>|<key>". The owner/Family ("" id) uses
the plain keys, exactly as before profiles existed.
"""
from .viewer import current


def prefix():
    who = current()
    return who.id + "|" if who.id else ""


def key(name):
    return prefix() + name


def read(conn, names):
    """{name: value} for these settings: the person's own value, else the shared one."""
    names = list(names)
    marks = ",".join("?" * len(names))
    values = {row["key"]: row["value"] for row in conn.execute(
        f"SELECT key,value FROM app_settings WHERE key IN ({marks})", names)}
    own = prefix()
    if own:
        for row in conn.execute(f"SELECT key,value FROM app_settings WHERE key IN ({marks})",
                                [own + n for n in names]):
            values[row["key"][len(own):]] = row["value"]
    return values
