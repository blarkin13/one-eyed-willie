"""Optional At a Glance integrations: Clock, Weather and News.

Configurations live in the local SQLite app_settings table. Only approved
upstream hosts are contacted (never accept arbitrary URLs from clients).
Weather uses a user-entered US ZIP, the public ZIP lookup and the NWS grid
forecast. News presents short, attributed RSS headlines and links only.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from .library import db

router = APIRouter(prefix="/api/glance", tags=["integrations"])
NAMES = ("clock", "weather", "news")
FEEDS = {
    "npr": ("NPR News", "https://feeds.npr.org/1001/rss.xml", "npr.org"),
    "bbc": ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "bbc.co.uk"),
}
WEATHER_HEADERS = {
    "User-Agent": "Yarr Media (https://yarr.media)",
    "Accept": "application/geo+json",
}
# Cache public upstream results in server RAM only; no visitor tracking.
_CACHE = {}
_WEATHER_GRID = re.compile(
    r"^https://api\.weather\.gov/gridpoints/[A-Z]{3}/[0-9]{1,4},[0-9]{1,4}/forecast$"
)


class WidgetConfig(BaseModel):
    enabled: bool = False
    home: bool = True
    pause: bool = True
    idle: bool = True
    zip_code: str = Field(default="", pattern=r"^(?:|[0-9]{5})$")
    clock_format: Literal["12h", "24h"] = "12h"
    clock_zone: str = Field(default="local", min_length=1, max_length=64)
    news_source: Literal["npr", "bbc"] = "npr"


def _valid_config(config):
    if config.clock_zone != "local":
        try:
            ZoneInfo(config.clock_zone)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise HTTPException(422, "Invalid clock time zone")
    return config


def _settings_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)")


def _read(conn, name):
    _settings_table(conn)
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", ("glance_" + name,)).fetchone()
    if not row:
        return WidgetConfig()
    try:
        return _valid_config(WidgetConfig.model_validate_json(row["value"]))
    except Exception:
        return WidgetConfig()


@router.get("/settings")
def all_settings():
    with db() as conn:
        return {"integrations": {name: _read(conn, name).model_dump() for name in NAMES}}


@router.get("/settings/{name}")
def one_setting(name: Literal["clock", "weather", "news"]):
    with db() as conn:
        return _read(conn, name).model_dump()


@router.put("/settings/{name}")
def save_setting(name: Literal["clock", "weather", "news"], config: WidgetConfig):
    config = _valid_config(config)
    with db() as conn:
        _settings_table(conn)
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("glance_" + name, config.model_dump_json()),
        )
        conn.commit()
    _CACHE.pop(("weather", config.zip_code), None)
    _CACHE.pop(("news", config.news_source), None)
    return config.model_dump()


async def _json_from(url, headers=None):
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        if len(response.content) > 240_000:
            raise ValueError("Provider response too large")
        return response.json()


async def _xml_from(url):
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        response = await client.get(url, headers={"User-Agent": "YarrMedia/1.0"})
        response.raise_for_status()
        if len(response.content) > 300_000:
            raise ValueError("Provider response too large")
        return ET.fromstring(response.content)


@router.get("/weather")
async def weather():
    with db() as conn:
        config = _read(conn, "weather")
    if not config.enabled:
        raise HTTPException(404, "Weather integration is disabled")
    if not config.zip_code:
        raise HTTPException(422, "Enter a US ZIP code in Weather integration settings")
    key = ("weather", config.zip_code)
    cached = _CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        place = await _json_from("https://api.zippopotam.us/us/" + config.zip_code)
        location = place["places"][0]
        latitude, longitude = float(location["latitude"]), float(location["longitude"])
        if not (18 <= latitude <= 72 and -180 <= longitude <= -65):
            raise ValueError("Invalid US coordinates")
        point = await _json_from(
            f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}",
            WEATHER_HEADERS,
        )
        forecast_url = point["properties"]["forecast"]
        if not isinstance(forecast_url, str) or not _WEATHER_GRID.fullmatch(forecast_url):
            raise ValueError("Unexpected forecast provider address")
        forecast = await _json_from(forecast_url, WEATHER_HEADERS)
        periods = forecast["properties"]["periods"]
        if not periods:
            raise ValueError("No forecast available")
        current = periods[0]
        result = {
            "source": "National Weather Service",
            "source_url": "https://www.weather.gov/",
            "location": location.get("place name", "US")[:70] + ", " +
                        location.get("state abbreviation", "")[:2],
            "period": str(current.get("name", "Forecast"))[:60],
            "temperature": int(current["temperature"]),
            "unit": str(current.get("temperatureUnit", "F"))[:2],
            "conditions": str(current.get("shortForecast", ""))[:120],
            "wind": str(current.get("windSpeed", ""))[:45],
        }
        _CACHE[key] = (time.monotonic() + 900, result)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as error:
        raise HTTPException(503, "Weather forecast is unavailable right now") from error


@router.get("/news")
async def news():
    with db() as conn:
        config = _read(conn, "news")
    if not config.enabled:
        raise HTTPException(404, "News integration is disabled")
    key = ("news", config.news_source)
    cached = _CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    source, feed_url, allowed_domain = FEEDS[config.news_source]
    try:
        root = await _xml_from(feed_url)
        articles = []
        for item in root.findall("./channel/item"):
            heading = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            url = urlparse(link)
            if (url.scheme != "https" or not url.hostname or
                    (url.hostname != allowed_domain and
                     not url.hostname.endswith("." + allowed_domain))):
                continue
            if not heading:
                continue
            articles.append({"title": heading[:180], "url": link})
            if len(articles) == 5:
                break
        if not articles:
            raise ValueError("Feed has no usable headlines")
        result = {"source": source, "headlines": articles}
        _CACHE[key] = (time.monotonic() + 300, result)
        return result
    except (httpx.HTTPError, ValueError, TypeError, ET.ParseError) as error:
        raise HTTPException(503, "News headlines are unavailable right now") from error
