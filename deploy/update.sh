#!/usr/bin/env bash
set -Eeuo pipefail

# Installed as a root-run systemd oneshot service. Never print secrets.
exec 9>/run/one-eyed-willie-updater.lock
flock -n 9 || exit 0

APP_DIR=/opt/one-eyed-willie/app
cd "$APP_DIR"

# Reuse Brian's already-authorized GitHub CLI credentials. The NUC needs
# outbound HTTPS only; no incoming SSH or GitHub webhook.
GH_TOKEN="$(runuser -u brian -- /snap/bin/gh auth token)"
export GH_TOKEN
test -n "$GH_TOKEN"

git_auth='!f() { printf "%s\\n" "username=x-access-token" "password=$GH_TOKEN"; }; f'
git -c safe.directory="$APP_DIR" -c "credential.helper=$git_auth" fetch --quiet origin main
unset GH_TOKEN

current="$(git -c safe.directory="$APP_DIR" rev-parse HEAD)"
target="$(git -c safe.directory="$APP_DIR" rev-parse origin/main)"
if [[ "$current" == "$target" ]]; then
  echo "One-Eyed Willie: no update ($current)"
  exit 0
fi

echo "One-Eyed Willie: updating $current -> $target"
# This directory is a deployment checkout; do not make local code edits here.
git -c safe.directory="$APP_DIR" reset --hard "$target"
if ! docker compose build; then
  echo "Build failed; restoring previous checkout"
  git -c safe.directory="$APP_DIR" reset --hard "$current"
  exit 1
fi
if ! docker compose up -d --no-build; then
  echo "Deployment failed; rolling back"
  git -c safe.directory="$APP_DIR" reset --hard "$current"
  docker compose up -d --build
  exit 1
fi

healthy=false
for i in $(seq 1 24); do
  if curl --silent --show-error --fail --max-time 3 http://127.0.0.1:8787/health >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 5
done

if [[ "$healthy" == true ]]; then
  echo "One-Eyed Willie: deployed $target"
else
  echo "Health check failed; restoring $current"
  git -c safe.directory="$APP_DIR" reset --hard "$current"
  docker compose up -d --build
  exit 1
fi
