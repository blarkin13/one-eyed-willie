# One-Eyed Willie Worker (optional, free web control-plane)

Public endpoint: `https://one-eyed-willie.larki-brian.workers.dev` when deployed to this account.

The Worker reverse-proxies only the web UI and control-plane API to a separately reachable HTTPS home server. Video, audio, range requests and media-stream routes are refused; Android TV should stream directly from the secure origin in the future. No Cloudflare Tunnel, domain under Humperdinck, or paid service needed.

- Set `ORIGIN_URL` in the Worker environment to `https://<your-reachable-origin-host>` (not a literal IP).
- Origin must have an automatically renewed publicly trusted TLS certificate and require strong authentication (Caddy proxy). No public port 8787.
- Forward TCP 443 from home router to the host running Caddy. Validate endpoint with an un-authenticated GET producing HTTP 401, then authenticate to see /health.
- Changing home public IP requires updating both the origin hostname/certificate and Worker variable. Prefer a user-controlled DDNS hostname for permanent use.
- Worker responds 503 while origin is unavailable; /__edge/health tests Worker infrastructure only and does not verify origin.
- Worker does not handle logins or register TV clients: Caddy currently applies HTTP Basic authentication; Android TV auth will need future device credentials.
- Treat this code as experimental FOSS-friendly integration; only deployment configuration holds personal network information.

**Warning:** Basic auth is not suitable as the final Android TV pairing flow. Protect existing Sonarr/Radarr ports independently.
