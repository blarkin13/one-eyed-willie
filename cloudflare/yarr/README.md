# Yarr account platform — development

Yarr is a **working name**, not a final domain decision. Public staging URL: `https://yarr.larki-brian.workers.dev`.

## Current Cloudflare resources

- Worker `yarr`: independent of `one-eyed-willie`, with public preview home page and account page
- D1 database `yarr-accounts` bound as `ACCOUNTS`
- Account records: users, registered servers, devices, hashed sessions, and one-time OAuth flows
- Google Sign-In implemented but deliberately disabled until its own Google OAuth credentials are securely configured
- **No media proxy** or automatic home-server access; `one-eyed-willie` and the Docker install stay unchanged

## Google sign-in activation (not complete)

In Google Cloud Console create/select a project, configure **Google Auth Platform** with External audience and testing users, then create a **Web application** OAuth client.

- Authorized redirect URI: `https://yarr.larki-brian.workers.dev/auth/google/callback`
- Authorized JavaScript origin, if required: `https://yarr.larki-brian.workers.dev`
- Required scopes: `openid email profile`
- Store `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` as **secrets on the yarr Worker**. Never put them in Git, chat, or frontend code.
- In Google Auth Platform > Audience, keep the client in testing with only approved test users until verified/ready for public launch.

Once correctly configured, the public landing page reveals Google Sign-In and `/account` works as the authenticated dashboard. Future production domain requires updating the trusted `SITE` constant (or migrating it to a validated env setting), consent screen authorized domain and callback URL; do not redirect between hostnames without retesting cookies and OAuth.

## Implemented login security

- Authorization code with PKCE S256, opaque state cookie, nonce, one-time D1 transaction, 10-minute expiry
- Token exchange is server-side; cryptographically verify Google's ID token using Google JWKS / RS256, issuer, audience, nonce, expiry and verified email
- Store account identity by Google's immutable `sub`, not email
- Cryptographically random session secret goes only in an HttpOnly, Secure, SameSite=Lax cookie; only SHA-256 hash is stored in D1; expires after 7 days
- Sign-out revokes the server-side session; POST with same-origin check
- `/api/me` returns only authenticated profile data; server operations remain disabled

## Not ready for public users

- Google Cloud application credentials and real end-to-end login validation
- Secure pairing/ownership proof for an installed media server
- CSRF, authorization and origin checks on all future state-changing endpoints
- Safe remote connectivity, per-user server isolation, device-code TV pairing, revocation, rate limits, privacy/legal review
- Installers and server onboarding built for independent installations and not hard-coded owner paths

## No-change compatibility rule

**Never copy the old `one-eyed-willie` Worker proxy to Yarr**: it has one hardcoded origin pointing at the owner's server. Keep media and integration credentials inside each self-hosted instance. Do not transport video data through the account Worker.

## Validation

Cloudflare accepted the Worker deployment and binding. Actual Google OAuth sign-in has **not** been tested because Google client ID/secret are not configured. Browser-level live smoke checks remain outstanding.

## Step 3 — server registration (deployed 2026-11-18)

- Google Client ID and encrypted Client Secret are configured on the Worker; the user reported successful sign-in.
- Signed-in account dashboard accepts a server display name and optional private LAN URL and/or public HTTPS origin.
- The database now has an optional `servers.local_url` column (ALTER TABLE migration applied). Current `schema.sql` includes it.
- Account-owned `GET /api/servers` lists only that user's registrations.
- POST `/account/servers` supports create/remove using same-origin checks and owner-scoped SQL; limit 5 registrations per account.
- Registered server URLs are *inert account settings*. They are never fetched or proxied. Status remains `pending` until secure server ownership pairing is built.
- The account Worker still cannot view or stream media; the original Docker server and legacy Worker are untouched.
- Cloudflare confirmed Google credentials and D1 binding remained attached after deployment.
- A full end-to-end browser CRUD and two-user isolation test is still needed before public release.

## Step 4 — application entry point and simplified registration

