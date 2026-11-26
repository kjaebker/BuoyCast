# Changelog

All notable changes to BuoyCast are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Before 1.0, a minor version bump
can include breaking changes; they're called out below.

## Unreleased

### Added
- A live graph can replace the rowing scene. Pick Pace, Watts, SPM or HR
  above the scene to see the last 5 minutes of that metric with its average;
  Scene switches back. The choice is remembered on each device.

### Fixed
- The phone or tablet screen no longer goes to sleep during a workout. The
  browser's wake lock only works over HTTPS, and BuoyCast is served over
  plain HTTP, so it never took effect. A silent looping video now keeps the
  screen on instead. On iPhone it starts after your first tap on the page.
- The screen also stays on while a workout is paused, not only while rowing.

## 0.3.2 — 2026-11-20

### Fixed
- The Bluetooth pairing agent now registers. It always failed at startup
  with "pairing agent registration failed", so a device that tried to bond
  with BuoyCast (as Peloton may) was rejected.
- The Bluetooth advertisement now includes FTMS Service Data saying
  BuoyCast is an available rower. Apps that filter on the machine type,
  Peloton among them, skipped it without this.

## 0.3.1 — 2026-11-14

### Changed
- Strava and HTTP export controls only appear when they're set up. The
  completion screen shows the export's delivery status when an export URL
  is configured, offers the Strava upload only when an account is
  connected, and otherwise just has a **Done** button. The top bar's Strava
  badge and the Strava and export sections in Settings are hidden until
  configured, with a pointer to the setup guide.

## 0.3.0 — 2026-11-14

First public release.

### Security
- Other websites can no longer control BuoyCast through your browser.
  Cross-site POST/PUT/PATCH/DELETE requests and WebSocket connections are
  rejected, CORS is no longer open to every origin, and requests for
  unknown host names are refused to block DNS rebinding. If you reach the
  dashboard by a host name other than an IP address, `*.local` or a
  single-label name, add it to the new `[server] allowed_hosts` setting.
  See [SECURITY.md](SECURITY.md).

### Added
- **HTTP export:** send each finished workout (JSON or FIT) to your own
  endpoint, with a bearer token and automatic retries. Workouts get an
  export status and a Send button in history. See [docs/export.md](docs/export.md).
- **Install and update from GitHub Releases:** a one-line installer, and
  updates (with automatic rollback) from Settings → Software Update.
- **Animated rower** synced to your real strokes using the S4's stroke
  start/end events.
- Simulation mode (`--simulate`) for running without a rower or strap.
- Heart-rate debug capture (`[heart_rate] debug_capture`).

### Changed
- Installs live in `/opt/buoycast` and run as a dedicated `buoycast` user
  instead of `pi`. Re-running the installer migrates an older install in
  place.
- Heart rate moved from the stats grid into the stroke-rate chart.
- Workout history only shows Strava controls when Strava is connected.
- The default `[server] mdns_name` is now `buoycast` (was `waterrower`).
- Documentation rewritten for new users: README, a single
  [setup guide](docs/setup.md), [CONTRIBUTING.md](CONTRIBUTING.md) and
  [SECURITY.md](SECURITY.md). Internal planning files were removed.
- The Peloton section of the [hardware checklist](docs/hardware-checklist.md)
  now has the correct pairing steps (Peloton app, inside a rowing class).

### Fixed
- Distance, strokes and calories now count from the start of the workout,
  not from the monitor's running totals.
- The recorder saved per-second samples as strokes, and could orphan
  workouts after a reset.
- Workouts could get stuck and return 409 Conflict on start.
- Heart-rate data corruption from the RR-interval buffer.
- Path traversal in the dashboard's static file serving.
- The in-app update could stop its own service halfway through.

## 0.2.0 — 2026-03-15

First release with the release-bundle deploy experiment. Superseded by 0.3.0;
its bundle can't be installed by the current installer.

## 0.1.0 — 2026-03-15

Initial version.
