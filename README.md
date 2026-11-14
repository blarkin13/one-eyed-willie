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