- Public website and sign-in: `https://yarr.larki-brian.workers.dev/`
- App entry address: `https://app-yarr.larki-brian.workers.dev/`
- **Temporary deliberate redirect:** app-yarr sends users to `https://yarr.larki-brian.workers.dev/app`, where the established secure host-scoped Google session can be checked. The app is not yet independently hosted on the second hostname.
- Signed-in `/app` is an isolated *shell* listing only the account's own server registrations. It does not stream media or read local libraries.
- Normal server registration requires a **name only**. Both local and remote address inputs are removed. Records remain `pending`; pre-existing saved addresses are not displayed or used for access.
- The server-side create route ignores address fields if malicious/older clients submit them. Neither account Worker nor app entry Worker ever fetches user-supplied origins.
- Future pairing should use a one-time ownership proof initiated by the installed server and a secure outbound connection. That requires a planned backward-compatible server update.
- Do not claim the second app hostname has authenticated independent application hosting until cross-host sign-in is implemented and verified.
- Both Workers were accepted by Cloudflare and workers.dev routing is enabled; browser end-to-end visual testing remains outstanding.

## Step 5 — account-to-server pairing foundation (2026-11-18)

Cloudflare:
- Deployed `POST /api/pairing/start` (anonymous server start, rate limited), `GET /api/pairing/status` (server polling secret), and `POST /account/pair` (Google-account-authenticated claim).
- Each pairing code is 16 characters in a non-ambiguous alphabet, expires in ten minutes, and is single-use. D1 stores the **hash** of the code and polling secret, never their plaintext.
- A Google-signed-in user can claim a pending code, creating an owned server record with a unique persistent server identity. The D1 account database is independent of the local media database.
- Initial pairing tables and unique server identity index were applied to `yarr-accounts`, with the schema reflected in `schema.sql`.
- Anonymous start and code guessing have per-source-IP rate limits. Production security review and two-user race/load testing are still required.

Self-hosted server (development branch only):
- `server/connections.py` already persists `server_id`; this ID is reused.
- `server/yarr_pairing.py` uses a random, expiring code, random polling secret, TLS outbound calls and file permission `0600` for private state. It does not store Google credentials.
- `server/main.py` includes optional Yarr pairing router.
- `server/remote_settings.html` adds a **Connect to Yarr** button, displays the code, opens account claim screen and checks the status.
- Server-side UI requires same-origin POST before initiating pairing. Local network access is not equivalent to authenticated administration; local auth and TLS configuration must be reviewed before production.
- No existing Docker server has been updated and the new pairing code is not on `main`.

Restrictions:
- A paired server is *not remotely accessible*. No streaming, per-user library authorization, or automatic network tunneling has been enabled.
- Existing manual Remote Access settings are preserved; pairing introduces a separate opt-in route.
- The browser and app Worker do not proxy private media.
- No end-to-end physical server test, automated Python tests or two-account negative tests have passed yet.
- Before releasing: test code expiry, reuse, concurrent claims, IP limits, repeat linking, local cross-origin rejection, offline behavior, and server restart persistence.

## Connection status stage — deployed 2026-11-18

- The Yarr Worker now accepts only `POST /api/connection/heartbeat` with a 256-bit server bearer credential and exposes `GET /api/connection/status` only to a signed-in owner. The heartbeat writes `last_seen_at` to D1; online is a short freshness window (150 seconds), *not* a functioning remote media connection.
- D1 columns `servers.connection_secret_hash` and `servers.last_seen_at` were applied and are present in the checked-in schema.
- Initial pairing stores a SHA-256 credential hash in the corresponding owner-linked server record; plaintext remains only in the server's 0600 local pairing-state file. The old server account registration is preserved.
- Servers paired before this update need **Refresh secure connection** in the installed server's Settings → General or Settings → Remote Access. It generates a new short-lived code that the existing owner claims. The database allows the same owner to rotate its credential, but prevents a different account from claiming that identity.
- The installed server sends a minimal authenticated heartbeat once per minute through outbound HTTPS. Local playback is unaffected by internet or account-service outages.
- The worker and server code are in separate git branches: web/Cloudflare code stays on `feature/yarr-multiuser-foundation`; server code was committed to `main`.

