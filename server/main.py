from contextlib import asynccontextmanager
import threading
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from server.library import router, db
from server.catalog import catalog, start_background_scans
from server.compression import compressed_json
from server.connections import router as connections_router
from server.remote_config import router as remote_config_router
from server.yarr_pairing import router as yarr_pairing_router
from server.home import router as home_router
from server.media_actions import router as media_actions_router
from server.playback import router as playback_router
from server.playback_settings import router as playback_settings_router
from server.subtitle_settings import router as subtitle_settings_router
from server.ambient_settings import router as ambient_settings_router
from server.theme_music import router as theme_music_router
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
from server.catalog_metadata import (router as catalog_metadata_router,
                                     start_refresh as start_catalog_metadata_refresh,
                                     automatic_refresh_loop as catalog_metadata_refresh_loop)

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
    metadata_stop = threading.Event()
    metadata_thread = threading.Thread(
        target=catalog_metadata_refresh_loop, args=(metadata_stop,),
        daemon=True, name="catalog-metadata-background")
    metadata_thread.start()
    try:
        yield
    finally:
        metadata_stop.set()
        metadata_thread.join(timeout=3)
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
app.include_router(yarr_pairing_router)
app.include_router(home_router)
app.include_router(media_actions_router)
app.include_router(playback_router)
app.include_router(playback_settings_router)
app.include_router(subtitle_settings_router)
app.include_router(ambient_settings_router)
app.include_router(theme_music_router)
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

@app.get("/api/catalog/revision")
def catalog_revision():
    """Lightweight change signal for open library and home screens."""
    with db() as conn:
        revision = conn.execute(
            "SELECT revision FROM catalog_state WHERE id=1"
        ).fetchone()[0]
    return {"revision": revision}


