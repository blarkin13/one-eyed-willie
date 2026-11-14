# Remote Access settings

Open **Settings → Remote Access** in One-Eyed Willie.

- Enter the public IPv4 address of the home router. This value is **stored privately on the NUC** in `/data/remote-settings.json`; it is not hardcoded in the source.
- Enter the preferred public application URL (for example, a `workers.dev` URL). The application validates HTTPS URLs.
- See the automatically derived `<public-ip-with-dashes>.sslip.io` origin hostname for a free direct HTTPS approach.
- See the local connection, required router forwarding, and whether setup is verified.

**This UI saves configuration only.** It never attempts UPnP port forwarding, runs Docker commands, creates Cloudflare resources, or reports an untested remote URL as working. The app currently has no native authentication; do not publicly expose port 8787. HTTPS and authentication are required before enabling remote access.

Future milestones will make password setup, secure origin activation, external reachability checks, and revocable Android TV device pairing controllable through this same Settings screen.
