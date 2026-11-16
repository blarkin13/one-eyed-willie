"""Verified Intel VAAPI availability inside the running container."""
import os
import subprocess
from functools import lru_cache
from pathlib import Path

DEVICE = "/dev/dri/renderD128"


@lru_cache(maxsize=1)
def hardware_supported():
    if os.environ.get("WILLIE_HW_ACCEL", "auto").lower() not in ("auto", "vaapi"):
        return False
    if not Path(DEVICE).is_char_device() or not os.access(DEVICE, os.R_OK | os.W_OK):
        return False
    # Checking /dev/dri exists is not enough: the driver and encoder must work.
    try:
        test = subprocess.run(
            ["/usr/bin/ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
             "-vaapi_device", DEVICE, "-f", "lavfi", "-i",
             "color=c=black:s=64x64:r=1", "-vf", "format=nv12,hwupload",
             "-frames:v", "1", "-c:v", "h264_vaapi", "-f", "null", "-"],
            capture_output=True, timeout=8, check=False,
        )
        return test.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
