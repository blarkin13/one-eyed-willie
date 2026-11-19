"""Stable per-install server identity for future web and Android TV clients."""
import json
import os
import uuid
from pathlib import Path
from threading import Lock

from fastapi import APIRouter

router = APIRouter(prefix="/api")
LOCK = Lock()
IDENTITY_PATH = Path(os.environ.get("SERVER_IDENTITY_PATH", "/data/server-identity.json"))


def get_server_id():
    with LOCK:
        try:
            document = json.loads(IDENTITY_PATH.read_text())
            return str(uuid.UUID(document["server_id"]))
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("Server identity file is invalid; refusing to overwrite it")

        IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        identifier = str(uuid.uuid4())
        # Exclusive creation avoids replacing identity from concurrent workers.
        try:
            with IDENTITY_PATH.open("x") as file:
                json.dump({"server_id": identifier}, file)
                file.write("\n")
            os.chmod(IDENTITY_PATH, 0o600)
            return identifier
        except FileExistsError:
            return str(uuid.UUID(json.loads(IDENTITY_PATH.read_text())["server_id"]))


@router.get("/server/info")
def server_info():
    return {
        "server_id": get_server_id(),
        "name": "Yarr Media",
        "api_version": 1,
        "capabilities": {
            "libraries": True,
            "local_discovery": False,
            "remote_access": False,
            "device_pairing": False,
            "streaming": False,
        },
    }
