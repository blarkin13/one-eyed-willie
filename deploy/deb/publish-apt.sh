#!/usr/bin/env bash
# Add .deb files to the signed apt repository kept on the apt-repo branch.
#   APT_SIGNING_KEY=<armored private key> bash deploy/deb/publish-apt.sh <repo-dir> <deb>...
# Served at https://yarr.media/apt (the yarr.media Worker reads this branch).
set -euo pipefail
REPO="${1:?repository directory}"; shift
[[ -n "${APT_SIGNING_KEY:-}" ]] || { echo "APT_SIGNING_KEY is not set" >&2; exit 1; }
export GNUPGHOME; GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
printf '%s\n' "$APT_SIGNING_KEY" | gpg --batch --quiet --import
KEYID="$(gpg --batch --list-secret-keys --with-colons | awk -F: '/^sec/{print $5; exit}')"
mkdir -p "$REPO/pool/main/y/yarr-media"
cp "$@" "$REPO/pool/main/y/yarr-media/"
cd "$REPO"
gpg --batch --export "$KEYID" >yarr-media.gpg
gpg --batch --armor --export "$KEYID" >yarr-media.asc
for arch in amd64 arm64; do
  mkdir -p "dists/stable/main/binary-$arch"
  apt-ftparchive --arch "$arch" packages pool >"dists/stable/main/binary-$arch/Packages"
  gzip -9nkf "dists/stable/main/binary-$arch/Packages"
done
apt-ftparchive \
  -o APT::FTPArchive::Release::Origin="Yarr Media" -o APT::FTPArchive::Release::Label="Yarr Media" \
  -o APT::FTPArchive::Release::Suite=stable -o APT::FTPArchive::Release::Codename=stable \
  -o APT::FTPArchive::Release::Architectures="amd64 arm64" -o APT::FTPArchive::Release::Components=main \
  release dists/stable >dists/stable/Release
rm -f dists/stable/InRelease dists/stable/Release.gpg
gpg --batch --yes --default-key "$KEYID" --clearsign -o dists/stable/InRelease dists/stable/Release
gpg --batch --yes --default-key "$KEYID" -abs -o dists/stable/Release.gpg dists/stable/Release
