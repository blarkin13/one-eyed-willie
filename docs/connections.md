# Connection architecture — no additional paid services

## Goal
Use the same server API for the web client and future Android TV client. Prefer a local connection on home Wi-Fi; use HTTPS to a personally configured hostname outside the home.

## Rules
- Do not require a hosted account, subscription, third-party relay, paid VPN, or paid DNS provider.
- A remote hostname may use an existing domain or free dynamic DNS.
- Automatic certificate issuance/renewal with Let's Encrypt (ACME) is free.
- No unauthenticated public access. Never automatically expose Docker port 8787.
- Remote playback is direct from the owner's NUC; upload bandwidth, router, and ISP restrictions apply.
- Carrier-grade NAT cannot be solved by direct inbound port forwarding. No guarantee of zero-cost remote access for every network.
- Only store random installation and device identifiers, not hardware serial numbers.

## Phase 1 (implemented)
- Persistent random server ID at `/data/server-identity.json`.
- `GET /api/server/info` announces stable identity and capabilities, with unavailable features explicitly false.
- Backward-compatible existing library routes.

## Phase 2
- Authenticate owner sessions and protect mutating APIs (including local).
- Short-lived device pairing code, rate limits, token rotation/revocation.
- mDNS service advertisement (`_oneeyedwillie._tcp.local.`) on host networking, avoid advertising a Docker-only IP.
- Remember local connection for Android TV and validate server ID before trust.
- Implement HTTPS origin, configurable remote hostname, no automatic insecure port forward.
- Connection selection: test local first, then remote; never silently fall back to an insecure public origin.
- FFmpeg/media streaming API with HTTP range and authorization.
- Admin device list, disable remote access switch, health and connection diagnostics.

## Deployment caution
Do not publicly forward TCP 8787. No media streaming and no remote access have been enabled by this change.
