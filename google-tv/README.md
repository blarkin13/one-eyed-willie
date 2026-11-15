# One-Eyed Willie for Google TV

Native Android TV / Google TV client (Kotlin + Compose, Media3). This first milestone is LAN-first.

## Build and install
1. Open the `google-tv/` folder in Android Studio (JDK 17).
2. Let Android Studio sync Gradle, then select `app` and **Build APK**.
3. Install the debug APK on a Google TV device using Android Studio or `adb install app/build/outputs/apk/debug/app-debug.apk`.
4. Start the server on the same network and enter `http://SERVER-IP:8787` in the app.

The TV launcher entry is included. The app connects to `/health`, browses `/api/catalog`, drills into TV seasons and launches a fullscreen Media3 player using the server stream endpoint.

## Current limitations
- Basic text tiles only. Poster art, D-pad focus animations and redesigned home shelves are next.
- No discovery/pairing yet; enter the local server address manually.
- HTTP cleartext is enabled for LAN servers. Do not expose an unauthenticated server or client over the public internet.
- No media transcoding: codec support depends on Google TV device and source format.
- Progress/watched sync and resume still require wiring to `/api/playback/progress`.
- No CI build validation has yet been run on this Android project.
