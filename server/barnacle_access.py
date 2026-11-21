"""What a barnacle may do on this server: watch and listen, nothing else.

A strict allowlist, checked before any page or API runs. Barnacles can browse
and play their allowed libraries, keep their own progress, and read the
appearance settings pages need. Settings, integrations, downloads, deleting,
rescans, metadata edits and every other owner tool are refused. Anything that
names a library or a title is checked against the barnacle's libraries.
"""
import re

from .library import db

_ID = r"(\d+)"
# (methods, path pattern, which part identifies the title/library to check)
#   "media"   -> the first group is a media id
#   "library" -> the first group is a library id
#   None      -> nothing in the path; query parameters are still checked
_RULES = [
    # Pages
    ({"GET", "HEAD"}, r"/", None),
    ({"GET", "HEAD"}, r"/(movies|movie|tv|tv/show|tv/season|tv/episode|music|person|credit|settings)", None),
    ({"GET", "HEAD"}, r"/watch/" + _ID, "media"),
    ({"GET", "HEAD"}, r"/(favicon\.ico|favicon\.png|app\.webmanifest)", None),
    ({"GET", "HEAD"}, r"/assets/[A-Za-z0-9._/-]+", None),
    # Browsing
    ({"GET"}, r"/api/(home|home/revision|catalog|catalog/all|catalog/revision|libraries|server/info|viewer)", None),
    ({"GET"}, r"/api/libraries/" + _ID + r"/(header|icon)\.png", "library"),
    ({"GET"}, r"/api/artwork/(thumb/)?[A-Za-z0-9_-]+(\.[a-z]+)?", None),
    ({"GET"}, r"/api/movies/details", None),
    ({"POST"}, r"/api/movies/posters", None),
    ({"GET"}, r"/api/tv/(poster|show|season|episode|next)", None),
    ({"GET"}, r"/api/music/catalog", None),
    ({"GET"}, r"/api/music/artist-top", None),
    ({"GET"}, r"/api/music/tracks/" + _ID + r"/(stream|art|details)", "media"),
    ({"GET"}, r"/api/people/(profile|local-title)", None),
    ({"GET"}, r"/api/settings/(ambient|playback|sidebar|sidebar/icons|subtitle-appearance|tv-appearance)", None),
    # Their own playback, subtitle and TV look preferences (stored per person)
    ({"PUT"}, r"/api/settings/(playback|subtitle-appearance|tv-appearance)", None),
    # Who's watching (household profiles)
    ({"GET", "HEAD"}, r"/who", None),
    ({"GET"}, r"/api/profiles", None),
    ({"POST"}, r"/api/profiles/choose", None),
    ({"GET"}, r"/api/themes/" + _ID + r"/(audio|info)", "media"),
    # Playing
    ({"GET", "HEAD"}, r"/api/watch/" + _ID + r"/(status|stream|transcode)", "media"),
    ({"POST"}, r"/api/stream/hls/start/" + _ID, "media"),
    ({"GET"}, r"/api/stream/hls/(audio|estimates)/" + _ID, "media"),
    ({"GET"}, r"/api/stream/hls/qualities", None),
    ({"GET"}, r"/api/stream/hls/[A-Za-z0-9_-]+/(status|[A-Za-z0-9_.-]+)", None),
    ({"DELETE"}, r"/api/stream/hls/[A-Za-z0-9_-]+", None),
    ({"GET"}, r"/api/stream/subtitles/" + _ID, "media"),
    # Downloading for offline use (through the owner's Pro)
    ({"GET"}, r"/api/downloads/status", None),
    ({"GET"}, r"/api/downloads/options/" + _ID, "media"),
    ({"POST"}, r"/api/downloads/prepare/" + _ID, "media"),
    ({"GET", "HEAD"}, r"/api/downloads/jobs/[a-f0-9]{32}(/file)?", None),
    ({"GET", "HEAD"}, r"/api/downloads/music/" + _ID, "media"),
    ({"GET"}, r"/api/stream/subtitles/" + _ID + r"/[A-Za-z0-9_.:-]+\.vtt", "media"),
    ({"GET"}, r"/api/maintenance/preview/" + _ID + r"(/[A-Za-z0-9_.-]+)?", "media"),
    # Their own history
    ({"POST", "PUT"}, r"/api/playback/progress", None),
    ({"PUT"}, r"/api/watch/" + _ID + r"/watched", "media"),
    ({"PUT"}, r"/api/tv/(show|season)/watched", None),
    ({"POST"}, r"/api/home/continue/" + _ID + r"/(dismiss|start)", "media"),
]
_COMPILED = [(methods, re.compile(pattern + r"\Z"), kind) for methods, pattern, kind in _RULES]
# The HLS token routes above must not swallow the start/audio/estimates/qualities
# routes' paths for other methods; those are matched first because of order.


def media_library(media_id):
    with db() as connection:
        row = connection.execute("SELECT library_id FROM media WHERE id=?", (media_id,)).fetchone()
    return row["library_id"] if row else None


def allowed(viewer, method, path, query):
    """True when this barnacle (or kid profile) may make this request."""
    if not viewer.restricted:
        return True
    for methods, pattern, kind in _COMPILED:
        if method not in methods:
            continue
        match = pattern.match(path)
        if not match:
            continue
        if kind == "media" and not viewer.can_see(media_library(int(match.group(1)))):
            return False
        if kind == "library" and not viewer.can_see(int(match.group(1))):
            return False
        for value in query.get("library_id", []):
            if not value.isdigit() or not viewer.can_see(int(value)):
                return False
        for value in query.get("media_id", []):
            if not value.isdigit() or not viewer.can_see(media_library(int(value))):
                return False
        return True
    return False
