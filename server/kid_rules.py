"""What a kid profile may watch: a highest rating, whether unrated titles show,
which libraries, and per-title exceptions both ways.

Movie (MPAA) and TV (US TV Parental Guidelines) ratings share one scale, so a
single "Up to" choice covers both:

    0 TV-Y  ·  1 TV-Y7  ·  2 G / TV-G  ·  3 PG / TV-PG  ·  4 PG-13 / TV-14  ·  5 R / TV-MA  ·  6 NC-17
"""
from dataclasses import dataclass, field
import re

LEVELS = {
    "TV-Y": 0, "TV-Y7": 1, "TV-Y7-FV": 1, "G": 2, "TV-G": 2, "PG": 3, "TV-PG": 3,
    "PG-13": 4, "TV-14": 4, "R": 5, "TV-MA": 5, "NC-17": 6, "X": 6,
}
CHOICES = [  # (level, label) for the "Up to" setting
    (0, "TV-Y (little kids)"), (1, "TV-Y7"), (2, "G / TV-G"), (3, "PG / TV-PG"),
    (4, "PG-13 / TV-14"), (5, "R / TV-MA"),
]
_UNRATED = {"", "NR", "UR", "NOT RATED", "UNRATED", "N/A", "NONE"}


def normalize(rating):
    """A rating string as used on the scale (e.g. 'Rated PG-13' -> 'PG-13'), or ''."""
    text = re.sub(r"\s+", " ", str(rating or "")).strip().upper()
    text = re.sub(r"^(RATED|US:|US )\s*", "", text).strip()
    text = text.replace("TV Y", "TV-Y").replace("TVY", "TV-Y").replace("TV14", "TV-14").replace("TVMA", "TV-MA")
    text = text.replace("TVPG", "TV-PG").replace("TVG", "TV-G").replace("PG13", "PG-13").replace("NC17", "NC-17")
    return "" if text in _UNRATED else text if text in LEVELS else ""


def level(rating):
    """Where a rating sits on the shared scale, or None when unrated/unknown."""
    return LEVELS.get(normalize(rating))


def title_id(kind, library_id, key):
    """How exceptions name a title: 'movies:3:the matrix (1999)'."""
    return f"{kind}:{int(library_id)}:{key}"


@dataclass(frozen=True)
class KidRules:
    max_level: int = 3                      # PG / TV-PG
    allow_unrated: bool = False
    libraries: frozenset | None = None      # None = every library
    allow: frozenset = field(default_factory=frozenset)   # title ids always allowed
    block: frozenset = field(default_factory=frozenset)   # title ids never allowed

    @classmethod
    def from_json(cls, data):
        data = data if isinstance(data, dict) else {}
        try:
            top = min(6, max(0, int(data.get("max_level", 3))))
        except (TypeError, ValueError):
            top = 3
        libs = data.get("libraries")
        libs = None if libs is None else frozenset(
            n for n in libs if isinstance(n, int) and not isinstance(n, bool) and n > 0)
        ids = lambda name: frozenset(str(x)[:300] for x in (data.get(name) or [])[:2000] if isinstance(x, str))
        return cls(max_level=top, allow_unrated=bool(data.get("allow_unrated", False)),
                   libraries=libs, allow=ids("allow"), block=ids("block"))

    def to_json(self):
        return {"max_level": self.max_level, "allow_unrated": self.allow_unrated,
                "libraries": None if self.libraries is None else sorted(self.libraries),
                "allow": sorted(self.allow), "block": sorted(self.block)}

    def allows(self, kind, library_id, key, rating):
        """May the kid see this title? Exceptions win over the rating."""
        if self.libraries is not None and library_id not in self.libraries:
            return False
        if kind == "music":
            return True
        ident = title_id(kind, library_id, key)
        if ident in self.block:
            return False
        if ident in self.allow:
            return True
        where = level(rating)
        if where is None:
            return self.allow_unrated
        return where <= self.max_level