### Tunnel and remote streaming boundary

No tunnel was provisioned. The Cloudflare account currently has only an unrelated pre-existing tunnel, which must not be reused, and no Yarr-owned DNS zone. A future proper route needs a Yarr-owned hostname or an explicitly approved alternative, a separate customer tunnel with limited origin routing, and strict account/device authorization *before* an installed media server can be exposed.

A common `app-yarr.larki-brian.workers.dev` login does not itself make a private origin reachable. Serving video from a personal server requires a separately authenticated data connection; don't route video through the Yarr account Worker or through another customer's origin.

### Acceptance checks still pending

- Restart the server on updated `main`; verify the reauthorization button appears for an older paired server.
- Generate code → claim while logged into the original account → verify local code is not duplicated and the server stores the credential.
- Verify owner-scoped status becomes online after the next heartbeat; offline after it stops for 150 seconds.
- Negative tests: other account attempting claim, incorrect/expired codes, multiple owners, token replay after rotation, forged heartbeat, revoked/removed server and cross-origin form posts.
- Verify restart persistence and outage behavior. GitHub CI execution/installed server verification are outstanding.

## Workers VPC private health pilot (2026-11-18)

Cloudflare created a dedicated remote-managed Tunnel named `yarr-gazorpazorp-vpc` and a Workers VPC HTTP Service named `yarr-gazorpazorp-api` routed to the Docker hostname `one-eyed-willie` on port 8787. Neither has a public hostname.

The `yarr` Worker has the `YARR_PRIVATE_API` VPC Service binding and `YARR_PRIVATE_SERVER_ID` owner-check variable. Authenticated `GET /api/private/health` verifies that the logged-in account owns the pinned, paired server **before** fetching the fixed path `/health` over Workers VPC. All user-provided URLs, paths and other server destinations are ignored. Returned health information is sanitized; no video or media metadata is relayed.

This is a **single-server test** and must not be presented as a scalable multi-customer network design. The Cloudflare Tunnel is not connected until the local connector is run with its private token; the token must never be copied into GitHub or chat. Local Docker opt-in code and installation details: `compose.yarr-vpc.yaml`, `deploy/setup-yarr-vpc.sh`, `deploy/yarr-vpc-test.md` on `main`.

The Workers VPC binding must be preserved during every subsequent Worker deployment. Do not use a general-purpose VPC Network binding or proxy arbitrary private paths. A scalable, per-customer security model, origin authentication, and revocation are mandatory before media access is implemented.

## Hosted personal media library pilot (2026-11-18)

`https://yarr.larki-brian.workers.dev/app` now renders an authenticated, read-only **Movies** and **TV Shows** browser with artwork, title search, sorting, watched indicators and a compact details panel. It loads data from the user's paired private server using:

- `GET /api/private/catalog?kind=movies|tv&offset=N&sort=title|recent|added|year|length|rating&search=...`
- `GET /api/private/artwork/thumb/<64-lowercase-hex>` (and similarly for full artwork)

Both routes **authenticate the Yarr session**, check in D1 that the current account owns the pinned paired server, and verify the tunneled origin's `/api/server/info` identity matches D1 before requesting any data. The catalog route strictly accepts enumerated search, pagination and sort arguments, fetches only the existing read-only `/api/catalog` local endpoint with an enforced page size, caps the response size, and projects safe display fields. File paths, raw episode file lists, sources and integration secrets are never returned to the web client.

Artwork is restricted to valid hash-based local artwork paths, approved MIME types, and a 5 MB maximum. Both routes disable shared caching; the browser also uses no-store. No arbitrary URL or path proxy exists. Browser scripts run under a strict same-origin CSP; HTML is not cached.

The frontend automatically loads additional catalog pages as the user scrolls. Clicking a poster displays title, year, rating, genres, seasons and watched status. Playback controls are deliberately absent.

