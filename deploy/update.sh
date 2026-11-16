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

# Preserve the existing remote HTTPS deployment and Intel GPU device bindings.
# Plain docker compose previously silently recreated the app without the GPU.
compose_files=(-f compose.yaml)
compose_env=()
if docker container inspect one-eyed-willie-https >/dev/null 2>&1; then
  # Remote setup stores its Caddy hostname/password hash in .env.remote, not
  # .env. Without --env-file the compose config check fails on every update.
  # Never print the file or expose its secrets in command-line arguments.
  if [[ ! -f "$APP_DIR/.env.remote" ]]; then
    echo "HTTPS mode detected but $APP_DIR/.env.remote is missing" >&2
    exit 1
  fi
  compose_files=(-f compose.remote.yaml)
  compose_env=(--env-file "$APP_DIR/.env.remote")
fi
if [[ -c /dev/dri/renderD128 ]]; then
  export WILLIE_RENDER_GID="$(stat -c '%g' /dev/dri/renderD128)"
  compose_files+=(-f compose.gpu.yaml)
fi
compose() { docker compose "${compose_env[@]}" "${compose_files[@]}" "$@"; }

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
if ! compose config --quiet || ! compose build; then
  echo "Build failed; restoring previous checkout"
  git -c safe.directory="$APP_DIR" reset --hard "$current"
  exit 1
fi
if ! compose up -d --no-build; then
  echo "Deployment failed; rolling back"
  git -c safe.directory="$APP_DIR" reset --hard "$current"
  compose up -d --build
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
  compose up -d --build
  exit 1
fi
