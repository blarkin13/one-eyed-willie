# One-Eyed Willie

Lightweight, self-hosted Movies and TV media server. Modern interface, with pirate identity limited to the name and logo.

## Initial milestone

- Dockerized FastAPI server on port 8787
- Health endpoint at `/health`
- Media folders mounted read-only; no automatic changes to existing files
- Persistent configuration and database directories

Planned: local movie/TV scanning, TMDB/TVDB metadata, posters and cast, playback, and Radarr/Sonarr-powered Discover.

## Run on Ubuntu NUC

```bash
cd /opt/one-eyed-willie
git clone https://github.com/blarkin13/one-eyed-willie.git app
cd app
sudo docker compose up -d --build
curl http://127.0.0.1:8787/health
```

The provided Compose example mounts `/media/brian/My Book` as `/media:ro`, with application data in `/opt/one-eyed-willie/data`. Do not expose port 8787 to the public internet until authentication is implemented.


## GPU compatibility playback

The Intel GPU path is opt-in. On the NUC, verify `/dev/dri/renderD128` exists, configure `WILLIE_RENDER_GID` to the render-device group ID, and deploy with the GPU override:

```sh
export WILLIE_RENDER_GID="$(stat -c '%g' /dev/dri/renderD128)"
docker compose -f compose.remote.yaml -f compose.gpu.yaml up -d --build
```

The compatibility HLS transcoder requests VAAPI **decoding, GPU scaling, and H.264 encoding**. Unsupported codecs, drivers, or devices fall back to CPU software processing when FFmpeg cannot start hardware decoding. This does **not** force hardware decoding for Direct Play on client devices; browser/TV hardware support determines that. The player's diagnostics icon reports the server's selected engine. GPU playback requires verification using an actual media sample on the NUC.

## In-player subtitle search

The subtitle icon now includes an OpenSubtitles search, results, download and direct activation. Configure your own API key through the server environment (do not commit credentials to Git):

```sh
export OPENSUBTITLES_API_KEY='your-opensubtitles-api-key'
# Optional provider bearer token if required for your account/downloads:
export OPENSUBTITLES_TOKEN='your-token'
docker compose -f compose.remote.yaml -f compose.gpu.yaml up -d --build
```

The optional credentials are passed through both Docker Compose modes. Without a key, local and embedded subtitles continue to function and the search panel shows a configuration message. Downloads stay in the private `/data/subtitles/opensubtitles` cache, never on the read-only media drive. Search/download uses OpenSubtitles' API and is subject to its account limits and provider availability. Downloads are restricted to HTTPS OpenSubtitles hosts; if the provider returns an unapproved external CDN host, that download is rejected rather than following an arbitrary URL. Verify provider responses with your account before relying on them.

### OpenSubtitles settings

Open **Settings → Connections → OpenSubtitles** to paste and verify an API key, with an optional account bearer token for provider downloads. The server saves credentials only under `/data/opensubtitles-settings.json` with restricted file permissions, never returns credential values, and applies changes immediately without restarting Docker. Environment-provided keys remain a fallback and are indicated as such in Settings; a Settings-saved key takes precedence. Removing a Settings-saved key falls back to the environment key if one exists. Previously downloaded subtitles remain available.
