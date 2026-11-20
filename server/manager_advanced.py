"""Expanded Radarr/Sonarr/Lidarr operations with strict endpoint allowlists and sanitized responses."""
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from .manager_control import _provider, _request, _positive_int, _text, _kind, ID_KEYS

router = APIRouter(prefix="/api/managers")

def _rows(data):
    rows = data.get("records", []) if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []

def _json_date(value):
    return _text(value, 40)

def _event(data, name):
    related = data.get("series") or data.get("movie") or data.get("artist") or {}
    if not isinstance(related, dict):
        related = {}
    return {
        "id": _positive_int(data.get("id")),
        "item_id": _positive_int(data.get(ID_KEYS[name])),
        "title": _text(data.get("title") or data.get("sourceTitle") or related.get("title") or
                       related.get("artistName")),
        "status": _text(data.get("status") or data.get("eventType"), 80),
        "date": _json_date(data.get("date")),
        "timeleft": _text(data.get("timeleft"), 70),
        "sizeleft": data.get("sizeleft"),
        "output_path": _text(data.get("outputPath"), 200),
        "message": _text(data.get("trackedDownloadStatus"), 100),
    }

def _episode(data, files=None):
    """An episode is downloaded if Sonarr links it to an imported media file."""
    file_id = _positive_int(data.get("episodeFileId"))
    embedded = data.get("episodeFile")
    embedded = embedded if isinstance(embedded, dict) else {}
    if file_id is None:
        file_id = _positive_int(embedded.get("id"))
    files = files or {}
    file_data = files.get(file_id) or embedded
    quality = file_data.get("quality") if isinstance(file_data, dict) else {}
    if isinstance(quality, dict):
        quality = quality.get("quality") or quality
    quality_name = _text(quality.get("name") if isinstance(quality, dict) else quality, 80)
    size = file_data.get("size") if isinstance(file_data, dict) else None
    size = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
    path = file_data.get("path") or file_data.get("relativePath") or ""
    filename = str(path).replace(chr(92), "/").rsplit("/", 1)[-1] if path else ""
    has_file = bool(data.get("hasFile")) or file_id is not None or bool(file_data)
    return {
        "id": _positive_int(data.get("id")),
        "title": _text(data.get("title"), 200),
        "season": data.get("seasonNumber"),
        "episode": data.get("episodeNumber"),
        "air_date": _json_date(data.get("airDateUtc") or data.get("airDate")),
        "monitored": bool(data.get("monitored")),
        "has_file": has_file,
        "file_id": file_id,
        "file_quality": quality_name,
        "file_size": size,
        "file_name": _text(filename, 220),
        "overview": _text(data.get("overview"), 1000),
        "absolute": data.get("absoluteEpisodeNumber"),
    }

def _release(data):
    quality = data.get("quality") or {}
    if isinstance(quality, dict):
        quality = quality.get("quality") or quality
    return {
        "guid": _text(data.get("guid"), 400),
        "indexer_id": _positive_int(data.get("indexerId")),
        "title": _text(data.get("title"), 250),
        "indexer": _text(data.get("indexer"), 100),
        "quality": _text(quality.get("name") if isinstance(quality, dict) else quality, 80),
        "size": data.get("size"),
        "age": data.get("age"),
        "protocol": _text(data.get("protocol"), 40),
        "approved": bool(data.get("approved", not bool(data.get("rejected")))),
        "rejections": [_text(x, 120) for x in (data.get("rejections") or [])[:4]],
    }

