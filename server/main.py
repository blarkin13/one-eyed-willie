from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from server.library import router

app = FastAPI(title="One-Eyed Willie", version="0.2.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.2.0"}


@app.get("/")
def home():
    return FileResponse(Path(__file__).with_name("index.html"), media_type="text/html")
