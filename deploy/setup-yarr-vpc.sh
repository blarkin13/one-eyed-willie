#!/usr/bin/env bash
# Install the outbound-only Yarr Workers VPC connector on a Docker Compose server.
# Never print or commit your tunnel token.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed." >&2
  exit 1
fi
if [[ ! -f compose.yaml || ! -f compose.yarr-vpc.yaml ]]; then
  echo "Yarr Compose configuration is missing; run git pull first." >&2
  exit 1
fi

printf 'Paste the token for tunnel yarr-gazorpazorp-vpc (input is hidden): '
IFS= read -r -s YARR_TOKEN
printf '\n'
if [[ ${#YARR_TOKEN} -lt 40 || "$YARR_TOKEN" == *' '* ]]; then
  echo "Token looks invalid. No files changed." >&2
  exit 1
fi

umask 077
TEMP_ENV="$(mktemp .env.yarr.XXXXXXXX)"
trap 'rm -f "$TEMP_ENV"' EXIT
if [[ -f .env ]]; then
  grep -v '^YARR_TUNNEL_TOKEN=' .env > "$TEMP_ENV" || true
fi
printf 'YARR_TUNNEL_TOKEN=%s\n' "$YARR_TOKEN" >> "$TEMP_ENV"
chmod 600 "$TEMP_ENV"
mv "$TEMP_ENV" .env
unset YARR_TOKEN
echo "Saved connector credential in local .env (not in GitHub)."

if docker info >/dev/null 2>&1; then
  docker compose -f compose.yaml -f compose.yarr-vpc.yaml up -d --no-deps yarr-cloudflared
else
  sudo docker compose -f compose.yaml -f compose.yarr-vpc.yaml up -d --no-deps yarr-cloudflared
fi
echo "The connector has been started. Check the Yarr app's private connection test."