### Test and limitations

1. Confirm the paired tunnel is healthy.
2. Sign into the Yarr app with the Google account owning Gazorpazorp.
3. Click Movies, TV Shows, Search and Sort; verify posters render and media titles match the local One-Eyed Willie libraries.
4. Sign out and ensure the JSON endpoints return 401; confirm the site cannot serve media without login.
5. Ensure another account cannot list this user's server library; verify origin identity mismatch returns no data.

**Pilot limitation:** `YARR_PRIVATE_SERVER_ID` and `YARR_PRIVATE_API` currently target only the test Gazorpazorp installation; this is not dynamically provisioned for other customers yet. The previous `/api/private/health` test remains available.

This is a **library metadata and artwork preview only**, not remote playback. Before launch, implement scalable multi-tenant VPC routing, signed per-origin API authorization, an origin-facing revocation workflow, per-device/session controls, video transport and range/HLS/subtitle support.

## Complete hosted One-Eyed Willie app pilot (2026-11-18)

The standalone hosted Movies/TV catalog viewer was removed from Yarr. The existing self-hosted frontend is now the only application UI. No duplication of local movie, TV, settings, or playback templates is intended.

**Authenticated routing:** `/app`, `/` (for signed-in users), `/movies`, `/tv`, `/watch/{id}`, `/assets/*`, application `/api/*` endpoints and the other original application paths now flow to the paired `one-eyed-willie:8787` through the private `YARR_PRIVATE_API` service. For signed-out visitors, `/` remains Yarr's marketing landing page. Yarr's `/account`, Google sign-in/logout, and account/pairing/connection endpoints remain separately handled by Yarr. `/api/private/*` old preview APIs remain unavailable.

**Authorization and isolation:** Before *every* proxied request, the Worker validates the Yarr session, checks in D1 that the signed-in user owns the configured paired server, and checks the tunneled server identity against the paired installation. Destination host is fixed (no arbitrary URL proxy); browser cookies and authorization headers are not forwarded to the NUC. State-changing requests require same-origin browser evidence, and origin/referrer are reset to the local server only *after* session and ownership checks.

**Streaming support:** Proxy forwards GET, HEAD, POST, PUT, PATCH and DELETE, restricts request size by declared Content-Length (with Cloudflare's platform request-size limit as a second safeguard), allows video Range/If-Range, and streams response bodies without buffering. It forwards media, playlist and HLS segment content-type/length/range headers where appropriate, strips upstream cookies and forwarding headers, blocks off-origin redirects and shared caching. This is a **single-server staging bridge**: in this pilot media bytes travel *through* the account Worker. That is **not** the desired production data-plane architecture. Before customer launch replace this with separately authenticated and authorized server-to-client media transport, check Cloudflare plan/usage limits and billing, and implement scale-safe multi-tenant routing.

**Test checklist requiring a signed-in browser:**
- `/app` displays the actual local Home page, not the temporary hosted viewer.
- Home → Movies → TV Shows → show → season → episode and browser Back all work.
- Posters, backdrops, CSS, icons, video player assets and API calls load under the Yarr host, without CORS errors.
- Direct-play video responds with 206 + Content-Range for byte-range requests. HLS manifests and segments stream. Verify seek, subtitles, pause/resume, Continue Watching and watched/unwatched actions.
- Remote Settings and other mutations work only while signed in; an unsigned visitor receives a redirect for pages or 401 for APIs. Cross-origin mutations must fail 403.
- Sign-out invalidates the online session; attempts to view pages and streams afterwards must fail.
- Other Yarr accounts cannot view the bound server; the current pilot is deliberately pinned to Gazorpazorp.
- Check latency, bandwidth, Worker billing and any Cloudflare service restrictions before putting real media traffic through the staging Worker regularly.

**Deployment:** Latest Worker code was published to the existing `yarr` service while retaining Google OAuth, D1, VPC and tunnel secrets. No local NUC update is required because this reuses all existing local page and media endpoints. The full live signed-in browser checks have not yet been completed.
