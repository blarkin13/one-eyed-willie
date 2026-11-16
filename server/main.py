from contextlib import asynccontextmanager
import threading
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from server.library import router
from server.catalog import catalog, start_background_scans
from server.connections import router as connections_router
from server.remote_config import router as remote_config_router
from server.home import router as home_router
from server.playback import router as playback_router
from server.playback_settings import router as playback_settings_router
from server.sidebar_settings import router as sidebar_settings_router
from server.plex_import import router as plex_router
from server.manager_control import router as manager_router
from server.manager_advanced import router as manager_advanced_router
from server.sabnzbd import router as sabnzbd_router
from server.subtitles import router as subtitles_router
from server.subtitle_provider import router as subtitle_provider_router
from server.hls import router as hls_router, init_cache, cleanup_loop
from server.media_probe import warm_media_profiles
from server.hardware import hardware_supported
from server.artwork import router as artwork_router
from server.movies import router as movies_router
from server.arr import router as arr_router
from server.tv import router as tv_router
from server.metadata import router as metadata_router
from server.people import router as people_router
from server.maintenance import router as maintenance_router, maintenance_loop
from server.poster_index import poster_loop
from server.catalog_metadata import router as catalog_metadata_router, start_refresh as start_catalog_metadata_refresh

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_cache()
    cleanup_stop = threading.Event()
    cleanup_thread = threading.Thread(target=cleanup_loop,args=(cleanup_stop,),daemon=True)
    cleanup_thread.start()
    maintenance_stop = threading.Event()
    maintenance_thread = threading.Thread(target=maintenance_loop, args=(maintenance_stop,), daemon=True, name='maintenance-scheduler')
    maintenance_thread.start()
    stop, thread = start_background_scans()
    probe_stop = threading.Event()
    probe_thread = threading.Thread(target=warm_media_profiles, args=(probe_stop,), daemon=True)
    probe_thread.start()
    threading.Thread(target=hardware_supported, daemon=True,
                     name="transcoder-hardware-preflight").start()
    posters_stop = threading.Event()
    poster_thread = threading.Thread(target=poster_loop, args=(posters_stop,), daemon=True, name='poster-prefetch')
    poster_thread.start()
    try:
        yield
    finally:
        posters_stop.set()
        posters_thread = poster_thread
        posters_thread.join(timeout=3)
        probe_stop.set()
        probe_thread.join(timeout=3)
        stop.set()
        thread.join(timeout=5)
        maintenance_stop.set()
        maintenance_thread.join(timeout=3)
        cleanup_stop.set()
        cleanup_thread.join(timeout=3)

app = FastAPI(title="One-Eyed Willie", version="0.14.2", lifespan=lifespan)
app.include_router(router)
app.include_router(connections_router)
app.include_router(remote_config_router)
app.include_router(home_router)
app.include_router(playback_router)
app.include_router(playback_settings_router)
app.include_router(sidebar_settings_router)
app.include_router(plex_router)
app.include_router(manager_router)
app.include_router(manager_advanced_router)
app.include_router(sabnzbd_router)
app.include_router(subtitle_provider_router)
app.include_router(subtitles_router)
app.include_router(hls_router)
app.include_router(artwork_router)
app.include_router(movies_router)
app.include_router(arr_router)
app.include_router(tv_router)
app.include_router(metadata_router)
app.include_router(people_router)
app.include_router(maintenance_router)
app.include_router(catalog_metadata_router)

@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.14.2"}

@app.get("/api/catalog/all")
def get_entire_catalog(
    kind: str | None = None,
    search: str = Query("", max_length=150),
    sort: str = Query("title"),
    library_id: int | None = Query(None, ge=1),
    genre: str = Query("", max_length=60),
):
    if kind not in ("movies", "tv"):
        return {"total": 0, "items": []}
    if sort not in ("title", "recent", "added", "year", "length", "rating"):
        sort = "title"
    # Refresh metadata independently of poster generation; never block browsing.
    start_catalog_metadata_refresh()
    return catalog(kind, search, limit=1_000_000, sort=sort, library_id=library_id, genre=genre)


