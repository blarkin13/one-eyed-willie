# Yarr Media

Self-hosted movies, TV and music. Run the server on a computer that holds your
media, then watch on Google TV, in any browser at home, or anywhere at
[app.yarr.media](https://app.yarr.media) with Pro.

Your media stays on your server. Video streams straight from your server to
your screen; it is never uploaded to or relayed through Yarr Media.

## Install

On a 64-bit Linux computer (Intel/AMD or ARM) that can see your media:

```bash
curl -fsSL https://yarr.media/install.sh | sudo bash
```

The installer:

- installs Docker if it is missing and asks which folder holds your media;
- runs the server (`ghcr.io/blarkin13/yarr-media:stable`) on port **8787**;
- adds an HTTPS front door for Pro remote access and asks your router (UPnP) to
  forward port **443**;
- updates everything nightly (`sudo yarr-media-update` updates now).

Run it again at any time to change settings; your library and watch history
are kept. Options: `YARR_MEDIA_DIR=/path`, `YARR_CHANNEL=stable|edge`,
`YARR_NO_REMOTE=1` (home network only), `YARR_PORT=8787`.

**Ubuntu / Debian with apt**

```bash
curl -fsSL https://yarr.media/apt/yarr-media.gpg | sudo tee /usr/share/keyrings/yarr-media.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/yarr-media.gpg] https://yarr.media/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/yarr-media.list
sudo apt update && sudo apt install yarr-media
sudo yarr-media-setup
```

**Uninstall**: `cd /opt/yarr-media && sudo docker compose down && sudo rm -rf /opt/yarr-media`
(or `sudo apt purge yarr-media`). Library data stays in `/var/lib/yarr-media`
until you delete it.

## Watch

| Where | How |
| --- | --- |
| Home network | Open `http://<server-ip>:8787` in any browser. |
| Google TV | Install the APK from [Releases](https://github.com/blarkin13/one-eyed-willie/releases/latest) (on the TV: Downloader app → `yarr.media/tv`). It finds the server on your network. |
| Anywhere (Pro) | [app.yarr.media](https://app.yarr.media) after the steps below. |

### Remote access (Pro)

1. In the app: **Settings → General → Connect to Yarr**, and pair the server with
   your account at [yarr.media/account](https://yarr.media/account).
2. Make sure TCP port **443** reaches the server (the installer tries UPnP; if
   that fails, forward it on your router).
3. On **My Account**, use **Check remote access**, then open
   [app.yarr.media](https://app.yarr.media) anywhere.

How it works: app.yarr.media serves only a small starter page and service
worker. After you sign in, your browser talks directly to your server's own
HTTPS address (derived from the public IP it reports to yarr.media). Every
remote request carries a short-lived, signed **Yarr pass**, which the server
checks itself; requests from your home network do not need one.

On a Google TV, sign in from **Server settings → Yarr account** by entering the
code shown at [yarr.media/activate](https://yarr.media/activate).

## What's in this repository

| Path | What |
| --- | --- |
| `server/` | The media server: FastAPI + SQLite, web UI, FFmpeg/HLS playback, metadata, integrations, the remote-access gate (`remote_access.py`). |
| `google-tv/` | Android / Google TV app (WebView shell + native Media3 player). |
| `cloudflare/yarr/` | The yarr.media Worker: website, accounts (Google sign-in), TV sign-in, passes, Stripe, D1 migrations, deploy script. |
| `deploy/` | Installer, `.deb` packaging and apt publishing, Caddy configs, the development server's updater. |
| `tests/`, `cloudflare/yarr/test/` | Python tests (incl. Playwright browser tests) and Worker tests. |
| `docs/` | Feature notes ([features.md](docs/features.md)), integrations, playback, remote access, [development server](docs/development-server.md). |

## Develop

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8787      # server
python -m unittest discover -s tests              # Python tests (browser tests need Chrome + playwright)
node --test cloudflare/yarr/test/*.test.mjs       # Worker tests (Node 22)
```

Google TV app: `cd google-tv && gradle :app:assembleDebug` (CI builds a debug
and a smaller "lean" APK on every change).

**Releases**: every merge to `main` publishes the `edge` image. A release is
**Actions → Release → Run workflow** with a version (or pushing a `vX.Y.Z` tag):
it publishes the `stable` image, a GitHub Release with the TV APK, installer
and `.deb`, and the signed apt repository (needs the `APT_SIGNING_KEY` secret,
created once with `deploy/deb/create-apt-key.sh`).

**yarr.media Worker**: `bash cloudflare/yarr/deploy.sh` (add `dev` for the dev
Worker and database). Database changes go in `cloudflare/yarr/migrations/`.

## Credits

### SABnzbd

The SABnzbd icon bundled as `server/sabnzbd-official.svg` is the unmodified upstream `icons/logo-arrow.svg` from [SABnzbd's source repository](https://github.com/sabnzbd/sabnzbd/blob/develop/icons/logo-arrow.svg). **SABnzbd name and icon © the SABnzbd Team.** Their [branding terms](https://sabnzbd.org/wiki/contact) permit this use by applications connecting through the SABnzbd API; use does not imply endorsement or a guarantee of continued API compatibility. The icon is not licensed under SABnzbd's software license.

### Integration logos

Connection-service logos are bundled locally and used only to identify supported third-party services. Lidarr and Plex pictograms are sourced from the [selfh.st icon collection](https://github.com/selfhst/icons), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) by that collection's contributors. OpenSubtitles' icon is from the [official OpenSubtitles.com Kodi add-on](https://github.com/opensubtitles-dev/service.subtitles.opensubtitles-com). Radarr, Sonarr, and SABnzbd keep their previously bundled logos. Logos and trademarks belong to their respective owners; their presence does not imply endorsement.
