"""Explicitly confirmed Radarr/Sonarr deletion actions for local media.

One-Eyed Willie's /media mount is intentionally read-only. These actions do
not unlink local files or change Docker mounts. Manager operations happen only
when the selected title is uniquely matched to a connected manager.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import arr, movies, tv
from .library import db

router = APIRouter(prefix="/api/media/actions", tags=["media actions"])


class DeleteSelection(BaseModel):
    kind: str
    library_id: int = Field(gt=0)
    key: str = Field(min_length=1, max_length=500)
    scope: str
    media_id: int | None = Field(default=None, gt=0)
    season_number: int | None = Field(default=None, ge=0, le=999)
    manager_id: int = Field(gt=0)
    confirm_title: str = Field(min_length=1, max_length=300)
    delete_files: bool = False
    remove_from_manager: bool = False


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _selection(kind, library_id, key, scope, media_id=None, season_number=None):
    if kind not in ("movies", "tv"):
        raise HTTPException(422, "Unsupported media type")
    if kind == "movies":
        if scope != "movie":
            raise HTTPException(422, "Movies can only be deleted individually")
        parsed, _, _ = movies._movie_path(library_id, key)
        title, year = parsed["title"], parsed.get("year")
        name = title
        manager = "radarr"
    else:
        if scope not in ("episode", "season", "series"):
            raise HTTPException(422, "Select episode, season or series")
        show = tv.local_show(library_id, key)
        title, year = show["title"], show.get("year")
        manager = "sonarr"
        if scope == "episode":
            episode = next((ep for ep in show["episodes"] if ep["id"] == media_id), None)
            if not episode:
                raise HTTPException(404, "Episode not found in the selected series")
            season_number = episode["season"]
            if season_number is None or episode["episode"] is None:
                raise HTTPException(422, "The episode has no recognized season and episode number")
            name = f"{title} S{season_number:02}E{episode['episode']:02}"
        elif scope == "season":
            if season_number is None or not any(ep["season"] == season_number for ep in show["episodes"]):
                raise HTTPException(404, "Season not found in the local library")
            name = f"{title} Season {season_number}"
        else:
            name = title
    return {"kind": kind, "scope": scope, "title": title, "name": name,
            "year": year, "provider": manager, "season_number": season_number,
            "media_id": media_id}


def _manager_match(meta):
    name = meta["provider"]
    settings = arr._settings(name)
    if not settings:
        return None
    records = arr._get(name, "movie" if name == "radarr" else "series")
    if not isinstance(records, list):
        raise HTTPException(502, "Media manager did not return its library")
    # Never delete by a fuzzy title match or a client-supplied manager id.
    title = _normalize(meta["title"])
    matches = [record for record in records
               if isinstance(record, dict)
               and _normalize(record.get("title")) == title
               and isinstance(record.get("id"), int)
               and record["id"] > 0]
    if meta["year"]:
        matches = [record for record in matches
                   if str(record.get("year") or "") == str(meta["year"])]
    if len(matches) > 1:
        raise HTTPException(409, "Several manager titles match. Delete directly in the manager.")
    return matches[0] if matches else None


def _delete_manager(name, resource, record_id, query=None):
    settings = arr._settings(name)
    if not settings:
        raise HTTPException(409, f"Connect {name.title()} in Settings → Connections")
    # The resource is a hardcoded choice, never a client-supplied URL/path.
    if (name, resource) not in {
        ("radarr", "movie"), ("sonarr", "series"), ("sonarr", "episodefile")
    } or not isinstance(record_id, int) or record_id <= 0:
        raise HTTPException(422, "Invalid manager deletion target")
    endpoint = f"/api/{arr._version(name, settings)}/{resource}/{record_id}"
    url = settings["url"] + endpoint
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url, method="DELETE",
        headers={"X-Api-Key": settings["api_key"], "Accept": "application/json",
                 "User-Agent": "OneEyedWillie/0.9"}
    )
    try:
        with urllib.request.build_opener(arr.NoRedirect()).open(request, timeout=15) as response:
            if response.status not in (200, 202, 204):
                raise HTTPException(502, "Media manager did not confirm deletion")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise HTTPException(409, "The selected manager item no longer exists") from error
        raise HTTPException(502, "Media manager could not complete deletion") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HTTPException(502, "Media manager is unreachable; check its deletion status") from error


def _episode_file_ids(series_id, season_number, episode_number=None):
    episodes = arr._get("sonarr", "episode", {"seriesId": series_id})
    if not isinstance(episodes, list):
        raise HTTPException(502, "Sonarr did not return episode information")
    matched = [ep for ep in episodes if isinstance(ep, dict)
               and ep.get("seasonNumber") == season_number
               and (episode_number is None or ep.get("episodeNumber") == episode_number)]
    if episode_number is not None and len(matched) != 1:
        raise HTTPException(409, "Sonarr cannot uniquely identify this episode")
    ids = {ep["episodeFileId"] for ep in matched
           if isinstance(ep.get("episodeFileId"), int) and ep["episodeFileId"] > 0}
    return sorted(ids)


@router.get("")
def media_action_preview(kind: str, library_id: int = Query(ge=1),
                         key: str = Query(min_length=1, max_length=500),
                         scope: str = "series",
                         media_id: int | None = Query(default=None, ge=1),
                         season_number: int | None = Query(default=None, ge=0, le=999)):
    info = _selection(kind, library_id, key, scope, media_id, season_number)
    connected = bool(arr._settings(info["provider"]))
    match = _manager_match(info) if connected else None
    return {**info, "connected": connected, "manager_id": match["id"] if match else None,
            "manager_title": match.get("title") if match else None,
            "media_files_writable": False,
            "explanation": ("Files are managed through Radarr or Sonarr; "
                            "One-Eyed Willie's media mount is read-only.")}


@router.post("/delete")
def delete_media(selection: DeleteSelection):
    info = _selection(selection.kind, selection.library_id, selection.key,
                      selection.scope, selection.media_id, selection.season_number)
    if selection.confirm_title != info["name"]:
        raise HTTPException(422, "Confirm the exact title shown in the dialog")
    match = _manager_match(info)
    if not match or match["id"] != selection.manager_id:
        raise HTTPException(409, "Media manager match changed; reopen the confirmation dialog")
    if selection.scope in ("episode", "season"):
        if selection.remove_from_manager or not selection.delete_files:
            raise HTTPException(422, "For individual episodes and seasons, select Sonarr file deletion")
        number = None
        if selection.scope == "episode":
            show = tv.local_show(selection.library_id, selection.key)
            chosen = next((ep for ep in show["episodes"] if ep["id"] == selection.media_id), None)
            if not chosen:
                raise HTTPException(404, "Episode not found")
            number = chosen["episode"]
        ids = _episode_file_ids(match["id"], info["season_number"], number)
        if not ids:
            raise HTTPException(409, "Sonarr has no downloaded file for this selection")
        deleted = 0
        for file_id in ids:
            try:
                _delete_manager("sonarr", "episodefile", file_id)
                deleted += 1
            except HTTPException as error:
                raise HTTPException(502, f"Sonarr deleted {deleted} of {len(ids)} files. "
                                    "Check Sonarr before retrying.") from error
        return {"deleted": True, "provider": "sonarr", "files_requested": deleted,
                "manager_record_removed": False,
                "rescan_required": True}
    if not selection.delete_files and not selection.remove_from_manager:
        raise HTTPException(422, "Choose whether to remove the manager entry or delete its files")
    if selection.delete_files and not selection.remove_from_manager:
        # Keep management entry; delete only files through file endpoints.
        if selection.kind == "movies":
            movie_file = match.get("movieFile") or {}
            file_id = movie_file.get("id") or match.get("movieFileId")
            if not isinstance(file_id, int) or file_id <= 0:
                raise HTTPException(409, "Radarr has no downloaded file for this movie")
            _delete_manager("radarr", "moviefile", file_id)
            return {"deleted": True, "provider": "radarr", "files_requested": 1,
                    "manager_record_removed": False, "rescan_required": True}
        ids = sorted({ep for ep in _episode_file_ids(match["id"], 0)})
        # Whole-series files should be delegated to Sonarr's series delete,
        # which can safely handle all series seasons together. Refuse this
        # combination instead of quietly removing the Sonarr series record.
        raise HTTPException(422, "To delete all series files, also select Remove from Sonarr")
    _delete_manager(info["provider"], "movie" if info["provider"] == "radarr" else "series",
                    match["id"], {"deleteFiles": str(selection.delete_files).lower(),
                                  **({"addImportExclusion": "false"}
                                     if info["provider"] == "radarr" else {})})
    return {"deleted": True, "provider": info["provider"],
            "files_requested": 1 if selection.delete_files else 0,
            "manager_record_removed": True, "rescan_required": bool(selection.delete_files)}
