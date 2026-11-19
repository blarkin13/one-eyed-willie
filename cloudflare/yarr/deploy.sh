#!/usr/bin/env bash
# Deploy the yarr.media account Worker and make sure the remote-access signing
# key exists. Run from anywhere:  bash cloudflare/yarr/deploy.sh   (add "dev" for yarr-dev)
set -euo pipefail
cd "$(dirname "$0")"
WRANGLER=(npx --yes wrangler@4)
ENV_ARGS=(--env "")
NAME=yarr
SITE=https://yarr.media
if [[ "${1:-}" == "dev" ]]; then ENV_ARGS=(--env dev); NAME=yarr-dev; SITE=https://yarr-dev.larki-brian.workers.dev; fi

"${WRANGLER[@]}" whoami >/dev/null 2>&1 || "${WRANGLER[@]}" login

# Code, bindings, domains and cron. --keep-vars leaves dashboard variables alone;
# secrets are never changed by a deploy.
"${WRANGLER[@]}" deploy --keep-vars "${ENV_ARGS[@]}"

# Create the pass signing key once. It goes straight from this machine into
# Cloudflare and is never printed or saved.
if ! "${WRANGLER[@]}" secret list "${ENV_ARGS[@]}" 2>/dev/null | grep -q '"PASS_SIGNING_KEY"'; then
  node tools/new-pass-key.mjs | "${WRANGLER[@]}" secret put PASS_SIGNING_KEY "${ENV_ARGS[@]}"
fi

echo
echo "Checking $SITE ..."
sleep 3
curl -fsS "$SITE/health"; echo
curl -fsS "$SITE/api/passes/keys"; echo
