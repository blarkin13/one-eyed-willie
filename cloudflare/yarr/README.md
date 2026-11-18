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
