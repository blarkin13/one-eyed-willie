#!/usr/bin/env bash
# One-time local activation: no Cloudflare credential, Docker socket exposure, or UPnP.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS="/opt/one-eyed-willie/data/remote-settings.json"
if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $ROOT/scripts/enable-remote.sh" >&2
  exit 1
fi
if [[ ! -r "$SETTINGS" ]]; then
  echo "First save your public IP at Yarr Media → Settings → Remote Access." >&2
  exit 1
fi
HOSTNAME="$(python3 - "$SETTINGS" <<'PY'
import ipaddress, json, sys
with open(sys.argv[1]) as source:
    value = json.load(source).get("public_ip", "")
ip = ipaddress.IPv4Address(value)
if not ip.is_global:
    raise SystemExit("Enter a valid public IP in Settings first.")
print(str(ip).replace(".", "-") + ".sslip.io")
PY
)"
echo "Secure origin: https://${HOSTNAME}"
echo "This will restart Yarr Media with an HTTPS reverse proxy."
echo "Before remote testing, forward Google Wifi TCP 443 → vogsphere TCP 443."
echo "Do not forward port 8787."
read -r -s -p "Choose a remote-access password (14+ characters): " PASSWORD </dev/tty
printf '\n'
if [[ ${#PASSWORD} -lt 14 ]]; then
  echo "Password is too short." >&2
  unset PASSWORD
  exit 1
fi
read -r -s -p "Confirm the password: " CONFIRM </dev/tty
printf '\n'
if [[ "$PASSWORD" != "$CONFIRM" ]]; then
  echo "Passwords did not match; nothing changed." >&2
  unset PASSWORD CONFIRM
  exit 1
fi
unset CONFIRM
# Newline is required for Caddy's non-interactive stdin password prompt.
HASH="$(printf '%s\n' "$PASSWORD" | docker run --rm -i caddy:2 caddy hash-password --algorithm bcrypt)"
unset PASSWORD
[[ "$HASH" == \$2* ]] || { echo "Failed to create password hash." >&2; exit 1; }
umask 077
ENV_FILE="$ROOT/.env.remote"
TMP="$(mktemp "$ROOT/.env.remote.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
{
  printf 'WILLIE_HOSTNAME=%s\n' "$HOSTNAME"
  printf 'WILLIE_USERNAME=willie\n'
  printf "WILLIE_PASSWORD_HASH='%s'\n" "$HASH"
} > "$TMP"
mv -f "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"
cd "$ROOT"
docker compose --env-file "$ENV_FILE" -f compose.remote.yaml config -q
docker compose -f compose.yaml down
docker compose --env-file "$ENV_FILE" -f compose.remote.yaml up -d --build
echo
echo "Proxy started. HTTPS certificate issuance requires inbound TCP 443."
echo "Test from cellular data at https://${HOSTNAME}/health"
echo "Login username: willie (use the password you just set)."
echo "The public Worker URL will work after the HTTPS origin becomes reachable."
