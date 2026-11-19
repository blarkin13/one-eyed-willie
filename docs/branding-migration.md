# Yarr Media rebranding and compatibility notes

The product and all new user-facing copy use **Yarr Media**. The original
repository, installation, app, and protocol names have deliberately **not**
been renamed as part of the branding change.

## New display name
- Web app titles, navigation, metadata views, settings, and server description: Yarr Media
- Android TV launcher and app user-facing messages: Yarr Media (requires a rebuilt APK)
- Documentation headings, support messages, and updater descriptions: Yarr Media
- The public Yarr website already displays Yarr Media

## Stable identifiers — do not bulk-rename
- GitHub repo: `blarkin13/one-eyed-willie` — cloning URLs, CI, and updater references rely on it
- Install directory: `/opt/one-eyed-willie` — updater, mounts, and service files rely on it
- Docker Compose service/container: `one-eyed-willie` — Cloudflare Workers VPC
  origin URLs and other Compose files use this name
- Android application ID and Kotlin namespace: `studio.oneeyedwillie.tv`.
  Changing it would create a *different* app, not an upgrade
- Health response protocol key: `application: one-eyed-willie`.
  Server discovery and Cloudflare checks must continue working with old clients
- TV WebView user-agent token: `OneEyedWillieTV/1`, and native
  `oewtv:` message protocol. These are compatibility identifiers
- Existing persisted `oew-*`, `willie-*`, and `WILLIE_*` keys,
  SQLite paths, Android preferences, and third-party client IDs
- Previously deployed Cloudflare Worker URLs containing `one-eyed-willie`
  and references to the existing GitHub path. A URL migration requires a
  separate rollout and redirects, not a search-and-replace
- Third-party HTTP User-Agent strings may be application/provider-registered;
  preserve them until each integration is validated

If a technical rename becomes necessary, handle it as a separate migration with
compatibility aliases, data migration, installed-client tests, and a rollback plan.

## Deployment
The web UI rename requires the server to deploy the new `main` commit.
The Android app launcher name requires rebuilding/installing the new APK; the
unchanged application ID allows it to replace the currently installed app,
provided the signing certificate is also unchanged. The app title in a store
listing must be updated separately in the relevant store console.
