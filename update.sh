#!/usr/bin/env bash
# Update BuoyCast to the latest version.
# Run from anywhere: sudo bash /opt/buoycast/update.sh
# Or from the repo:  sudo bash update.sh
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_NAME="buoycast"

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
    # INSTALL_DIR is itself a git repo — pull directly
    sudo -u pi git -C "$INSTALL_DIR" pull origin main

elif [[ -f "$INSTALL_DIR/.source_dir" ]]; then
    # install.sh recorded where it copied files from — pull there, then re-sync
    SOURCE_DIR=$(cat "$INSTALL_DIR/.source_dir")
    if [[ -d "$SOURCE_DIR/.git" ]]; then
        info "Pulling into source repo at $SOURCE_DIR..."
        sudo -u pi git -C "$SOURCE_DIR" pull origin main
        info "Syncing updated files to $INSTALL_DIR..."
        rsync -a --delete \
            --exclude='.git' \
            --exclude='.venv' \
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

# ── Update Python dependencies ────────────────────────────────────────
info "Updating Python dependencies..."
# Clean up any stale pip temp dirs (left behind by interrupted/root installs)
find "$INSTALL_DIR/.venv/lib" -maxdepth 3 -name '~*' -type d -exec rm -rf {} + 2>/dev/null || true
sudo -u pi "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" -q

# ── Restart service ───────────────────────────────────────────────────
info "Restarting service..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl restart "$SERVICE_NAME"
    info "Service restarted"
else
    warn "Service is not running — start it with: sudo systemctl start $SERVICE_NAME"
fi

info "Done — BuoyCast updated successfully"
