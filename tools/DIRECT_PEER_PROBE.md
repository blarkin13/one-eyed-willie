# Yarr direct peer transport — isolated experiment

This is the first executable prototype for [issue #184](https://github.com/blarkin13/one-eyed-willie/issues/184).
It does **not** change One-Eyed Willie's production media player, Cloudflare Worker,
account configuration, or server routing.

## What it demonstrates

- A browser and the Python server negotiate an encrypted WebRTC RTCDataChannel.
- The browser requests a specific 1 MiB logical byte range, beginning at offset 1024.
- The Python server produces deterministic **synthetic bytes**, sends them in bounded 16 KiB chunks, and the browser validates every byte and prints its SHA-256.
- Browser diagnostics print the selected ICE candidate types to help determine whether the connection was direct or relayed.
- No real media file, transcoder, database, private key, or Yarr account is accessed.

**This is not yet proof of remote connectivity:** that requires an off-LAN test and inspection
of the selected candidate pair, actual network traffic, and Cloudflare Worker usage.
The prototype has no Yarr session grant yet and is deliberately not a production feature.

## Run

On a developer machine with Python 3.12 and appropriate firewall rules:

```bash
python -m venv .venv-direct-probe
. .venv-direct-probe/bin/activate
pip install -r requirements.txt -r tools/requirements-direct-probe.txt

# For this temporary experiment, use a random secret with at least 32 characters.
export YARR_DIRECT_PROBE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# Make a note of the token for the browser form; never commit it.
python -m uvicorn tools.direct_peer_probe:app --host 127.0.0.1 --port 8799
```

Open `http://127.0.0.1:8799/probe` on the **same computer** and paste the token.
For testing across computers, use an authenticated HTTPS development ingress and
explicit firewall policy. Do not publish this test port or remove the token gate.
Browsers generally require a secure context for their WebCrypto integrity check.

Both the browser and the Python peer now use a public STUN resolver for ICE discovery,
not a TURN media relay; direct connectivity can still fail behind restrictive NAT/firewalls.

## Off-LAN validation checklist (not yet completed)

1. Run the isolated probe on a controlled development host (not a production server),
   with a temporary high-entropy token, and expose **only HTTPS signaling** through a
   restricted, authenticated development ingress. Do not expose port 8799 publicly.
2. Connect a different test device using a different internet connection (e.g.,
   cellular with Wi-Fi off) and visit that development HTTPS origin's `/probe` page.
3. Execute the 1 MiB integrity test and capture the selected ICE candidate pair,
   transfer time, failures, and relevant sanitized logs. Never share the token.
4. Verify the selected path with packet or ICE diagnostics and check Cloudflare
   traffic independently. A `host`/`srflx` candidate alone does not prove that
   Cloudflare was bypassed on every hop, and HTTPS signaling may still use it.
5. Repeat with different NAT/firewall configurations, including a known restrictive
   network. Document direct-connection failures without automatically relaying video.

**Important:** No off-LAN connection has been verified by this change. Installing
STUN discovery alone does not create a publicly reachable server or a TURN fallback.
Do not interpret a successful same-machine test as proof of remote connectivity.

## Security / known gaps

- Probe is disabled unless the explicit `YARR_DIRECT_PROBE_TOKEN` is set to 32+ characters.
- No real file I/O or arbitrary proxy requests. Single bounded 1 MiB synthetic read per peer.
- Four simultaneous peer connections maximum.
- This standalone prototype must **not** be integrated with Yarr's session cookie,
  used on an untrusted public ingress, or presented as a finished remote-access feature.
- Next: issue a short-lived, authenticated, server-bound grant via Yarr; add explicit
  ICE signaling, expiration, rate limiting, session cleanup, and then read-only media
  range handling with library authorization. A browser MSE / HLS transport adapter
  is required before existing video playback can use RTCDataChannel.

Existing Yarr remote playback remains Cloudflare-relayed until a tested direct
transport and player integration are implemented.
