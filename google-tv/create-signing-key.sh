#!/usr/bin/env bash
# One-time: create the permanent key that signs the Yarr Media apps (Google TV
# and Android phone) and store it as GitHub secrets, so every build installs
# over the previous one and keeps the app's data (server address, sign-in).
# Run on your own computer (needs Java's keytool and the GitHub CLI, signed in):
#   bash google-tv/create-signing-key.sh
# Keep the two files it creates safe (a password manager is ideal). If the key
# is lost, every installed app has to be uninstalled before it can be updated.
set -euo pipefail
REPO="${YARR_REPO:-blarkin13/one-eyed-willie}"
KEYSTORE="${YARR_KEYSTORE_OUT:-$HOME/yarr-media-app-signing.p12}"
PASSFILE="${KEYSTORE%.p12}-password.txt"

if ! keytool -help >/dev/null 2>&1; then
  for jdk in "$(brew --prefix openjdk 2>/dev/null)/bin" /usr/local/opt/openjdk/bin /opt/homebrew/opt/openjdk/bin; do
    [ -x "$jdk/keytool" ] && PATH="$jdk:$PATH" && break
  done
fi
keytool -help >/dev/null 2>&1 || { echo "Install Java first (macOS: brew install openjdk)" >&2; exit 1; }
command -v gh >/dev/null || { echo "Install the GitHub CLI first (macOS: brew install gh)" >&2; exit 1; }

umask 077
if [ -e "$KEYSTORE" ]; then
  [ -s "$PASSFILE" ] || { echo "$KEYSTORE exists but $PASSFILE is missing; not touching either." >&2; exit 1; }
  echo "Using the existing key in $KEYSTORE (it is never replaced)."
  PASS="$(cat "$PASSFILE")"
else
  PASS="$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-32)"
  keytool -genkeypair -keystore "$KEYSTORE" -storetype PKCS12 -alias yarr-media \
    -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Yarr Media, O=Yarr Media" \
    -storepass "$PASS" -keypass "$PASS" -noprompt >/dev/null
  printf '%s\n' "$PASS" >"$PASSFILE"
fi
keytool -list -keystore "$KEYSTORE" -storetype PKCS12 -storepass "$PASS" -alias yarr-media >/dev/null

base64 <"$KEYSTORE" | tr -d '\n' | gh secret set ANDROID_KEYSTORE_BASE64 -R "$REPO"
printf '%s' "$PASS" | gh secret set ANDROID_KEYSTORE_PASSWORD -R "$REPO"
echo
echo "Saved ANDROID_KEYSTORE_BASE64 and ANDROID_KEYSTORE_PASSWORD to $REPO."
echo "Back up these two files somewhere safe and never share them:"
echo "  $KEYSTORE"
echo "  $PASSFILE"
echo "SHA-256 fingerprint (CI prints the same one for every signed build):"
keytool -list -v -keystore "$KEYSTORE" -storetype PKCS12 -storepass "$PASS" -alias yarr-media | grep -i 'SHA256:' | head -1
