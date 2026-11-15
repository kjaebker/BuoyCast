#!/usr/bin/env bash
# BuoyCast installer for Raspberry Pi OS (64-bit, Bookworm or newer).
#
#   curl -fsSL https://github.com/kjaebker/BuoyCast/releases/latest/download/install.sh | sudo bash
#
# Options (pass after `bash -s --` when piping, e.g. `| sudo bash -s -- --version v0.3.0`):
#   --version vX.Y.Z   install a specific release instead of the latest
#   --tarball PATH     install from a locally built release tarball
#   --repo OWNER/NAME  install from a fork's releases
#
# Safe to re-run: it keeps config.toml and data/, and upgrades older
# BuoyCast installs (git checkout layout, `pi` user, sudoers) in place.
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_USER="buoycast"
REPO="kjaebker/BuoyCast"
UV_VERSION="0.13.6"
VERSION=""
TARBALL=""

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="${2:?}"; shift 2 ;;
        --tarball) TARBALL="$(realpath "${2:?}")"; shift 2 ;;
        --repo)    REPO="${2:?}"; shift 2 ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)         die "Unknown option: $1" ;;
    esac
done

# ── Preflight ────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"
[[ "$(uname -m)" == "aarch64" ]] || warn "Expected a 64-bit OS (aarch64), found $(uname -m). Prebuilt wheels may be missing."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
    || die "Python 3.11+ required (Raspberry Pi OS Bookworm or newer)"

# ── System packages ──────────────────────────────────────────────────
info "Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 bluez avahi-daemon curl ca-certificates
# polkit authorises the dashboard's restart/update/reboot buttons.
apt-get install -y -qq polkitd 2>/dev/null || apt-get install -y -qq policykit-1
# A freshly installed polkitd needs D-Bus to load its bus policy first, or it
# exits with "Lost the name org.freedesktop.PolicyKit1".
systemctl reload dbus.service 2>/dev/null || true
systemctl restart polkit.service 2>/dev/null || true

# ── uv (installs the locked Python dependencies; no compiling on the Pi) ──
if ! command -v uv >/dev/null || [[ "$(uv --version | awk '{print $2}')" != "$UV_VERSION" ]]; then
    info "Installing uv $UV_VERSION..."
    curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" \
        | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh -s -- --quiet
fi

# ── Service user ─────────────────────────────────────────────────────
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating system user '$SERVICE_USER'..."
    useradd --system --user-group --home-dir "$INSTALL_DIR" --no-create-home \
        --shell /usr/sbin/nologin "$SERVICE_USER"
fi
# Serial port, BlueZ D-Bus, and reading its own journal for /api/logs.
usermod -aG dialout,bluetooth,systemd-journal "$SERVICE_USER"

# ── Migrate a pre-0.2 install (git checkout in /opt/buoycast, run as pi) ──
if [[ -d "$INSTALL_DIR/src" && ! -L "$INSTALL_DIR/current" ]]; then
    backup="$INSTALL_DIR/legacy-$(date +%Y%m%d%H%M%S)"
    warn "Found a pre-0.2 install; moving old app files to $backup (config.toml and data/ are kept)"
    systemctl stop buoycast.service 2>/dev/null || true
    mkdir -p "$backup"
    shopt -s dotglob
    for item in "$INSTALL_DIR"/*; do
        case "$(basename "$item")" in
            config.toml|data|logs|releases|legacy-*) ;;
            *) mv "$item" "$backup/" ;;
        esac
    done
    shopt -u dotglob
fi
rm -f /etc/sudoers.d/buoycast  # no longer used; replaced by a polkit rule
if systemctl list-unit-files waterrower.service 2>/dev/null | grep -q waterrower; then
    warn "Removing legacy 'waterrower' service"
    systemctl disable --now waterrower.service 2>/dev/null || true
    rm -f /etc/systemd/system/waterrower.service
fi

# ── Directories ──────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/releases" "$INSTALL_DIR/data/fit" "$INSTALL_DIR/logs"
chown root:root "$INSTALL_DIR" "$INSTALL_DIR/releases"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
chmod 0750 "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
chmod 0755 "$INSTALL_DIR" "$INSTALL_DIR/releases"

# ── Release ──────────────────────────────────────────────────────────
# Use update.sh from alongside this script (local checkout / extracted
# release); otherwise fetch the one published with the release.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
UPDATER="$(mktemp)"
trap 'rm -f "$UPDATER"' EXIT
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/update.sh" ]]; then
    cp "$SCRIPT_DIR/update.sh" "$UPDATER"
else
    tag="${VERSION:-latest}"
    if [[ "$tag" == "latest" ]]; then
        url="https://github.com/$REPO/releases/latest/download/update.sh"
    else
        [[ "$tag" == v* ]] || tag="v$tag"
        url="https://github.com/$REPO/releases/download/$tag/update.sh"
    fi
    curl -fsSL -o "$UPDATER" "$url" || die "Could not download $url"
fi

args=(--repo "$REPO" --no-restart)
[[ -n "$VERSION" ]] && args+=(--version "$VERSION")
[[ -n "$TARBALL" ]] && args+=(--tarball "$TARBALL")
bash "$UPDATER" "${args[@]}"

# ── Config ───────────────────────────────────────────────────────────
if [[ ! -f "$INSTALL_DIR/config.toml" ]]; then
    cp "$INSTALL_DIR/current/config.toml.example" "$INSTALL_DIR/config.toml"
    info "Created $INSTALL_DIR/config.toml from the template"
fi
# Holds the Strava client secret: readable by the service, not by everyone.
chown "root:$SERVICE_USER" "$INSTALL_DIR/config.toml"
chmod 0640 "$INSTALL_DIR/config.toml"

# ── Start ────────────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable avahi-daemon.service >/dev/null 2>&1 || true
systemctl start avahi-daemon.service || true
systemctl enable buoycast.service
systemctl restart buoycast.service

HOST="$(hostname)"
PORT="$(python3 -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1],"rb")).get("server",{}).get("port",8080))' "$INSTALL_DIR/config.toml" 2>/dev/null || echo 8080)"

info "Waiting for BuoyCast to come up..."
healthy=false
for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 3 "http://127.0.0.1:${PORT}/api/status"; then
        healthy=true; break
    fi
    sleep 3
done
if ! $healthy; then
    journalctl -u buoycast.service -n 30 --no-pager >&2 || true
    die "BuoyCast did not start. See the log above, or: journalctl -u buoycast -e"
fi

cat <<EOF

==========================================
  BuoyCast $(grep -m1 '^version' "$INSTALL_DIR/current/pyproject.toml" | cut -d'"' -f2) is installed and running
==========================================

  Dashboard:  http://${HOST}.local:${PORT}

  Next steps:
    1. Edit the config (heart rate strap, Strava credentials):
         sudo nano $INSTALL_DIR/config.toml
         sudo systemctl restart buoycast
    2. Connect Strava (optional), from a browser on your network:
         http://${HOST}.local:${PORT}/api/strava/auth

  Logs:     journalctl -u buoycast -f
  Update:   from the dashboard (Settings → Software Update),
            or: sudo systemctl start buoycast-update
  Rollback: sudo buoycast-update --rollback

EOF
