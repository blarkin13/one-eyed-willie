from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from server.library import router
from server.catalog import catalog, start_background_scans
from server.connections import router as connections_router
from server.remote_config import router as remote_config_router
from server.home import router as home_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop, thread = start_background_scans()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)

app = FastAPI(title="One-Eyed Willie", version="0.4.0", lifespan=lifespan)
app.include_router(router)
app.include_router(connections_router)
app.include_router(remote_config_router)
app.include_router(home_router)

@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.4.0"}

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

@app.get("/movies")
@app.get("/tv")
def browse():
    return FileResponse(Path(__file__).with_name("catalog.html"), media_type="text/html")

@app.get("/assets/ui.css")
def ui_stylesheet():
    return FileResponse(Path(__file__).with_name("ui.css"), media_type="text/css")

@app.get("/assets/shell.js")
def ui_shell():
    return FileResponse(Path(__file__).with_name("shell.js"), media_type="text/javascript")

@app.get("/settings/libraries")
def library_settings():
    return FileResponse(Path(__file__).with_name("index.html"), media_type="text/html")

@app.get("/settings/remote")
def remote_settings_page():
    return FileResponse(Path(__file__).with_name("remote_settings.html"), media_type="text/html")
