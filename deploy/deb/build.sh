#!/usr/bin/env bash
# Build the yarr-media .deb:  bash deploy/deb/build.sh <version> <outdir>
# The package installs the same installer as yarr.media/install.sh plus a
# `yarr-media-setup` command; the server itself runs from the Docker image and
# updates nightly, so the .deb rarely needs to change.
set -euo pipefail
VERSION="${1:?version, e.g. 0.15.0}"
OUT="${2:?output directory}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
chmod 0755 "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/share/yarr-media" "$STAGE/usr/sbin" "$STAGE/usr/share/doc/yarr-media" "$OUT"
install -m 0755 "$ROOT/deploy/install.sh" "$STAGE/usr/share/yarr-media/install.sh"
cat >"$STAGE/usr/sbin/yarr-media-setup" <<'S'
#!/bin/sh
# Choose the media folder and (re)configure Yarr Media.
exec /usr/share/yarr-media/install.sh "$@"
S
chmod 0755 "$STAGE/usr/sbin/yarr-media-setup"
printf 'Yarr Media server package. Project home: https://yarr.media\n' >"$STAGE/usr/share/doc/yarr-media/README"
sed "s/@VERSION@/$VERSION/" "$HERE/control" >"$STAGE/DEBIAN/control"
for script in postinst prerm postrm; do install -m 0755 "$HERE/$script" "$STAGE/DEBIAN/$script"; done
dpkg-deb --root-owner-group --build "$STAGE" "$OUT/yarr-media_${VERSION}_all.deb" >/dev/null
echo "$OUT/yarr-media_${VERSION}_all.deb"
