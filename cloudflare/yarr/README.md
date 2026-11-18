# Yarr multi-user foundation (staging)

The product name/domain are **not finalized**. `yarr` is the requested staging Worker name, not a domain decision.

## Provisioned
- Cloudflare Worker: `yarr`, separate from production `one-eyed-willie`
- Cloudflare D1: `yarr-accounts`, binding `ACCOUNTS`
- Account schema: users, servers, devices and hashed sessions
- Worker responds to `/health` and `/__edge/health`; login and account APIs return 503 until implemented.
- **No media forwarding**: the existing Worker points at the owner's server and MUST NOT be blindly copied for multi-user access.

## Required before enabling sign-in
1. Create Google OAuth application and configure approved redirect URI for the eventual account domain.
2. Implement OIDC authorization-code flow with PKCE, nonce/state, Google ID token verification and secure HttpOnly session cookies (store only session token hashes).
3. Implement ownership checks on every user/server/device route and CSRF protection on mutations.
4. Implement secure one-time server claim/pairing with proof of possession, explicit user consent, server-side verified endpoint allowlisting (prevent SSRF), and revocation.
5. Implement TV device-code pairing with expiring, one-time tokens, rate limits and authorization scopes. No credentials typed on TV.
6. Add account UI. Keep each self-hosted server's media catalog, Radarr/Sonarr/SABnzbd credentials, and playback data on that server.
7. Do not stream media through Workers. Use secure direct connections from the devices to their paired self-hosted server.
8. Add abuse controls, data deletion behavior, tests, and production auth review before exposing to public users.
9. Update server installer configuration to avoid hardcoded owner-specific paths and hostname; no forced migration of existing installation.

## Deployment
This branch contains source of the staging account Worker and initial D1 schema. The Worker was initially uploaded through the Cloudflare API. Next deployments should be reproducible from source and preserve the account DB binding.

**Do not deploy the current `one-eyed-willie` proxy code into `yarr`.** It hardcodes a single home-server origin, and its Basic Auth is not multi-tenant identity management.