@router.get("/{name}/section/{section}")
def view_section(name: str, section: str, page: int = Query(1, ge=1, le=100)):
    setting = _provider(name)
    if section == "calendar":
        start = date.today() - timedelta(days=7)
        end = start + timedelta(days=70)
        raw = _request(name, setting, "calendar", query={
            "start": start.isoformat(), "end": end.isoformat(),
            "includeSeries": "true", "includeArtist": "true",
        })
        events = []
        for item in _rows(raw)[:300]:
            if not isinstance(item, dict):
                continue
            if name == "lidarr":
                artist = item.get("artist") if isinstance(item.get("artist"), dict) else {}
                events.append({
                    "item_id": _positive_int(item.get("artistId")),
                    "title": _text(artist.get("artistName") or item.get("title"), 180),
                    "subtitle": _text(item.get("title"), 180),
                    "date": _json_date(item.get("releaseDate")),
                    "monitored": bool(item.get("monitored")),
                })
                continue
            series = item.get("series") if isinstance(item.get("series"), dict) else {}
            events.append({
                "item_id": _positive_int(item.get("movieId" if name == "radarr" else "seriesId") or item.get("id")),
                "title": _text(series.get("title") if name == "sonarr" else item.get("title"), 180),
                "episode_title": _text(item.get("title"), 180) if name == "sonarr" else "",
                "season": item.get("seasonNumber") if name == "sonarr" else None,
                "episode": item.get("episodeNumber") if name == "sonarr" else None,
                "date": _json_date(item.get("airDateUtc") or item.get("airDate") or item.get("digitalRelease") or item.get("physicalRelease") or item.get("inCinemas")),
                "has_file": bool(item.get("hasFile")),
                "monitored": bool(item.get("monitored")),
            })
        events.sort(key=lambda row: row["date"])
        return {"section": section, "items": events}
    if section in ("missing", "cutoff"):
        raw = _request(name, setting, "wanted/" + section, query={
            "page": page, "pageSize": 100,
            "sortKey": {"sonarr": "airDateUtc", "lidarr": "releaseDate"}.get(name, "title"),
            "sortDirection": "descending", "includeSeries": "true", "includeArtist": "true",
        })
        events = []
        for item in _rows(raw)[:100]:
            if not isinstance(item, dict):
                continue
            if name == "lidarr":
                artist = item.get("artist") if isinstance(item.get("artist"), dict) else {}
                events.append({
                    "id": _positive_int(item.get("id")),
                    "item_id": _positive_int(item.get("artistId")),
                    "title": _text(artist.get("artistName"), 180),
                    "subtitle": _text(item.get("title"), 160),
                    "date": _json_date(item.get("releaseDate")),
                })
                continue
            series = item.get("series") if isinstance(item.get("series"), dict) else {}
            events.append({
                "id": _positive_int(item.get("id")),
                "item_id": _positive_int(item.get("movieId" if name == "radarr" else "seriesId") or item.get("id")),
                "title": _text(series.get("title") if name == "sonarr" else item.get("title"), 180),
                "subtitle": _text(item.get("title"), 160) if name == "sonarr" else "",
                "season": item.get("seasonNumber"),
                "episode": item.get("episodeNumber"),
                "date": _json_date(item.get("airDateUtc") or item.get("airDate") or item.get("digitalRelease")),
            })
        return {"section": section, "items": events, "page": page, "has_more": len(events) == 100}
    if section in ("queue", "history", "blocklist"):
        raw = _request(name, setting, section, query={
            "page": page, "pageSize": 100, "sortKey": "date" if section != "queue" else "timeleft",
            "sortDirection": "descending", "includeSeries": "true", "includeArtist": "true",
        })
        events = [_event(item, name) for item in _rows(raw)[:100] if isinstance(item, dict)]
        return {"section": section, "items": events, "page": page, "has_more": len(events) == 100}
    if section == "system":
        system = _request(name, setting, "system/status")
        health = _request(name, setting, "health")
        disks = _request(name, setting, "diskspace")
        clients = _request(name, setting, "downloadclient")
        indexers = _request(name, setting, "indexer")
        return {"section": section,
                "status": {k: system.get(k) for k in ("version", "branch", "osName", "appName", "isProduction", "isDebug", "runtimeVersion", "authentication") if k in system}
                if isinstance(system, dict) else {},
                "health": [{"type": _text(row.get("type")), "message": _text(row.get("message"), 250)}
                           for row in _rows(health) if isinstance(row, dict)],
                "diskspace": [{"path": _text(row.get("path"), 250), "free": row.get("freeSpace"),
                               "total": row.get("totalSpace")}
                              for row in _rows(disks) if isinstance(row, dict)],
                "clients": [{"name": _text(row.get("name")), "enabled": bool(row.get("enable", False)),
                             "implementation": _text(row.get("implementation"))}
                            for row in _rows(clients) if isinstance(row, dict)],
                "indexers": [{"name": _text(row.get("name")), "enabled": bool(row.get("enable", False)),
                              "implementation": _text(row.get("implementation"))}
                             for row in _rows(indexers) if isinstance(row, dict)]}
    raise HTTPException(404, "Unsupported manager section")