@app.get("/api/catalog")
def get_catalog(
    kind: str | None = None,
    search: str = Query("", max_length=150),
    sort: str = Query("title"),
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=100),
    library_id: int | None = Query(None, ge=1),
    genre: str = Query("", max_length=60),
):
    if kind not in (None, "movies", "tv"):
        return {"total": 0, "items": []}
    if sort not in ("title", "recent", "added", "year", "length", "rating"):
        sort = "title"
    start_catalog_metadata_refresh()
    return catalog(kind, search, limit=limit, offset=offset, sort=sort, library_id=library_id, genre=genre)

@app.get("/")
def home():
    return FileResponse(Path(__file__).with_name("dashboard.html"), media_type="text/html")

@app.get("/person")
def person_page():
    return FileResponse(Path(__file__).with_name("person.html"), media_type="text/html")

@app.get("/credit")
def credit_title_page():
    return FileResponse(Path(__file__).with_name("credit_detail.html"), media_type="text/html")


@app.get("/movie")
def movie_page():
    return FileResponse(Path(__file__).with_name("movie_detail.html"), media_type="text/html")


@app.get("/movies")
@app.get("/tv")
def browse():
    return FileResponse(Path(__file__).with_name("catalog.html"), media_type="text/html")

@app.get("/assets/ui.css")
def ui_stylesheet():
    return FileResponse(Path(__file__).with_name("ui.css"), media_type="text/css")

@app.get("/assets/ship-logo.png")
def ship_logo_png():
    return FileResponse(Path(__file__).with_name("ship-logo.png"), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/poster-placeholder.jpg")
def poster_placeholder():
    return FileResponse(Path(__file__).with_name("poster-placeholder.jpg"), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/logo.png")
def brand_logo_png():
    return FileResponse(Path(__file__).with_name("logo.png"), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/favicon.ico")
@app.get("/favicon.png")
@app.get("/assets/favicon.png")
def favicon_png():
    return FileResponse(Path(__file__).with_name("favicon.png"), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})


@app.get("/assets/logo.svg")
def brand_logo():
    return FileResponse(Path(__file__).with_name("logo.svg"), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/shell.js")
def ui_shell():
    return FileResponse(Path(__file__).with_name("shell.js"), media_type="text/javascript")

@app.get("/assets/player.js")
def player_script():
    return FileResponse(Path(__file__).with_name("player.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"})


@app.get("/watch/{media_id}")
def watch_page(media_id: int):
    return FileResponse(Path(__file__).with_name("watch.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings")
def settings_home_page():
    return FileResponse(Path(__file__).with_name("settings_hub.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings/general")
def general_settings_page():
    return FileResponse(Path(__file__).with_name("general_settings.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings/playback")
def playback_settings_page():
    return FileResponse(Path(__file__).with_name("playback_settings.html"), media_type="text/html")


@app.get("/settings/libraries")
def library_settings():
    return FileResponse(Path(__file__).with_name("index.html"), media_type="text/html")

@app.get("/settings/remote")
def remote_settings_page():
    return FileResponse(Path(__file__).with_name("remote_settings.html"), media_type="text/html")

@app.get("/tv/show")
@app.get("/tv/season")
@app.get("/tv/episode")
def tv_details_page():
    return FileResponse(Path(__file__).with_name("tv_detail.html"), media_type="text/html")

@app.get("/settings/metadata")
def metadata_settings_page():
    return FileResponse(Path(__file__).with_name("metadata_settings.html"), media_type="text/html")

@app.get("/explore")
def explore_more_page():
    return FileResponse(Path(__file__).with_name("explore.html"), media_type="text/html")

@app.get("/services")
def download_services_page():
    return FileResponse(Path(__file__).with_name("services.html"), media_type="text/html")


@app.get("/radarr")
@app.get("/sonarr")
def manager_dashboard_page():
    return FileResponse(Path(__file__).with_name("manager_dashboard.html"), media_type="text/html")


@app.get("/sonarr/series/{series_id}")
def sonarr_series_page(series_id: int):
    if series_id <= 0:
        from fastapi import HTTPException
        raise HTTPException(404, "Series not found")
    return FileResponse(Path(__file__).with_name("sonarr_series.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/sabnzbd")
def sabnzbd_dashboard_page():
    return FileResponse(Path(__file__).with_name("sab_dashboard.html"), media_type="text/html")


@app.get("/settings/connections")
def arr_connections_page():
    return FileResponse(Path(__file__).with_name("arr_connections.html"), media_type="text/html")


@app.get("/settings/maintenance")
def maintenance_settings_page():
    return FileResponse(Path(__file__).with_name("maintenance_settings.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})
