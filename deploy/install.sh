#!/usr/bin/env bash
# Yarr Media server installer.
#
#   curl -fsSL https://yarr.media/install.sh | sudo bash
#
# Installs Docker if needed, runs the Yarr Media server and an HTTPS front door
# (Caddy) with Docker Compose, keeps both updated daily, and tries to open
# port 443 on the router (UPnP) so Pro remote access works. Safe to run again:
# settings and library data are kept.
#
# Optional settings (environment variables):
#   YARR_MEDIA_DIR=/path/to/media   folder with your movies/shows/music (asked if not set)
#   YARR_CHANNEL=stable|edge        image channel (default stable)
#   YARR_NO_REMOTE=1                skip the HTTPS front door and router setup
#   YARR_PORT=8787                  port for the app on your home network
set -Eeuo pipefail

INSTALL_DIR="${YARR_INSTALL_DIR:-/opt/yarr-media}"
DATA_DIR="${YARR_DATA_DIR:-/var/lib/yarr-media}"
SBIN="${YARR_SBIN_DIR:-/usr/local/sbin}"
SYSTEMD="${YARR_SYSTEMD_DIR:-/etc/systemd/system}"
IMAGE=ghcr.io/blarkin13/yarr-media
CHANNEL="${YARR_CHANNEL:-stable}"
PORT="${YARR_PORT:-8787}"
APP_UID=10001

say()  { printf '\033[1;31m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == Linux ]] || die "Yarr Media's installer supports Linux. On Windows or macOS, use Docker Desktop with the compose file from https://yarr.media."
[[ $EUID -eq 0 || -n "${YARR_TEST_MODE:-}" ]] || die "Run with sudo:  curl -fsSL https://yarr.media/install.sh | sudo bash"
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "Unsupported processor $(uname -m). Yarr Media runs on 64-bit Intel/AMD or ARM." ;;
esac
case "$CHANNEL" in stable|edge) ;; *) die "YARR_CHANNEL must be stable or edge" ;; esac

# Read answers from the terminal even when this script is piped into bash.
ask() {
  local prompt="$1" default="$2" reply=""
  if [[ -r /dev/tty ]]; then
    read -r -p "$prompt [$default]: " reply </dev/tty || true
  fi
  printf '%s' "${reply:-$default}"
}

# ---- Docker -------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker (from get.docker.com)"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing. Install the docker-compose-plugin package and run this again."

# ---- Media folder -------------------------------------------------------------
MEDIA_DIR="${YARR_MEDIA_DIR:-}"
if [[ -z "$MEDIA_DIR" && -f "$INSTALL_DIR/.env" ]]; then
  MEDIA_DIR="$(sed -n 's/^YARR_MEDIA_DIR=//p' "$INSTALL_DIR/.env" | head -1)"
fi
if [[ -z "$MEDIA_DIR" ]]; then
  guess=/srv/media
  for candidate in /media /mnt /srv/media "/home/${SUDO_USER:-}/Videos"; do
    if [[ -d "$candidate" ]] && [[ -n "$(ls -A "$candidate" 2>/dev/null)" ]]; then guess="$candidate"; break; fi
  done
  MEDIA_DIR="$(ask "Folder that holds your movies, shows and music" "$guess")"
fi
MEDIA_DIR="${MEDIA_DIR%/}"
[[ -d "$MEDIA_DIR" ]] || die "Media folder '$MEDIA_DIR' does not exist. Create it or set YARR_MEDIA_DIR=/path and run again."
[[ "$MEDIA_DIR" != *$'\n'* && "$MEDIA_DIR" != *'"'* ]] || die "Media folder path contains unsupported characters."

# ---- Files --------------------------------------------------------------------
say "Setting up $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$DATA_DIR/data" "$DATA_DIR/caddy"
chown -R "$APP_UID:$APP_UID" "$DATA_DIR/data" || [[ -n "${YARR_TEST_MODE:-}" ]]

GPU_BLOCK=""
if [[ "$ARCH" == amd64 && -c /dev/dri/renderD128 ]]; then
  RENDER_GID="$(stat -c '%g' /dev/dri/renderD128)"
  GPU_BLOCK="    devices:
      - /dev/dri/renderD128:/dev/dri/renderD128
    group_add:
      - \"$RENDER_GID\""
  say "Intel graphics found: hardware transcoding enabled"
fi

cat >"$INSTALL_DIR/.env" <<EOF
# Written by the Yarr Media installer. Run the installer again to change.
YARR_MEDIA_DIR=$MEDIA_DIR
YARR_CHANNEL=$CHANNEL
YARR_PORT=$PORT
EOF

