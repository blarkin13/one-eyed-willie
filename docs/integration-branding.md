# Official integration logos

One-Eyed Willie includes the unmodified Radarr and Sonarr SVG logos as local UI resources, solely to identify their integrations. Logos are not replacements for One-Eyed Willie's own branding.

- Radarr source: https://github.com/Radarr/Radarr/blob/develop/Logo/Radarr.svg
- Sonarr source: https://github.com/Sonarr/Sonarr/blob/develop/Logo/Sonarr.svg

Both files are distributed in the server image under `server/radarr-official.svg` and `server/sonarr-official.svg`, served through the allowlisted `/assets/brand/{radarr|sonarr}.svg` endpoint. They are used in the sidebar, media-manager tabs, integration connection UI and media-manager add action. No external network request or CSS recoloring is required to display them.

Radarr and Sonarr names and logos belong to their respective owners. Their inclusion identifies supported third-party integrations and does not imply sponsorship or endorsement.
