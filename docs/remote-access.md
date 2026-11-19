# Remote Access: Google Wifi + free HTTPS + Cloudflare Worker

This configuration provides secure remote web browsing without a VPN, Cloudflare Tunnel, paid services or changes to the Humperdinck site.

## Status
- A standalone Worker is deployed at `https://one-eyed-willie.larki-brian.workers.dev`. Until origin is ready it will show "not reachable yet".
- HTTPS Caddy reverse proxy is prepared but must be activated once on the Ubuntu NUC.
- The router TCP 443 forward must be added by the owner.
- The public app must be tested from outside the LAN before marking it operational.

## One-time NUC setup
1. In Yarr Media **Settings → Remote Access**, save your home public IP and the preferred Worker URL.
2. In a terminal on `vogsphere`, execute:

```bash
cd /opt/one-eyed-willie/app
sudo bash scripts/enable-remote.sh
```

3. Choose a long password; it is not stored in plaintext and should not be posted in chat.
4. On Google Wifi, forward **TCP 443** to the NUC's reserved LAN IP at internal port **443**. Do not forward 8787. TCP 80 is optional for HTTP validation/redirects if TLS-ALPN via 443 works.
5. Test from cellular data at the HTTPS origin shown by the script, then test the Worker endpoint. Expect browser Basic authentication and `/health` returning a JSON response when authenticated.

The script reads the public IP from your server's saved Settings, derives a temporary free `sslip.io` hostname, hashes the password using Caddy, writes a protected `.env.remote` file, checks Docker Compose configuration, and starts Caddy alongside your application. Caddy automatically attempts publicly trusted certificate issuance via ACME. Port 443 must be reachable from the internet before issuance can succeed.

## Security / architecture
- Port 8787 is kept available on the home LAN. **Never forward it to the internet.**
- Public 443 runs the HTTPS Caddy reverse proxy with password protection.
- The Worker proxies web and catalog requests; video/audio streams and HTTP range requests are blocked. The Android TV app will use direct secure origin streaming when implemented.
- This public endpoint has no native account management yet; Basic authentication is temporary for personal web use.
- Saving Settings alone does not make changes to the router, start Caddy, or update Cloudflare. The initial Worker origin is configured in Cloudflare; when the IP changes, update both the server setup and the Worker configuration.
- If your ISP changes your IP frequently, replace the temporary `sslip.io` hostname with a free user-controlled dynamic DNS hostname to keep TLS stable. Public certificates for shared wildcard-DNS hostnames may be rate limited.

## Rollback
```bash
cd /opt/one-eyed-willie/app
sudo docker compose --env-file .env.remote -f compose.remote.yaml down
sudo docker compose -f compose.yaml up -d --build
```
Also remove port 443 forwarding on the router when disabling remote access. The Worker should be disabled if not used.

## Not currently implemented
- Browser UI control for starting/stopping Docker HTTPS, checking reachability, changing the Caddy password, or automatically updating the Worker when the public IP changes
- Android TV pairing and token authentication
- Media streaming endpoints

Do not represent the Worker status endpoint as proof that the home origin is reachable.
