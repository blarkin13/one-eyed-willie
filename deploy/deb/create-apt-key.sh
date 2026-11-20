#!/usr/bin/env bash
# One-time: create the key that signs the Yarr Media apt repository and store
# it as the APT_SIGNING_KEY secret of the GitHub repository. Run on your own
# computer (needs gpg and the GitHub CLI, signed in):
#   bash deploy/deb/create-apt-key.sh
# Keep the printed backup file somewhere safe: if this key is lost, every apt
# user has to re-import a new key.
set -euo pipefail
command -v gpg >/dev/null || { echo "Install gpg first (macOS: brew install gnupg)" >&2; exit 1; }
command -v gh >/dev/null || { echo "Install the GitHub CLI first (macOS: brew install gh)" >&2; exit 1; }
export GNUPGHOME; GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --quiet --passphrase '' --quick-gen-key "Yarr Media apt repository <apt@yarr.media>" ed25519 sign 5y
BACKUP="$HOME/yarr-media-apt-signing-key.asc"
umask 077
gpg --batch --armor --export-secret-keys >"$BACKUP"
gh secret set APT_SIGNING_KEY -R blarkin13/one-eyed-willie <"$BACKUP"
echo "Saved APT_SIGNING_KEY to GitHub. Backup of the private key: $BACKUP (keep it safe, never share it)."
