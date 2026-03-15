#!/usr/bin/env bash
# Update BuoyCast to the latest version.
#
# Modes:
#   sudo bash update.sh              — auto-detect: try release bundle, fall back to git
#   sudo bash update.sh --release    — download latest GitHub Release bundle (offline install)
#   sudo bash update.sh --git        — legacy git pull + pip install
#   sudo bash update.sh --bundle /path/to/buoycast-v*.tar.gz — install from a local bundle file
#
set -euo pipefail

INSTALL_DIR="/opt/buoycast"
SERVICE_NAME="buoycast"
SERVICE_USER="pi"

# GitHub repo for release downloads (owner/repo)
GITHUB_REPO="kjaebker/BuoyCast"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Parse arguments ──────────────────────────────────────────────────
MODE="auto"
BUNDLE_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)  MODE="release"; shift ;;
        --git)      MODE="git";     shift ;;
        --bundle)
            MODE="bundle"
            BUNDLE_PATH="${2:?'--bundle requires a path to a .tar.gz file'}"
            shift 2
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

# ── Auto-detect mode ────────────────────────────────────────────────
if [[ "$MODE" == "auto" ]]; then
    if ! command -v curl &>/dev/null; then
        MODE="git"
        info "Auto-detected: curl not found, falling back to git"
    else
        # Check if a release bundle actually exists (curl -w to get HTTP status)
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
            "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" 2>/dev/null || echo "000")

        if [[ "$HTTP_CODE" == "200" ]]; then
            MODE="release"
            info "Auto-detected: using GitHub Release bundle"
        elif [[ "$HTTP_CODE" == "404" ]]; then
            MODE="git"
            info "Auto-detected: no GitHub Releases found yet, falling back to git"
        elif [[ "$HTTP_CODE" == "000" ]]; then
            MODE="git"
            info "Auto-detected: GitHub unreachable (network error), falling back to git"
        else
            MODE="git"
            info "Auto-detected: GitHub API returned HTTP $HTTP_CODE, falling back to git"
        fi
    fi
fi

# ── Helper: install from an extracted bundle directory ───────────────
install_from_bundle() {
    local BUNDLE_DIR="$1"

    # Verify bundle contents
    [[ -d "$BUNDLE_DIR/wheels" ]]         || error "Bundle missing wheels/ directory"
    [[ -d "$BUNDLE_DIR/dashboard-dist" ]] || error "Bundle missing dashboard-dist/ directory"

    # Show version being installed
    if [[ -f "$BUNDLE_DIR/VERSION" ]]; then
        info "Installing version: $(cat "$BUNDLE_DIR/VERSION")"
    fi

    # Install Python packages from pre-built wheels (fully offline)
    info "Installing Python packages from bundle wheels..."
    "$INSTALL_DIR/.venv/bin/pip" install \
        --no-index \
        --find-links "$BUNDLE_DIR/wheels" \
        --force-reinstall \
        buoycast bleak bless dbus-python \
        -q

    # Update dashboard
    info "Updating dashboard..."
    rm -rf "$INSTALL_DIR/dashboard/dist"
    cp -r "$BUNDLE_DIR/dashboard-dist" "$INSTALL_DIR/dashboard/dist"

    # Update service file and scripts
    cp "$BUNDLE_DIR/buoycast.service" "$INSTALL_DIR/buoycast.service"
    cp "$BUNDLE_DIR/buoycast.service" /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload

    # Update install/update scripts for next time
    cp "$BUNDLE_DIR/install.sh" "$INSTALL_DIR/install.sh"
    cp "$BUNDLE_DIR/update.sh" "$INSTALL_DIR/update.sh"

    # Store version
    if [[ -f "$BUNDLE_DIR/VERSION" ]]; then
        cp "$BUNDLE_DIR/VERSION" "$INSTALL_DIR/VERSION"
    fi

    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
}

# ── Mode: release (download from GitHub Releases) ───────────────────
if [[ "$MODE" == "release" ]]; then
    info "Fetching latest release from GitHub..."

    # Get the download URL for the bundle tarball
    RELEASE_JSON=$(curl -sf "https://api.github.com/repos/${GITHUB_REPO}/releases/latest") \
        || error "Failed to fetch release info from GitHub"

    DOWNLOAD_URL=$(echo "$RELEASE_JSON" | python3 -c "
import sys, json
assets = json.load(sys.stdin).get('assets', [])
for a in assets:
    if a['name'].startswith('buoycast-') and a['name'].endswith('.tar.gz'):
        print(a['browser_download_url'])
        break
" 2>/dev/null) || true

    [[ -n "$DOWNLOAD_URL" ]] || error "No buoycast bundle found in latest release"

    TAG_NAME=$(echo "$RELEASE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null)

    # Skip download if already on this version
    if [[ -f "$INSTALL_DIR/VERSION" ]]; then
        CURRENT_VERSION=$(cat "$INSTALL_DIR/VERSION")
        if [[ "$CURRENT_VERSION" == "$TAG_NAME" ]]; then
            info "Already running $TAG_NAME — nothing to update"
            exit 0
        fi
    fi

    info "Downloading $TAG_NAME bundle..."

    # Download to temp directory
    TMP_DIR=$(mktemp -d)
    trap "rm -rf $TMP_DIR" EXIT
    curl -fSL "$DOWNLOAD_URL" -o "$TMP_DIR/bundle.tar.gz" \
        || error "Failed to download release bundle"

    # Extract and install
    info "Extracting bundle..."
    mkdir -p "$TMP_DIR/bundle"
    tar -xzf "$TMP_DIR/bundle.tar.gz" -C "$TMP_DIR/bundle"

    install_from_bundle "$TMP_DIR/bundle"

# ── Mode: bundle (local file) ───────────────────────────────────────
elif [[ "$MODE" == "bundle" ]]; then
    [[ -f "$BUNDLE_PATH" ]] || error "Bundle file not found: $BUNDLE_PATH"

    info "Installing from local bundle: $BUNDLE_PATH"

    TMP_DIR=$(mktemp -d)
    trap "rm -rf $TMP_DIR" EXIT
    mkdir -p "$TMP_DIR/bundle"
    tar -xzf "$BUNDLE_PATH" -C "$TMP_DIR/bundle"

    install_from_bundle "$TMP_DIR/bundle"

# ── Mode: git (legacy) ──────────────────────────────────────────────
elif [[ "$MODE" == "git" ]]; then
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

    # Update Python dependencies
    info "Updating Python dependencies..."
    find "$INSTALL_DIR/.venv/lib" -maxdepth 3 -name '~*' -type d -exec rm -rf {} + 2>/dev/null || true
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" -q
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install bleak bless dbus-python -q
fi

# ── Restart service ──────────────────────────────────────────────────
info "Restarting service..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl restart "$SERVICE_NAME"
    info "Service restarted"
else
    warn "Service is not running — start it with: sudo systemctl start $SERVICE_NAME"
fi

# ── Show installed version ───────────────────────────────────────────
if [[ -f "$INSTALL_DIR/VERSION" ]]; then
    info "Done — BuoyCast $(cat "$INSTALL_DIR/VERSION") installed successfully"
else
    info "Done — BuoyCast updated successfully"
fi