@app.get("/api/catalog/all")
def get_entire_catalog(
    request: Request,
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
    # The full list is ~1 MB of JSON for a few thousand titles and the Movies
    # page cannot draw its first row until it has been downloaded and parsed.
    return compressed_json(request, catalog(
        kind, search, limit=1_000_000, sort=sort, library_id=library_id, genre=genre))


@app.get("/api/catalog")
def get_catalog(
    request: Request,
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
    return compressed_json(request, catalog(
        kind, search, limit=limit, offset=offset, sort=sort, library_id=library_id, genre=genre))

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

# The Google TV WebView needs sidebar visibility established BEFORE the first
# paint, rather than in a script injected after page load. Only requests from
# our native app get this final CSS override; browsers keep normal navigation.
TV_RAIL_CSS = """
/* TV-only first paint: no navy canvas and no skull watermark while artwork loads. */
:root,html,body,
body[data-page="home"],body[data-page="movies"],
body[data-page="tv"],body[data-page="explore"] {
  background:#000!important;
}
.willie-hover-backdrop {background:#000!important}
#items::before,.shelf-track::before,.explore-grid::before,
.movie-grid::before,.tv-grid::before {content:none!important;display:none!important}
/* TV rail: hidden until the remote deliberately moves focus into navigation. */
body .sidebar,body .sidebar:hover,body .sidebar:focus-within {
  transform:translateX(-120%)!important;
  pointer-events:none!important;
}
body.oew-tv-rail-open .sidebar,
body.oew-tv-rail-open .sidebar:hover,
body.oew-tv-rail-open .sidebar:focus-within {
  transform:translateX(0)!important;
  pointer-events:auto!important;
}
body .workspace {margin-left:0!important}
/* TV-only first-paint sizes. Include in CSS response so the Home shelves
   never flash at their larger desktop size before WebView JS injection. */
body[data-page="home"] .shelf-track {
  grid-auto-columns:clamp(87px,10.8vw,130.8px)!important;
  grid-template-rows:max-content!important;
  grid-auto-rows:0!important;
  align-items:start!important;
  align-content:start!important;
  gap:14px!important;
  padding:11px 11px 9px!important;
  width:calc(100% + 22px)!important;
  margin:0 -11px!important;
  overflow-y:hidden!important;
  min-height:0!important;
  scroll-padding-inline:11px!important;
  scroll-snap-type:none!important;
}
body[data-page="home"] .shelf {
  margin-top:13px!important;min-height:0!important;
}
body[data-page="home"] .shelf:first-of-type {margin-top:0!important}
body[data-page="home"] .shelf .section-heading {margin-bottom:5px!important}
body[data-page="home"] .shelf-track .tile {min-height:0!important;align-self:start!important}
body[data-page="home"] .shelf-track .tile h3 {
  margin:5px 0 2px!important;line-height:1.17!important;
}
body[data-page="home"] .workspace>.content,
body[data-page="movies"] .workspace>.content,
body[data-page="tv"] .workspace>.content {
  max-width:none!important;
  padding-left:clamp(36px,5vw,95px)!important;
  padding-right:clamp(36px,5vw,95px)!important;
}
body:is([data-page="movies"],[data-page="tv"]) #items {
  grid-template-columns:repeat(5,minmax(0,1fr))!important;
  gap:22px 20px!important;
}
body:is([data-page="movies"],[data-page="tv"]) .library-head {
  padding:7px 7px 4px!important;gap:4px!important;margin-bottom:5px!important;
}
body:is([data-page="movies"],[data-page="tv"]) .library-trivia {
  gap:1px!important;padding-top:0!important;
}
body:is([data-page="movies"],[data-page="tv"]) .trivia-question {
  min-height:1.45em!important;line-height:1.2!important;
}
body:is([data-page="movies"],[data-page="tv"]) .trivia-answer {
  min-height:1.4em!important;
}
body:is([data-page="movies"],[data-page="tv"]) .library-head + .section-heading {
  margin-bottom:5px!important;
}
"""

@app.get("/assets/ui.css")
def ui_stylesheet(request: Request):
    if "OneEyedWillieTV/1" not in request.headers.get("user-agent", ""):
        return FileResponse(Path(__file__).with_name("ui.css"), media_type="text/css",
                            headers={"Vary": "User-Agent"})
    stylesheet = Path(__file__).with_name("ui.css").read_text(encoding="utf-8")
    return Response(stylesheet + "\n" + TV_RAIL_CSS, media_type="text/css",
                    headers={"Cache-Control": "no-store", "Vary": "User-Agent"})

@app.get("/assets/brand/{brand}.svg")
def integration_brand_svg(brand: str):
    # Serve only the locally bundled official integration logos.
    if brand not in ("radarr", "sonarr", "sabnzbd"):
        from fastapi import HTTPException
        raise HTTPException(404, "Unknown integration")
    return FileResponse(
        Path(__file__).with_name(f"{brand}-official.svg"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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


@app.get("/assets/sidebar-icon-{name}.png")
def sidebar_default_icon(name: str):
    from fastapi import HTTPException
    from server.sidebar_settings import sidebar_icon_bytes
    icon, revision = sidebar_icon_bytes(name)
    return Response(content=icon, media_type="image/png",
                    headers={"Cache-Control": "private, no-cache",
                             "ETag": f'"{name}-{revision}"',
                             "X-Content-Type-Options": "nosniff"})


@app.get("/assets/library-header-{kind}.png")
def default_library_header_image(kind: str):
    from server.library_header_art import default_png
    if kind not in ("movies", "tv"):
        from fastapi import HTTPException
        raise HTTPException(404, "No default header for this library type")
    return Response(content=default_png(kind), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=604800",
                             "X-Content-Type-Options": "nosniff"})


@app.get("/assets/library-appearance.js")
def library_appearance_js():
    return FileResponse(Path(__file__).with_name("library_appearance.js"),
                        media_type="application/javascript")


@app.get("/assets/media-context.js")
def media_context_script():
    return FileResponse(Path(__file__).with_name("media_context.js"),
                        media_type="text/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/assets/ambient.js")
def ambient_script():
    return FileResponse(Path(__file__).with_name("ambient.js"),
                        media_type="text/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/assets/shell.js")
def ui_shell():
    return FileResponse(Path(__file__).with_name("shell.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-store"})

@app.get("/assets/theme-music.js")
def theme_music_script():
    return FileResponse(Path(__file__).with_name("theme-music.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/assets/player.js")
def player_script():
    return FileResponse(Path(__file__).with_name("player.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"})


@app.get("/assets/vendor/hls-1.7.4.min.js")
def hls_js_library():
    # Served locally so the player works on a LAN without internet access.
    return FileResponse(Path(__file__).with_name("vendor") / "hls-1.7.4.min.js",
                        media_type="text/javascript",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/watch/{media_id}")
def watch_page(media_id: int):
    return FileResponse(Path(__file__).with_name("watch.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings")
def settings_home_page(request: Request):
    # TV-only playback and connection preferences; server administration stays
    # on the full web Settings page and is never shown in the TV navigation.
    tv_client = "OneEyedWillieTV/1" in request.headers.get("user-agent", "")
    template = "tv_settings.html" if tv_client else "settings_hub.html"
    return FileResponse(Path(__file__).with_name(template), media_type="text/html",
                        headers={"Cache-Control": "no-store", "Vary": "User-Agent"})


@app.get("/settings/credits")
def credits_settings_page():
    return FileResponse(Path(__file__).with_name("credits.html"), media_type="text/html")


@app.get("/settings/appearance")
def appearance_settings_page():
    return FileResponse(Path(__file__).with_name("appearance_settings.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings/general")
def general_settings_page():
    return FileResponse(Path(__file__).with_name("general_settings.html"), media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/settings/playback")
def playback_settings_page():
    # Legacy bookmarks go to the single, canonical playback settings section.
    return RedirectResponse(url="/settings/general#playback-heading", status_code=307)


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