@router.get("/{name}/details/{item_id}")
def title_detail(name: str, item_id: int = Path(gt=0)):
    setting = _provider(name)
    data = _request(name, setting, _kind(name) + "/" + str(item_id))
    if not isinstance(data, dict) or _positive_int(data.get("id")) != item_id:
        raise HTTPException(404, "Title not found")
    fields = {
        "id": item_id, "title": _text(data.get("title") or data.get("artistName")), "overview": _text(data.get("overview"), 2700),
        "year": data.get("year"), "status": _text(data.get("status"), 65),
        "path": _text(data.get("path"), 320), "root_folder": _text(data.get("rootFolderPath"), 320),
        "monitored": bool(data.get("monitored")), "profile_id": _positive_int(data.get("qualityProfileId")),
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
        "runtime": data.get("runtime"), "size_on_disk": data.get("sizeOnDisk"),
        "has_file": bool(data.get("hasFile")),
        "series_type": _text(data.get("seriesType"), 40),
        "network": _text(data.get("network"), 120),
        "genres": [_text(x, 70) for x in (data.get("genres") or [])[:15]],
        "external_url": setting["url"],
    }
    if name == "sonarr":
        episodes = _request(name, setting, "episode", query={
            "seriesId": item_id, "includeEpisodeFile": "true",
        })
        episode_rows = [row for row in _rows(episodes) if isinstance(row, dict)]
        # Older Sonarr versions omit nested file details even with includeEpisodeFile.
        # Fetch the series' imported files once and join via episodeFileId.
        file_map = {}
        if any((row.get("hasFile") or _positive_int(row.get("episodeFileId")) or
                isinstance(row.get("episodeFile"), dict)) for row in episode_rows):
            try:
                episode_files = _request(name, setting, "episodefile", query={"seriesId": item_id})
                if isinstance(episode_files, list):
                    file_map = {_positive_int(row.get("id")): row for row in episode_files
                                if isinstance(row, dict) and _positive_int(row.get("id"))}
            except HTTPException:
                # File association is still available from the episode response.
                pass
        ep = [_episode(row, file_map) for row in episode_rows]
        ep.sort(key=lambda row: (row["season"] if isinstance(row["season"], int) else -1,
                                row["episode"] if isinstance(row["episode"], int) else -1))
        seasons = []
        for row in data.get("seasons", []) or []:
            if not isinstance(row, dict):
                continue
            number = row.get("seasonNumber")
            if not isinstance(number, int):
                continue
            stats = row.get("statistics") if isinstance(row.get("statistics"), dict) else {}
            seasons.append({"number": number, "monitored": bool(row.get("monitored")),
                            "episode_count": stats.get("episodeCount"),
                            "file_count": stats.get("episodeFileCount")})
        fields["episodes"] = ep[:2000]
        fields["seasons"] = sorted(seasons, key=lambda row: row["number"])
    elif name == "lidarr":
        fields["status"] = _text(data.get("status"), 65)
        fields["series_type"] = _text(data.get("artistType"), 40)
        stats = data.get("statistics") if isinstance(data.get("statistics"), dict) else {}
        fields["size_on_disk"] = stats.get("sizeOnDisk")
        albums = _request(name, setting, "album", query={"artistId": item_id})
        rows = []
        for row in _rows(albums)[:500]:
            if not isinstance(row, dict):
                continue
            st = row.get("statistics") if isinstance(row.get("statistics"), dict) else {}
            rows.append({
                "id": _positive_int(row.get("id")),
                "title": _text(row.get("title"), 200),
                "type": _text(row.get("albumType"), 40),
                "release_date": _json_date(row.get("releaseDate")),
                "monitored": bool(row.get("monitored")),
                "track_files": st.get("trackFileCount"),
                "tracks": st.get("totalTrackCount") or st.get("trackCount"),
            })
        rows.sort(key=lambda r: r["release_date"], reverse=True)
        fields["albums"] = rows
    else:
        moviefile = data.get("movieFile") if isinstance(data.get("movieFile"), dict) else {}
        fields["movie_file"] = {
            "path": _text(moviefile.get("path"), 320),
            "size": moviefile.get("size"),
            "quality": _text(((moviefile.get("quality") or {}).get("quality") or {}).get("name")
                             if isinstance(moviefile.get("quality"), dict) else "", 80),
        }
    return fields

