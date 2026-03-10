#!/usr/bin/env bash
# BuoyCast install script for Raspberry Pi
# Usage: sudo bash install.sh
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_NAME="waterrower"
SERVICE_USER="pi"
NODE_MAJOR=20

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Preflight checks ─────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "This script must be run as root (use sudo)"
id "$SERVICE_USER" &>/dev/null || error "User '$SERVICE_USER' does not exist"

info "Installing BuoyCast to $INSTALL_DIR"

# ── System dependencies ──────────────────────────────────────────────
info "Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-dev python3-pip \
    libdbus-1-dev libglib2.0-dev \
    bluez bluetooth \
    avahi-daemon avahi-utils \
    git curl

# Install Node.js if not present (for dashboard build)
if ! command -v node &>/dev/null; then
    info "Installing Node.js $NODE_MAJOR..."
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash -
    apt-get install -y -qq nodejs
else
    info "Node.js already installed: $(node --version)"
fi

# ── Copy application files ───────────────────────────────────────────
info "Setting up application directory..."
mkdir -p "$INSTALL_DIR"

# If running from repo, copy files; otherwise assume we're already in place
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
    # Copy project files (exclude .git, .venv, node_modules)
    rsync -a --delete \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='data/' \
        --exclude='__pycache__' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/"
fi

# Create data directories
mkdir -p "$INSTALL_DIR/data/fit"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── Python virtual environment ───────────────────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi

# Install Python dependencies
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" -q

# Install BLE library (bleak) for TICKR + FTMS
"$INSTALL_DIR/.venv/bin/pip" install bleak dbus-python -q

info "Python packages installed"

# ── Dashboard build ──────────────────────────────────────────────────
info "Building dashboard..."
cd "$INSTALL_DIR/dashboard"
npm ci --silent
# Skip tsc type-check (dev-time only); run vite build directly
npx vite build
cd "$INSTALL_DIR"

info "Dashboard built successfully"

# ── Config file ──────────────────────────────────────────────────────
if [[ ! -f "$INSTALL_DIR/config.toml" ]]; then
    cp "$INSTALL_DIR/config.toml.example" "$INSTALL_DIR/config.toml"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/config.toml"
    warn "Created config.toml from template — edit it before starting"
else
    info "config.toml already exists, not overwriting"
fi

# ── systemd service ──────────────────────────────────────────────────
info "Installing systemd service..."
cp "$INSTALL_DIR/waterrower.service" /etc/systemd/system/${SERVICE_NAME}.service
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service

info "Service installed and enabled"

# ── Avahi/mDNS ───────────────────────────────────────────────────────
info "Configuring mDNS (avahi)..."
systemctl enable avahi-daemon
systemctl start avahi-daemon || true

# Ensure hostname is set for .local resolution
MDNS_NAME=$(grep -oP 'mdns_name\s*=\s*"\K[^"]+' "$INSTALL_DIR/config.toml" 2>/dev/null || echo "waterrower")
if [[ "$(hostname)" != "$MDNS_NAME" ]]; then
    warn "Hostname is '$(hostname)', not '$MDNS_NAME'"
    warn "Run: sudo hostnamectl set-hostname $MDNS_NAME"
fi

# ── Bluetooth permissions ────────────────────────────────────────────
info "Ensuring Bluetooth permissions..."
usermod -aG bluetooth "$SERVICE_USER" 2>/dev/null || true
usermod -aG dialout "$SERVICE_USER" 2>/dev/null || true

# ── Done ─────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  BuoyCast installation complete!"
echo "=========================================="
echo ""
echo "Post-install checklist:"
echo ""
echo "  1. Edit config.toml:"
echo "     nano $INSTALL_DIR/config.toml"
echo ""
echo "     - Set TICKR MAC address:  heart_rate.device_mac"
echo "     - Set Strava credentials: strava.client_id / client_secret"
echo ""
echo "  2. Set hostname (for waterrower.local):"
echo "     sudo hostnamectl set-hostname $MDNS_NAME"
echo ""
echo "  3. Start the service:"
echo "     sudo systemctl start $SERVICE_NAME"
echo ""
echo "  4. Check status:"
echo "     sudo systemctl status $SERVICE_NAME"
echo "     journalctl -u $SERVICE_NAME -f"
echo ""
echo "  5. Connect Strava (one-time, from your phone/laptop browser):"
echo "     http://${MDNS_NAME}.local:8080/api/strava/auth"
echo ""
echo "  6. Verify everything:"
echo "     curl http://${MDNS_NAME}.local:8080/api/status"
echo ""
