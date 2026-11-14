from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from server.library import router
from server.catalog import catalog, start_background_scans
from server.connections import router as connections_router

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

@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.4.0"}

@app.get("/api/catalog")
def get_catalog(kind: str | None = None, search: str = Query("", max_length=150)):
    if kind not in (None, "movies", "tv"):
        return {"total": 0, "items": []}
    return catalog(kind, search)

@app.get("/")
def home():
    return FileResponse(Path(__file__).with_name("catalog.html"), media_type="text/html")

@app.get("/settings/libraries")
def library_settings():
    return FileResponse(Path(__file__).with_name("index.html"), media_type="text/html")