class EpisodeBulkChange(BaseModel):
    action: str
    episode_ids: list[int] = Field(min_length=1, max_length=400)


@router.post("/sonarr/series/{series_id}/episodes/bulk")
def bulk_episodes(series_id: int = Path(gt=0), change: EpisodeBulkChange = None):
    """Change monitoring or search only verified episodes belonging to a Sonarr series."""
    if change is None or change.action not in ("monitor", "unmonitor", "search"):
        raise HTTPException(422, "Choose Monitor, Unmonitor or Search.")
    episode_ids = change.episode_ids
    if not episode_ids or len(set(episode_ids)) != len(episode_ids) or any(
        not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in episode_ids
    ):
        raise HTTPException(422, "Select unique valid episode IDs.")
    setting = _provider("sonarr")
    series = _request("sonarr", setting, "series/" + str(series_id))
    if not isinstance(series, dict) or _positive_int(series.get("id")) != series_id:
        raise HTTPException(404, "Series not found.")
    episodes = _request("sonarr", setting, "episode", query={"seriesId": series_id})
    if not isinstance(episodes, list):
        raise HTTPException(502, "Sonarr did not return episode information.")
    owned = {_positive_int(row.get("id")): row
             for row in episodes if isinstance(row, dict) and
             _positive_int(row.get("seriesId")) in (None, series_id)}
    if not set(episode_ids).issubset(owned):
        raise HTTPException(422, "One or more episodes do not belong to this series.")
    if change.action == "search":
        result = _request("sonarr", setting, "command", method="POST", payload={
            "name": "EpisodeSearch", "episodeIds": episode_ids,
        })
        if not isinstance(result, dict):
            raise HTTPException(502, "Sonarr did not confirm the episode search.")
        return {"queued": True, "action": "search", "count": len(episode_ids),
                "command_id": _positive_int(result.get("id"))}
    monitored = change.action == "monitor"
    # Sonarr v3/v5 support bulk monitoring via PUT /episode/monitor.
    _request("sonarr", setting, "episode/monitor", method="PUT",
             payload={"episodeIds": episode_ids, "monitored": monitored})
    verified = _request("sonarr", setting, "episode", query={"seriesId": series_id})
    if not isinstance(verified, list):
        raise HTTPException(502, "Sonarr did not confirm the monitoring change.")
    statuses = {_positive_int(row.get("id")): bool(row.get("monitored"))
                for row in verified if isinstance(row, dict)}
    updated = [item for item in episode_ids if statuses.get(item) is monitored]
    if len(updated) != len(episode_ids):
        raise HTTPException(502, "Sonarr did not confirm monitoring for all selected episodes. Refresh to review their status.")
    return {"action": change.action, "count": len(updated), "monitored": monitored}


class EpisodeChange(BaseModel):
    monitored: bool

