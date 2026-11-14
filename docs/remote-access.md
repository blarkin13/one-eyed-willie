# Direct HTTPS remote access (optional, no added subscription)

**Status:** This is a prepared, opt-in configuration. It is NOT deployed, and remote access is NOT working until DNS and router setup are completed.

This mode does not depend on Cloudflare Tunnel or a VPN. It uses Caddy's automatic free HTTPS certificates and a password prompt in front of the existing application, which currently does not have built-in authentication.

## Requirements
- A router you can configure to forward TCP **443** to the NUC, and a home connection with a reachable public IPv4 address (not CGNAT). TCP 80 can also be forwarded for HTTP redirects and HTTP-based ACME checks but is optional when TLS-ALPN certificate verification on 443 works. UDP 443 is optional for HTTP/3.
- A hostname such as a free `your-choice.duckdns.org` name pointing to that public IP. This avoids changing any Humperdinck DNS records. The separate `workers.dev` public address, if used, will still need to reach this secure origin.
- If your public address changes, you need a free dynamic DNS update mechanism; this is not included yet.
- Ensure TCP 80/443 aren't already used by other software on the NUC.

## Security prerequisites
- **Do not** forward TCP 8787. The remote Compose file retains local port 8787 for home-network access; do not forward 8787 on your router.
- Set a strong password; four numeric digits are **not sufficient** for a public Internet service.
- Password authentication is temporary; future Android TV pairing will need device tokens instead.
- Basic authentication over HTTPS encrypts credentials in transit. The web app and metadata are behind Caddy.
- Do not store credentials in GitHub, chat messages, or uploaded files.
- Protect the `.env.remote` file using `chmod 600`.

## Setup (on the NUC, once router and DNS are ready)
```bash
cd /opt/one-eyed-willie/app
# Choose and enter a long password at the prompt, not on the command line.
read -rsp 'Remote access password: ' WILLIE_PASSWORD; echo
HASH=$(printf '%s' "$WILLIE_PASSWORD" | sudo docker run --rm -i caddy:2 caddy hash-password)
unset WILLIE_PASSWORD
umask 077
{
  printf 'WILLIE_HOSTNAME=YOUR_FREE_HOST.duckdns.org\n'
  printf 'ACME_EMAIL=YOUR_EMAIL_ADDRESS\n'
  printf 'WILLIE_USERNAME=willie\n'
  # Quotes prevent Compose treating hash dollars as variable interpolation.
  printf "WILLIE_PASSWORD_HASH='%s'\n" "$HASH"
} > .env.remote
unset HASH
chmod 600 .env.remote

# Only after changing DNS and router port forwarding:
sudo docker compose -f compose.yaml down
sudo docker compose --env-file .env.remote -f compose.remote.yaml up -d --build
```
Replace YOUR_EMAIL_ADDRESS in the local file with your own email (don't commit it).
Visit `https://YOUR_FREE_HOST.duckdns.org/health` from cellular data; authenticate and expect JSON.
Use `sudo docker compose --env-file .env.remote -f compose.remote.yaml logs https` if certificate issuance fails.

## Rollback to local mode
```bash
cd /opt/one-eyed-willie/app
sudo docker compose --env-file .env.remote -f compose.remote.yaml down
sudo docker compose -f compose.yaml up -d --build
```
Remove router forwarding and public DNS if disabling remote mode.

## Limitations
- If your ISP uses carrier-grade NAT or blocks inbound connections, this direct method will not work without changing network arrangements.
- Native browser Basic authentication is not a final Android TV sign-in method.
- This release has library catalog browsing, but media playback endpoints are not implemented yet.
- Remote bandwidth is limited by the NUC's upstream internet connection.
