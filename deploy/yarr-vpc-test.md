> **Superseded for normal testing.** The server now automatically launches cloudflared after pairing; use [yarr-automatic-tunnel.md](./yarr-automatic-tunnel.md). The steps below are retained only for manual diagnostic fallback.

# Private connection pilot: Gazorpazorp

This is an **isolated development pilot**, not multi-customer remote playback.

## Already provisioned on Cloudflare
- Tunnel: `yarr-gazorpazorp-vpc` (private; no public hostname, no route to your existing `one-eyed-willie` Worker)
- Workers VPC Service: `yarr-gazorpazorp-api` targeting the Docker service `one-eyed-willie:8787`
- Worker `yarr`: `YARR_PRIVATE_API` VPC service binding, owner-checked `GET /api/private/health`
- Health endpoint is pinned to the paired Gazorpazorp server; arbitrary user-provided paths, hosts and media URLs are **not** fetched.

## One-time installation on your existing Linux server

1. In the Cloudflare dashboard, open **Workers VPC → Tunnels** (or Zero Trust → Networks → Tunnels) and select **yarr-gazorpazorp-vpc**.
2. Select the Docker connector instructions. Copy **only the tunnel token** (the string after `--token`), and don't paste it into GitHub or chat.
3. Run:

```bash
cd /opt/one-eyed-willie/app
git pull --ff-only origin main
bash deploy/setup-yarr-vpc.sh
```

The setup script securely prompts for the token and writes it to the local, gitignored `.env` with mode 0600. It starts **only** the optional `yarr-cloudflared` sidecar. It doesn't open firewall ports or replace the existing Yarr Media app. The tunnel requires outbound UDP 7844 (QUIC).

4. Once the Cloudflare tunnel shows Healthy, sign into `https://yarr.larki-brian.workers.dev/app` and click **Test private connection**.
5. Expected response: `connected: true`, the application name and version, and `media_access: false`. If the tunnel is offline, the endpoint returns a controlled error, rather than exposing your origin.

### Troubleshooting

```bash
sudo docker compose -f compose.yaml -f compose.yarr-vpc.yaml ps yarr-cloudflared
sudo docker compose -f compose.yaml -f compose.yarr-vpc.yaml logs --tail=50 yarr-cloudflared
```

Never share the tunnel token or logs containing credentials. If needed, redact tokens before sharing.

### Disable the test tunnel

```bash
cd /opt/one-eyed-willie/app
sudo docker compose -f compose.yaml -f compose.yarr-vpc.yaml stop yarr-cloudflared
```

The old media server continues operating locally, and the existing Yarr Media Worker is untouched.

## Security / rollout boundary

Workers VPC is currently a beta. The single `YARR_PRIVATE_API` binding is dedicated to Gazorpazorp and **cannot** be assumed to serve arbitrary customer servers. Each customer will require an isolated, authenticated binding/provisioning model.

No movie library, playback API, streams, directory listing, or unapproved origin route is exposed by this test. Before extending this to media access, implement end-to-end authorization on the origin server, signed requests, revocation, account/device permissions, session handling and a scalable per-server tunnel association. Never proxy arbitrary URLs through the account Worker.