REMOTE_SERVICES=""
if [[ "${YARR_NO_REMOTE:-0}" != 1 ]]; then
  REMOTE_SERVICES="
  # HTTPS front door for Pro remote access. It gets a certificate for this
  # home's own address (a-b-c-d.sslip.io) the first time a viewer connects,
  # after asking the server that the name is really its own.
  https:
    image: caddy:2
    container_name: yarr-media-https
    restart: unless-stopped
    depends_on: [yarr]
    ports:
      - \"443:443\"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - $DATA_DIR/caddy:/data
    security_opt:
      - no-new-privileges:true"
  cat >"$INSTALL_DIR/Caddyfile" <<'EOF'
{
	on_demand_tls {
		ask http://yarr:8787/api/remote/tls-check
	}
}

https:// {
	tls {
		on_demand
	}
	# Every request from the internet is marked remote, so the server
	# requires a Yarr pass from yarr.media. The home network is unaffected.
	reverse_proxy yarr:8787 {
		header_up X-Yarr-Remote 1
	}
}
EOF
fi

cat >"$INSTALL_DIR/compose.yaml" <<EOF
# Written by the Yarr Media installer (https://yarr.media/install.sh).
name: yarr-media
services:
  yarr:
    image: $IMAGE:$CHANNEL
    container_name: yarr-media
    restart: unless-stopped
    environment:
      MEDIA_ROOT: /media
      DATABASE_PATH: /data/library.sqlite3
    ports:
      - "$PORT:8787"
    volumes:
      - "$MEDIA_DIR:/media:ro"
      - "$DATA_DIR/data:/data"
$GPU_BLOCK
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
$REMOTE_SERVICES
EOF

# ---- Updates ------------------------------------------------------------------
cat >"$SBIN/yarr-media-update" <<EOF
#!/usr/bin/env bash
# Pull the newest Yarr Media images, restart only what changed, refresh the
# router's port mapping, and remove old images.
set -euo pipefail
cd "$INSTALL_DIR"
docker compose pull --quiet
docker compose up -d --remove-orphans
if [[ -x "$SBIN/yarr-media-upnp" ]]; then "$SBIN/yarr-media-upnp" || true; fi
docker image prune -f >/dev/null
EOF
chmod 755 "$SBIN/yarr-media-update"

cat >"$SYSTEMD/yarr-media-update.service" <<EOF
[Unit]
Description=Update Yarr Media
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=$SBIN/yarr-media-update
EOF
cat >"$SYSTEMD/yarr-media-update.timer" <<'EOF'
[Unit]
Description=Daily Yarr Media update

[Timer]
OnCalendar=*-*-* 04:00:00
RandomizedDelaySec=2h
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now yarr-media-update.timer >/dev/null

# ---- Router (UPnP) ------------------------------------------------------------
LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src"){print $(i+1); exit}}')"
UPNP_RESULT="skipped"
if [[ "${YARR_NO_REMOTE:-0}" != 1 && -n "$LAN_IP" ]]; then
  if ! command -v upnpc >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq miniupnpc >/dev/null 2>&1 || true
  fi
  if command -v upnpc >/dev/null 2>&1; then
    cat >"$SBIN/yarr-media-upnp" <<EOF
#!/usr/bin/env bash
# Ask the router to forward TCP 443 to this computer (renewed daily).
exec upnpc -e "Yarr Media" -a "$LAN_IP" 443 443 TCP 0 >/dev/null 2>&1
EOF
    chmod 755 "$SBIN/yarr-media-upnp"
    if "$SBIN/yarr-media-upnp"; then UPNP_RESULT="ok"; else UPNP_RESULT="failed"; fi
  fi
fi

# ---- Start --------------------------------------------------------------------
say "Downloading and starting Yarr Media ($CHANNEL)"
cd "$INSTALL_DIR"
docker compose pull --quiet
docker compose up -d --remove-orphans

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 || warn "The server is still starting. Check with: docker logs yarr-media"

echo
say "Yarr Media is running."
echo "   Open it on your home network:  http://${LAN_IP:-this-computer}:$PORT"
echo "   Media folder:                  $MEDIA_DIR"
if [[ "${YARR_NO_REMOTE:-0}" != 1 ]]; then
  echo
  echo "   Watching away from home (Pro):"
  echo "   1. In the app, open Settings > General > Connect to Yarr and pair with your yarr.media account."
  case "$UPNP_RESULT" in
    ok) echo "   2. Your router accepted the port 443 forward automatically." ;;
    *)  echo "   2. On your router, forward TCP port 443 to ${LAN_IP:-this computer} (automatic setup was not possible)." ;;
  esac
  echo "   3. On yarr.media/account choose 'Check remote access', then open app.yarr.media anywhere."
fi
echo
echo "   Updates install automatically every night. Update now: sudo $SBIN/yarr-media-update"
echo "   Uninstall: cd $INSTALL_DIR && sudo docker compose down && sudo rm -rf $INSTALL_DIR"
echo "              (your library data stays in $DATA_DIR until you delete it)"
