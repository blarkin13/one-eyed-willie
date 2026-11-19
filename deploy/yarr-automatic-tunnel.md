# Automatic Yarr tunnel — paired Gazorpazorp test

This replaces the old manual Docker sidecar test. The existing Yarr Media server now packages the official Cloudflare `cloudflared` connector in its Docker image.

## What happens automatically

1. The installed server uses its existing local Yarr pairing credential to authenticate with `yarr.larki-brian.workers.dev`.
2. The Yarr Worker checks the paired server identity and returns a tunnel credential **only** to the correct server. The credential is stored as an encrypted Cloudflare Worker secret, not in GitHub.
3. The installed server saves the credential in a 0600 file inside its persistent `/data` volume, then launches `cloudflared` via a token file. Tokens never appear in command-line arguments, browser responses or shell history.
4. The connector re-establishes its private outbound QUIC connection following a restart, monitors its process and retries transient failures. No inbound ports or public DNS are required.
5. From the signed-in hosted Yarr app, **Test private connection** checks only `/api/server/info` and `/health` over Workers VPC, verifying the server's actual ID before declaring success. This stage does not expose media.

## Test the update on the installed server

The latest Docker image **must be rebuilt** to include cloudflared. On the Linux server:

```bash
cd /opt/one-eyed-willie/app
git pull --ff-only origin main
sudo docker compose up -d --build one-eyed-willie
```

Do **not** use `deploy/setup-yarr-vpc.sh`, paste a token, or start `compose.yarr-vpc.yaml`. Those were the older manual test method.

After the app starts, open Yarr Media → Settings → General → Yarr Account. The server should report that its automatic private connector is running, if the Cloudflare service is reachable. You can then visit `https://yarr.larki-brian.workers.dev/app` while signed in and select **Test private connection**.

### If the test fails

Check only the status of the media server:

```bash
sudo docker compose ps one-eyed-willie
sudo docker compose logs --tail=80 one-eyed-willie
```

The connector deliberately suppresses raw output to avoid accidentally disclosing secrets. On the settings page it reports a safe error summary if provisioning or the binary fails. Cloudflare Tunnel must have outbound UDP 7844 allowed. Local library browsing and playback are never dependent on Cloudflare's availability.

### Security and public launch boundaries

**This is an automatic connector pilot for one already-paired server, Gazorpazorp.** The Cloudflare Worker is pinned to that server and its existing private Workers VPC service. Users of other servers cannot obtain this token.

For public release we still must implement secure **per-installation tunnel and VPC service provisioning**, dynamic worker routing, origin/server authorization, revocation and offline/device authentication. This pilot is not a production-safe multiuser video transport.

No tunnels are publicly exposed and no media is proxied at this stage. The standalone sidecar files remain in the repo for opt-in manual diagnostics but are no longer part of the primary test.