@router.put("/{name}/episodes/{episode_id}")
def episode_monitor(name: str, episode_id: int = Path(gt=0), change: EpisodeChange = None):
    if name != "sonarr":
        raise HTTPException(404, "Episodes are only available in Sonarr")
    if change is None:
        raise HTTPException(422, "Choose a monitoring state")
    setting = _provider(name)
    resource = "episode/" + str(episode_id)
    data = _request(name, setting, resource)
    if not isinstance(data, dict) or _positive_int(data.get("id")) != episode_id:
        raise HTTPException(404, "Episode not found")
    data["monitored"] = change.monitored
    result = _request(name, setting, resource, method="PUT", payload=data)
    if not isinstance(result, dict) or _positive_int(result.get("id")) != episode_id:
        result = _request(name, setting, resource)
    return {"id": episode_id, "monitored": bool(result.get("monitored"))}

class SeasonChange(BaseModel):
    monitored: bool

@router.put("/{name}/series/{series_id}/seasons/{season}")
def season_monitor(name: str, series_id: int = Path(gt=0), season: int = Path(ge=0),
                   change: SeasonChange = None):
    if name != "sonarr":
        raise HTTPException(404, "Seasons are only available in Sonarr")
    if change is None:
        raise HTTPException(422, "Choose a monitoring state")
    setting = _provider(name)
    resource = "series/" + str(series_id)
    data = _request(name, setting, resource)
    if not isinstance(data, dict) or _positive_int(data.get("id")) != series_id:
        raise HTTPException(404, "Series not found")
    matched = [row for row in data.get("seasons", []) if isinstance(row, dict) and row.get("seasonNumber") == season]
    if len(matched) != 1:
        raise HTTPException(404, "Season not found")
    matched[0]["monitored"] = change.monitored
    result = _request(name, setting, resource, method="PUT", payload=data)
    if not isinstance(result, dict) or _positive_int(result.get("id")) != series_id:
        result = _request(name, setting, resource)
    seasons = result.get("seasons", []) if isinstance(result, dict) else []
    found = [x for x in seasons if isinstance(x, dict) and x.get("seasonNumber") == season]
    if not found:
        raise HTTPException(502, "Sonarr did not confirm season monitoring")
    return {"series_id": series_id, "season": season, "monitored": bool(found[0].get("monitored"))}

class ExtendedCommand(BaseModel):
    action: str
    series_id: int | None = Field(default=None, gt=0)
    season: int | None = Field(default=None, ge=0)
    episode_id: int | None = Field(default=None, gt=0)

@router.post("/{name}/extended-command")
def advanced_command(name: str, change: ExtendedCommand):
    if name != "sonarr":
        raise HTTPException(404, "This action is available only for Sonarr")
    setting = _provider(name)
    if change.action == "episode" and change.episode_id:
        data = _request(name, setting, "episode/" + str(change.episode_id))
        if not isinstance(data, dict) or _positive_int(data.get("id")) != change.episode_id:
            raise HTTPException(404, "Episode not found")
        payload = {"name": "EpisodeSearch", "episodeIds": [change.episode_id]}
    elif change.action == "season" and change.series_id and change.season is not None:
        series = _request(name, setting, "series/" + str(change.series_id))
        if not isinstance(series, dict) or not any(
            isinstance(x, dict) and x.get("seasonNumber") == change.season
            for x in (series.get("seasons") or [])
        ):
            raise HTTPException(404, "Season not found")
        payload = {"name": "SeasonSearch", "seriesId": change.series_id, "seasonNumber": change.season}
    else:
        raise HTTPException(422, "Choose a valid episode or season search")
    result = _request(name, setting, "command", method="POST", payload=payload)
    return {"queued": True, "command_id": _positive_int(result.get("id")),
            "name": _text(result.get("name") or payload["name"])}

