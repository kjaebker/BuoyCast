#!/usr/bin/env bash
# Update BuoyCast to the latest version.
# Run from anywhere: sudo bash /opt/buoycast/update.sh
# Or from the repo:  sudo bash update.sh
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_NAME="buoycast"
SERVICE_USER="pi"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Pull latest code ──────────────────────────────────────────────────
info "Pulling latest code (includes pre-built dashboard)..."

if [[ -d "$INSTALL_DIR/.git" ]]; then
    sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull origin main

elif [[ -f "$INSTALL_DIR/.source_dir" ]]; then
    SOURCE_DIR=$(cat "$INSTALL_DIR/.source_dir")
    if [[ -d "$SOURCE_DIR/.git" ]]; then
        info "Pulling into source repo at $SOURCE_DIR..."
        sudo -u "$SERVICE_USER" git -C "$SOURCE_DIR" pull origin main
        info "Syncing updated files to $INSTALL_DIR..."
        rsync -a --delete \
            --exclude='.git' \
            --exclude='.venv' \
            --exclude='.source_dir' \
            --exclude='node_modules' \
            --exclude='data/' \
            --exclude='__pycache__' \
            --exclude='config.toml' \
            "$SOURCE_DIR/" "$INSTALL_DIR/"
    else
        error "Source directory '$SOURCE_DIR' is missing or not a git repo. Re-clone and re-run install.sh."
    fi

else
    error "$INSTALL_DIR is not a git repo and no source directory was recorded.
  To fix: clone the repo on this Pi and re-run install.sh, e.g.
    git clone <repo-url> ~/BuoyCast
    sudo bash ~/BuoyCast/install.sh"
fi

# ── Ensure runtime directories exist ─────────────────────────────────
mkdir -p "$INSTALL_DIR/data/fit"
mkdir -p "$INSTALL_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# ── Update systemd service file if changed ────────────────────────────
INSTALLED_SERVICE="/etc/systemd/system/${SERVICE_NAME}.service"
if ! diff -q "$INSTALL_DIR/${SERVICE_NAME}.service" "$INSTALLED_SERVICE" &>/dev/null; then
    info "Service file changed — updating and reloading systemd..."
    cp "$INSTALL_DIR/${SERVICE_NAME}.service" "$INSTALLED_SERVICE"
    systemctl daemon-reload
fi

# ── Stop service before pip to free RAM (Pi Zero 2W has 512 MB) ───────
WAS_RUNNING=false
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Stopping service to free memory for pip..."
    systemctl stop "$SERVICE_NAME"
    WAS_RUNNING=true
fi

# ── Update Python dependencies ────────────────────────────────────────
info "Updating Python dependencies..."
# Clean up any stale pip temp dirs (left behind by interrupted/root installs)
find "$INSTALL_DIR/.venv/lib" -maxdepth 3 -name '~*' -type d -exec rm -rf {} + 2>/dev/null || true
PIP="$INSTALL_DIR/.venv/bin/pip"
# --no-cache-dir keeps pip's memory footprint smaller on constrained hardware.
# Install one package at a time to avoid simultaneous resolver + download spikes.
sudo -u "$SERVICE_USER" "$PIP" install --no-cache-dir -e "$INSTALL_DIR" -q
sudo -u "$SERVICE_USER" "$PIP" install --no-cache-dir bleak -q
sudo -u "$SERVICE_USER" "$PIP" install --no-cache-dir bless -q
sudo -u "$SERVICE_USER" "$PIP" install --no-cache-dir dbus-python -q

# ── Restart service ───────────────────────────────────────────────────
if $WAS_RUNNING; then
    info "Restarting service..."
    systemctl start "$SERVICE_NAME"
    info "Service started"
else
    warn "Service was not running before update — start it with: sudo systemctl start $SERVICE_NAME"
fi

info "Done — BuoyCast updated successfully"
