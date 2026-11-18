# One-Eyed Willie

Lightweight, self-hosted Movies, TV and Music media server. Modern interface, with pirate identity limited to the name and logo.

## Music library (initial web implementation)

Music is a separate media type; it is not included in Movies/TV grouping or Continue Watching.

1. Open **Settings → Libraries → Add library** and select **Music**.
2. Name the library, select a folder that is already mounted under `/media`, and save.
3. Click **Scan** for that library (automatic scans also discover new audio files).
4. Open **Music** in the sidebar to browse artists, albums, and tracks, search and play music.

Supported indexing extensions: MP3, FLAC, M4A, AAC, OGG, Opus, WAV, AIFF, and ALAC. Playback depends on the client's available audio codecs. Music tags and embedded cover art are read with Mutagen; missing or unreadable tags fall back to folder and filename details. Audio media is streamed read-only from configured music library folders.

**Current boundaries:** This is the first web-based Music catalog and player. Playlists, saved favorites, gapless playback, a player that survives full-page navigation, and native Google TV music browsing are not implemented yet. Lidarr can be added later as an optional connection; it is not required to use Music. 

## Third-party integration branding

The SABnzbd icon bundled as `server/sabnzbd-official.svg` is the unmodified upstream `icons/logo-arrow.svg` from [SABnzbd's source repository](https://github.com/sabnzbd/sabnzbd/blob/develop/icons/logo-arrow.svg). **SABnzbd name and icon © the SABnzbd Team.** Their [branding terms](https://sabnzbd.org/wiki/contact) permit this use by applications connecting through the SABnzbd API; use does not imply endorsement or a guarantee of continued API compatibility. The icon is not licensed under SABnzbd's software license.

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


## TV series ratings and episode controls

Series and season pages show the US TV parental rating (such as TV-14 or TV-MA) when the configured TMDB source supplies it. This is a TV classification, not a movie MPAA rating. The interface does **not** present TMDB or TVmaze votes as IMDb scores.

If you want an actual IMDb score in the series details row, obtain an OMDb API key and set it as an **optional private server environment variable** (never commit it to Git):

```sh
export OMDB_API_KEY='your-omdb-api-key'
docker compose up -d --build
```

The optional key is passed through both Compose configurations. When the show has a validated IMDb ID, the server requests the score from OMDb and caches the result. Without a configured key, series still display a link to IMDb where the provider has an IMDb ID; no rating is invented. Series missing an external ID or parental classification show an unavailable label.

**Shuffle Season** randomly orders all locally indexed episodes in the selected season, then offers the remaining episodes in that randomized order. The playlist is session-scoped to the player, not a persistent saved playlist, and normal Play/Resume clears it. Native Android TV builds need updating to use the playlist across player transitions.

## Scheduled maintenance and video previews

Open **Settings → Maintenance** to configure background tasks. The server checks for
due jobs during the **4 AM Central** maintenance window, respecting DST, and retains
last completion/result in its SQLite database across deployments.

| Task | Cadence |
| --- | --- |
| Optimize SQLite database | Weekly |
| Remove old generated maintenance bundles | Weekly |
| Prune stale VTT conversion and HLS cache | Weekly |
| Expire outdated cached metadata | Every 3 days |
| Rescan all libraries | Weekly (existing background incremental scans also continue) |
| Analyze codec, format, duration and resolution | Weekly; up to 40 files per batch |
| Refresh show/season metadata on next use | Every 3 days |
| Sample audio loudness (extensive analysis) | Weekly; up to 3 files per batch |
| Generate video preview thumbnails | Daily, or via **Generate video previews now**; up to 4 video sets per batch |

Preview generation defaults **on** and uses FFmpeg to extract up to six 320px
JPEG frames per video into `/data/maintenance/previews`. The player displays
them when seeking on the progress bar. Generated images never modify source
videos and aren't served until the indexed video ID and file fingerprint match.
Heavy analysis and thumbnail jobs run sequentially at reduced process priority
and use bounded sample durations. Full-library completion requires multiple
batches; the task cursor advances across the library.

All task enable/disable settings, completion times and cursor positions persist
in SQLite. **Run maintenance now** executes enabled jobs without waiting for
the maintenance window. Only directories managed by One-Eyed Willie are
eligible for cleanup. Downloaded subtitle files, playback history, manual metadata
matches, and the read-only media drive are never deleted. The generated
maintenance-bundles directory is currently empty in a normal installation;
the bundle cleanup option safely does nothing until the app creates bundles.
Provider cache refresh only expires entries and does not guarantee external
sources have new data.

This app does not have Plex's full deep-video-analysis engine or its seek
thumbnail index format. Its extensive analysis currently samples audio loudness;
it does not perform whole-file scene detection, intros, credits, or loudness
normalization. GPU/CPU use and throughput vary by the NUC's hardware.