@router.get("/{name}/releases")
def manual_releases(name: str, item_id: int = Query(gt=0), episode_id: int | None = Query(None, gt=0)):
    setting = _provider(name)
    if name == "radarr":
        movie = _request(name, setting, "movie/" + str(item_id))
        if not isinstance(movie, dict) or _positive_int(movie.get("id")) != item_id:
            raise HTTPException(404, "Movie not found")
        query = {"movieId": item_id}
    else:
        if episode_id is None:
            raise HTTPException(422, "Select an episode for manual search")
        episode = _request(name, setting, "episode/" + str(episode_id))
        if not isinstance(episode, dict) or _positive_int(episode.get("seriesId")) != item_id:
            raise HTTPException(422, "Episode does not belong to that series")
        query = {"episodeId": episode_id}
    raw = _request(name, setting, "release", query=query)
    return {"items": [_release(x) for x in _rows(raw)[:100]
                      if isinstance(x, dict) and _positive_int(x.get("indexerId")) and x.get("guid")]}

class GrabInput(BaseModel):
    item_id: int = Field(gt=0)
    episode_id: int | None = Field(default=None, gt=0)
    guid: str = Field(min_length=1, max_length=400)
    indexer_id: int = Field(gt=0)

@router.post("/{name}/releases/grab")
def grab_release(name: str, choice: GrabInput):
    setting = _provider(name)
    # Validate ownership and re-query server-side: never trust release data from the browser.
    if name == "radarr":
        item = _request(name, setting, "movie/" + str(choice.item_id))
        if not isinstance(item, dict) or _positive_int(item.get("id")) != choice.item_id:
            raise HTTPException(404, "Movie not found")
        query = {"movieId": choice.item_id}
    else:
        if not choice.episode_id:
            raise HTTPException(422, "Select an episode")
        episode = _request(name, setting, "episode/" + str(choice.episode_id))
        if not isinstance(episode, dict) or _positive_int(episode.get("seriesId")) != choice.item_id:
            raise HTTPException(422, "Episode does not belong to this series")
        query = {"episodeId": choice.episode_id}
    candidates = _request(name, setting, "release", query=query)
    matched = [r for r in _rows(candidates) if isinstance(r, dict) and
               r.get("guid") == choice.guid and _positive_int(r.get("indexerId")) == choice.indexer_id]
    if len(matched) != 1:
        raise HTTPException(409, "Release is no longer available. Search again.")
    result = _request(name, setting, "release", method="POST", payload=matched[0])
    return {"submitted": True, "title": _text(matched[0].get("title")),
            "result": _text(result.get("title") if isinstance(result, dict) else "", 200)}

class QueueRemoveInput(BaseModel):
    remove_from_client: bool = False
    blocklist: bool = False

@router.post("/{name}/queue/{queue_id}/remove")
def remove_queue_entry(name: str, queue_id: int = Path(gt=0), change: QueueRemoveInput = None):
    setting = _provider(name)
    if change is None:
        raise HTTPException(422, "Confirm queue removal options")
    # Confirm that this queue item belongs to this manager before removing it.
    items = _request(name, setting, "queue", query={"page": 1, "pageSize": 1000})
    if queue_id not in {_positive_int(row.get("id")) for row in _rows(items) if isinstance(row, dict)}:
        raise HTTPException(404, "Queue item not found in the first 1,000 entries")
    _request(name, setting, "queue/" + str(queue_id), method="DELETE", query={
        "removeFromClient": str(change.remove_from_client).lower(),
        "blocklist": str(change.blocklist).lower(),
    })
    return {"removed": True}

class LibraryRemoveInput(BaseModel):
    preserve_files: bool = True

@router.post("/{name}/items/{item_id}/remove")
def remove_title(name: str, item_id: int = Path(gt=0), change: LibraryRemoveInput = None):
    setting = _provider(name)
    if change is None or not change.preserve_files:
        raise HTTPException(422, "Only removal with preserved files is supported.")
    resource = _kind(name) + "/" + str(item_id)
    record = _request(name, setting, resource)
    if not isinstance(record, dict) or _positive_int(record.get("id")) != item_id:
        raise HTTPException(404, "Title not found")
    _request(name, setting, resource, method="DELETE",
             query={"deleteFiles": "false"})
    return {"removed": True, "files_preserved": True}
