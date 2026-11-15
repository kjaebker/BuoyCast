# Security

## What BuoyCast protects, and what it doesn't

BuoyCast is meant to run on a trusted home network. **It has no login.**
Anyone who can reach the Pi on your network can open the dashboard and do
everything it can do: start and end workouts, delete them, reboot the Pi,
install updates, read logs, and send workouts to Strava or your export
endpoint.

- **Don't expose BuoyCast to the internet**, for example by port-forwarding
  8080 on your router. If you want remote access, use a VPN such as
  Tailscale or WireGuard, or put a reverse proxy with its own login in
  front of it. Add the proxy's host name to `[server] allowed_hosts`.
- **Guest or shared networks:** everyone on the network can control the
  rower. Put the Pi on a network only you use.

What BuoyCast does block is **other websites** using your browser to control
the Pi. Without that protection, a page you happen to have open could
quietly send commands such as "reboot" or "delete workout". BuoyCast:

- rejects POST, PUT, PATCH and DELETE requests and WebSocket connections
  that come from a page on another site, and sends no CORS headers, so other
  sites can't read its responses
- only answers to host names that can't belong to an attacker (IP
  addresses, `*.local` names, single-label names such as `raspberrypi`, and
  whatever you list in `[server] allowed_hosts`). This blocks DNS rebinding
  attacks.

Scripts and command-line tools such as `curl` keep working, because they
don't send a browser `Origin` header.

**Secrets** stay on the Pi: the Strava client secret and the export token
are in `/opt/buoycast/config.toml`, and the Strava tokens are in its SQLite
database. The dashboard never shows them.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub. On the repository,
go to **Security → Report a vulnerability**. Please don't open a public
issue.

Include what you found, how to reproduce it, and which version you tested
(Settings → Software Update shows it). This is a hobby project maintained in
spare time, so expect a reply within about a week. Fixes ship as a new
release, which Pis pick up through Settings → Software Update.

## Supported versions

Only the latest release gets security fixes.
