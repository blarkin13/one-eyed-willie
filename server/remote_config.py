"""Locally saved remote-connection preferences.

Saving preferences does not open a firewall port, configure a router,
publish a Worker, or switch on HTTPS. Deployment must be verified separately.
"""
import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")
CONFIG_FILE = Path(os.environ.get("REMOTE_SETTINGS_PATH", "/data/remote-settings.json"))
LOCK = RLock()
HOST_PATTERN = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


class RemoteSettings(BaseModel):
    public_ip: str = Field(default="", max_length=45)
    public_url: str = Field(default="", max_length=300)


def _invalid_port(parsed):
    try:
        return parsed.port not in (None, 443)
    except ValueError:
        return True


def normalized(data: RemoteSettings) -> RemoteSettings:
    public_ip = data.public_ip.strip()
    if public_ip:
        try:
            address = ipaddress.IPv4Address(public_ip)
        except ipaddress.AddressValueError as error:
            raise HTTPException(422, "Enter a valid public IPv4 address") from error
        if not address.is_global:
            raise HTTPException(422, "This must be a public IPv4 address")
        public_ip = str(address)

    public_url = data.public_url.strip()
    if public_url:
        try:
            parsed = urlsplit(public_url)
            host = parsed.hostname or ""
        except ValueError as error:
            raise HTTPException(422, "Enter a valid HTTPS URL") from error
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or _invalid_port(parsed)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or not HOST_PATTERN.fullmatch(host)
        ):
            raise HTTPException(422, "Enter a public HTTPS URL without a path, port or credentials")
        public_url = "https://" + host.lower()

    return RemoteSettings(public_ip=public_ip, public_url=public_url)


def _read_settings() -> RemoteSettings:
    try:
        return normalized(RemoteSettings.model_validate_json(CONFIG_FILE.read_text()))
    except FileNotFoundError:
        return RemoteSettings()
    except (ValueError, OSError) as error:
        raise HTTPException(500, "Saved remote settings cannot be read") from error


def _view(data: RemoteSettings):
    return {
        **data.model_dump(),
        "origin_hostname": data.public_ip.replace(".", "-") + ".sslip.io" if data.public_ip else "",
        "remote_access_ready": False,
        "status": "Setup required — saving settings does not enable remote access",
    }


@router.get("/remote/settings")
def get_remote_settings():
    with LOCK:
        return _view(_read_settings())


@router.put("/remote/settings")
def save_remote_settings(settings: RemoteSettings):
    validated = normalized(settings)
    with LOCK:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=".remote-settings-", suffix=".json", dir=CONFIG_FILE.parent
        )
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(validated.model_dump(), output)
                output.write("\n")
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, CONFIG_FILE)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    return _view(validated)
