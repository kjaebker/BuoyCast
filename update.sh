#!/usr/bin/env bash
# Update BuoyCast to the latest version.
# Run from anywhere: bash /opt/buoycast/update.sh
# Or from the repo: bash update.sh
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_NAME="waterrower"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

cd "$INSTALL_DIR"

info "Pulling latest code (includes pre-built dashboard)..."
git pull origin main

info "Updating Python dependencies..."
.venv/bin/pip install -e . -q

info "Restarting service..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
    info "Service restarted"
else
    warn "Service is not running — start it with: sudo systemctl start $SERVICE_NAME"
fi

info "Done — running version: $(git rev-parse --short HEAD)"
