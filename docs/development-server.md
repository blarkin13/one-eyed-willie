# Brian's NUC (development server)

The original home server runs from a git checkout instead of the installer, so
it can follow main within a minute (`deploy/update.sh` with
`deploy/one-eyed-willie-update.timer`). Customer servers use the installer and
the `stable` image instead.

```bash
cd /opt/one-eyed-willie
git clone https://github.com/blarkin13/one-eyed-willie.git app
cd app
sudo docker compose up -d --build
curl http://127.0.0.1:8787/health
```

`compose.yaml` mounts `/media/brian/My Book` as `/media:ro`, with data in
`/opt/one-eyed-willie/data`. Remote HTTPS uses `compose.remote.yaml` with
`deploy/Caddyfile.remote` (see `scripts/enable-remote.sh`); the optional Intel GPU
overlay is `compose.gpu.yaml`.
