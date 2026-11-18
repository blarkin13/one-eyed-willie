"""Host-network-only, diagnostic WebRTC endpoint.

The test is separate from Yarr's media server and Cloudflare connector.
Only paired account-authorized requests can initiate the 256-KiB synthetic
WebRTC transfer; no library volumes or media routes are mounted here.
"""
from fastapi import FastAPI

from .yarr_ice_probe import router
from .yarr_ice_fixed_port import install as install_fixed_ice_udp

# This process runs alone on Linux host networking, not in the main Yarr app.
install_fixed_ice_udp()

app = FastAPI(title="Yarr host-network diagnostic", docs_url=None,
              redoc_url=None, openapi_url=None)
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok", "component": "yarr-ice-diagnostic"}
