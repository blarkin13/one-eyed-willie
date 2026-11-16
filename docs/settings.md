# Settings organization

The gear opens **Settings** at /settings. The four categories are:
- **General** (/settings/general) — playback, maintenance scheduling and manual runs, remote access preferences, navigation layout, and server status.
- **Library** (/settings/libraries) — create, rename and remove collections, manage media folders, choose a collection icon/font, and control per-library sidebar visibility.
- **Metadata** (/settings/metadata) — metadata provider configuration and matching.
- **Connections** (/settings/connections) — Radarr, Sonarr, SABnzbd, OpenSubtitles, Plex.

Existing /settings/playback, /settings/maintenance, and /settings/remote remain available as detail pages and are reached from General.

## Library folders and safety

Existing libraries keep their original ID, kind, media rows, added dates and watch progress. On startup, each library's previous single root is backfilled into \`library_folders\`. Future scans index files from **all** configured roots under the read-only media mount. \`media.source_root\` records which root was used to parse each movie or show and prevents multi-root TV episodes from losing their correct series/season grouping.

New folders must be readable directories under \`MEDIA_ROOT\`. The UI prevents selecting a duplicate or nested root that overlaps any existing library folder. At least one folder must remain per library. Scans do not edit video files. Removing a folder leaves its old entries in the catalog until a successful rescan; those entries and their playback progress are removed when the scan confirms they no longer belong to the library. Deleting an entire library likewise removes its catalog and progress, never source files.

Library kind remains immutable after creation; moving movie files between collection types is not attempted as part of a cosmetic edit. Names, icons and fonts can be edited without rescanning. Icons and fonts are from fixed allowlists, never arbitrary HTML, CSS or paths.

## Sidebar

Home and Settings cannot be hidden; Settings stays last. Other system destinations and custom library links can be hidden and reordered on General. Per-library appearance is stored on each library, while layout ordering is stored in \`app_settings\`. New libraries appear in the ordered menu without requiring users to edit a JSON file. Renaming an existing standard Movies or TV Shows library to a custom name adds a dedicated sidebar entry; a standard collection shares its icon and font with the existing Movies or TV Shows navigation item.

## Acceptance tests

1. Open Settings from the gear on desktop and mobile, then enter all four pages.
2. Change playback, save it, reload General and confirm the value persists.
3. Set maintenance jobs, initiate a run, then review the existing Maintenance detail/history page.
4. Save a remote HTTPS URL, reopen General, and verify that only saved preferences change; no claim that router or Cloudflare is provisioned automatically.
5. Move and hide sidebar entries, save, reload on desktop/mobile and check order/focus.
6. Rename a library, choose a different icon/font, reload the app and confirm updated navigation.
7. Add a second TV folder containing more episodes from an existing show; rescan and verify episodes group under the same show and retain their media IDs.
8. Remove that folder; confirm source files remain untouched and the catalog updates after a scan.
9. Attempt to select a directory outside /media, duplicate another root, or remove the final library folder; confirm safe rejections.
