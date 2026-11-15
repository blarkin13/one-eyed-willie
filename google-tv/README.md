# One-Eyed Willie for Android TV / Google TV

This is the **actual One-Eyed Willie server interface** running inside a TV-optimized Android WebView—not a separately designed Android catalog. Home, Movies, TV Shows, Explore, details, matching, and Settings are rendered by the server. Layout and branding changes shipped to the server appear in the Android TV app without reimplementing screens.

The TV launcher icon is derived from the user-provided black-and-white pirate ship PNG. The image is bundled locally so the launcher works offline.

## Build and install

1. Open `google-tv/` in Android Studio (JDK 17) and build the app's debug APK, or use GitHub Actions' **Google TV APK** workflow.
2. Install with `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
3. Enter your server URL on the first run. The app saves it and loads the full server interface on subsequent launches.
4. A TV remote's D-pad navigates the actual server links and buttons, with focus indicators. Back returns to prior pages.

## Playback

Selecting Play in the browser interface switches to the existing native Media3 player to avoid Android WebView codec restrictions. As a result the **catalog and navigation match the server exactly**, but native playback controls may still differ from the browser player. Test resume, captions, seeking, and media compatibility on the target TV before relying on feature parity.

The Android client is LAN-first and currently supports HTTP for local media servers. Do not expose an unauthenticated server to the public internet. Native external metadata links are intentionally blocked from navigating inside the trusted embedded server view.

## Signing

The debug APK is not signed with a production release key. A debug APK with a new signing certificate may not update an already-installed APK with the same application ID. Do not uninstall a signed production installation without first considering its saved server settings.
