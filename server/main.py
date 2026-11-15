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
from server.subtitles import router as subtitles_router
from server.hls import router as hls_router, init_cache, cleanup_loop
from server.artwork import router as artwork_router
from server.movies import router as movies_router
from server.arr import router as arr_router
from server.tv import router as tv_router
from server.metadata import router as metadata_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_cache()
    cleanup_stop = threading.Event()
    cleanup_thread = threading.Thread(target=cleanup_loop,args=(cleanup_stop,),daemon=True)
    cleanup_thread.start()
    stop, thread = start_background_scans()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)
        cleanup_stop.set()
        cleanup_thread.join(timeout=3)

app = FastAPI(title="One-Eyed Willie", version="0.14.1", lifespan=lifespan)
app.include_router(router)
app.include_router(connections_router)
app.include_router(remote_config_router)
app.include_router(home_router)
app.include_router(playback_router)
app.include_router(subtitles_router)
app.include_router(hls_router)
app.include_router(artwork_router)
app.include_router(movies_router)
app.include_router(arr_router)
app.include_router(tv_router)
app.include_router(metadata_router)

@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.14.1"}

@app.get("/api/catalog/all")
def get_entire_catalog(
    kind: str | None = None,
    search: str = Query("", max_length=150),
    sort: str = Query("title"),
):
    if kind not in ("movies", "tv"):
        return {"total": 0, "items": []}
    if sort not in ("title", "recent", "year"):
        sort = "title"
    # The catalog is indexed locally and returned once; artwork loads lazily.
    return catalog(kind, search, limit=1_000_000, sort=sort)


@app.get("/api/catalog")
def get_catalog(
    kind: str | None = None,
    search: str = Query("", max_length=150),
    sort: str = Query("title"),
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=100),
):
    if kind not in (None, "movies", "tv"):
        return {"total": 0, "items": []}
    if sort not in ("title", "recent", "year"):
        sort = "title"
    return catalog(kind, search, limit=limit, offset=offset, sort=sort)

@app.get("/")
def home():
    return FileResponse(Path(__file__).with_name("dashboard.html"), media_type="text/html")

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

@app.get("/assets/logo.png")
def brand_logo_png():
    return FileResponse(Path(__file__).with_name("logo.png"), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/favicon.png")
def favicon_png():
    return FileResponse(Path(__file__).with_name("favicon.png"), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/logo.svg")
def brand_logo():
    return FileResponse(Path(__file__).with_name("logo.svg"), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/assets/shell.js")
def ui_shell():
    return FileResponse(Path(__file__).with_name("shell.js"), media_type="text/javascript")

@app.get("/assets/player.js")
def player_script():
    return FileResponse(Path(__file__).with_name("player.js"), media_type="text/javascript")


@app.get("/watch/{media_id}")
def watch_page(media_id: int):
    return FileResponse(Path(__file__).with_name("watch.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


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

@app.get("/settings/connections")
def arr_connections_page():
    return FileResponse(Path(__file__).with_name("arr_connections.html"), media_type="text/html")
