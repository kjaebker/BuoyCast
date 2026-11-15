#!/usr/bin/env bash
# BuoyCast release installer / updater.
#
# Installed by install.sh as /usr/local/sbin/buoycast-update and normally run
# by buoycast-update.service (the dashboard's "Install Update" button), but it
# is safe to run by hand:
#
#   sudo buoycast-update                    # install the latest release
#   sudo buoycast-update --version v0.3.0   # install a specific release
#   sudo buoycast-update --tarball ./buoycast-0.3.0.tar.gz   # local build
#   sudo buoycast-update --rollback         # switch back to the previous release
#
# Each release is unpacked into /opt/buoycast/releases/<version> with its own
# virtualenv, then /opt/buoycast/current is switched to it atomically. If the
# service does not come back healthy, the previous release is restored.
set -euo pipefail

INSTALL_DIR="${BUOYCAST_DIR:-/opt/buoycast}"
RELEASES_DIR="$INSTALL_DIR/releases"
CURRENT_LINK="$INSTALL_DIR/current"
CONFIG_FILE="$INSTALL_DIR/config.toml"
SERVICE="buoycast.service"
DEFAULT_REPO="kjaebker/BuoyCast"
HEALTH_TIMEOUT_S=90

export UV_CACHE_DIR="/var/cache/buoycast/uv"
export UV_PYTHON="/usr/bin/python3"
export UV_PYTHON_DOWNLOADS="never"
export UV_NO_PROGRESS=1

info()  { echo "[buoycast-update] $*"; }
warn()  { echo "[buoycast-update] WARNING: $*" >&2; }
die()   { echo "[buoycast-update] ERROR: $*" >&2; exit 1; }

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

VERSION=""
TARBALL=""
REPO=""
ROLLBACK=false
FORCE=false
RESTART=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)    VERSION="${2:?--version needs a value}"; shift 2 ;;
        --tarball)    TARBALL="${2:?--tarball needs a path}"; shift 2 ;;
        --repo)       REPO="${2:?--repo needs owner/name}"; shift 2 ;;
        --rollback)   ROLLBACK=true; shift ;;
        --force)      FORCE=true; shift ;;
        --no-restart) RESTART=false; shift ;;
        -h|--help)    usage 0 ;;
        *)            warn "Unknown option: $1"; usage 1 ;;
    esac
done

[[ $EUID -eq 0 ]] || die "Run as root (sudo buoycast-update)"
command -v uv >/dev/null || die "uv not found; re-run install.sh"

# ── Helpers ──────────────────────────────────────────────────────────

# Read a value from config.toml with Python's tomllib (no extra deps).
config_get() {  # config_get <section> <key> <default>
    python3 - "$CONFIG_FILE" "$1" "$2" "$3" <<'PY' 2>/dev/null || echo "$4"
import sys, tomllib
path, section, key, default = sys.argv[1:5]
try:
    with open(path, "rb") as f:
        print(tomllib.load(f).get(section, {}).get(key, default))
except FileNotFoundError:
    print(default)
PY
}

# Directory name of the active release (under releases/), or empty.
current_release() {
    if [[ -L "$CURRENT_LINK" ]]; then basename "$(readlink -f "$CURRENT_LINK")"; fi
}

project_version() {  # project_version <dir containing pyproject.toml>
    python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' \
        "$1/pyproject.toml" 2>/dev/null || true
}

current_version() {
    if [[ -L "$CURRENT_LINK" ]]; then project_version "$CURRENT_LINK"; fi
}

switch_to() {  # switch_to <release-dir-name>; atomic symlink swap
    ln -sfn "releases/$1" "$INSTALL_DIR/.current.tmp"
    mv -Tf "$INSTALL_DIR/.current.tmp" "$CURRENT_LINK"
}

install_system_files() {  # install_system_files <release dir>
    local rel="$1" changed=false
    for unit in buoycast.service buoycast-update.service; do
        if ! cmp -s "$rel/deploy/$unit" "/etc/systemd/system/$unit"; then
            install -m 0644 "$rel/deploy/$unit" "/etc/systemd/system/$unit"
            changed=true
        fi
    done
    install -D -m 0644 "$rel/deploy/buoycast.polkit.rules" /etc/polkit-1/rules.d/50-buoycast.rules
    # Keep this script in sync with the release it just installed.
    install -m 0755 "$rel/deploy/update.sh" /usr/local/sbin/buoycast-update
    if $changed; then systemctl daemon-reload; fi
}

wait_healthy() {
    local port deadline
    port="$(config_get server port 8080)"
    deadline=$((SECONDS + HEALTH_TIMEOUT_S))
    while (( SECONDS < deadline )); do
        if curl -fsS -o /dev/null --max-time 3 "http://127.0.0.1:${port}/api/status"; then
            return 0
        fi
        sleep 3
    done
    return 1
}

restart_and_verify() {  # restart_and_verify <previous release or empty>
    local previous="$1"
    $RESTART || { info "Skipping restart (--no-restart)"; return 0; }
    info "Restarting $SERVICE..."
    systemctl restart "$SERVICE"
    if wait_healthy; then
        info "Service is healthy on $(current_version)"
        return 0
    fi
    warn "Service did not become healthy within ${HEALTH_TIMEOUT_S}s"
    journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
    if [[ -n "$previous" && -d "$RELEASES_DIR/$previous" ]]; then
        warn "Rolling back to $previous"
        switch_to "$previous"
        install_system_files "$RELEASES_DIR/$previous"
        systemctl restart "$SERVICE"
    fi
    die "Update failed"
}

prune_releases() {  # keep only the active release and the one before it
    local keep_current keep_prev name
    keep_current="$(current_release)"
    keep_prev="${1:-}"
    for dir in "$RELEASES_DIR"/*/; do
        [[ -d "$dir" ]] || continue
        name="$(basename "$dir")"
        [[ "$name" == "$keep_current" || "$name" == "$keep_prev" ]] && continue
        info "Removing old release $name"
        rm -rf "$dir"
    done
}

# ── Rollback ─────────────────────────────────────────────────────────
if $ROLLBACK; then
    now="$(current_release)"
    prev=""
    for dir in "$RELEASES_DIR"/*/; do  # newest release other than the active one
        [[ -d "$dir" && "$(basename "$dir")" != "$now" ]] || continue
        if [[ -z "$prev" || "$dir" -nt "$RELEASES_DIR/$prev" ]]; then prev="$(basename "$dir")"; fi
    done
    [[ -n "$prev" ]] || die "No previous release to roll back to"
    info "Rolling back $now -> $prev"
    switch_to "$prev"
    install_system_files "$RELEASES_DIR/$prev"
    restart_and_verify ""
    exit 0
fi

# ── Obtain the release tarball ───────────────────────────────────────
REPO="${REPO:-$(config_get updates repo "$DEFAULT_REPO")}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ -n "$TARBALL" ]]; then
    [[ -f "$TARBALL" ]] || die "Tarball not found: $TARBALL"
    cp "$TARBALL" "$WORK/release.tar.gz"
else
    if [[ -z "$VERSION" ]]; then
        info "Looking up latest release of $REPO..."
        VERSION="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
            | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')" \
            || die "Could not determine the latest release of $REPO"
    fi
    [[ "$VERSION" == v* ]] || VERSION="v$VERSION"
    if [[ "$(current_version)" == "${VERSION#v}" ]] && ! $FORCE; then
        info "Already on ${VERSION#v}; nothing to do (use --force to reinstall)"
        install_system_files "$CURRENT_LINK"
        exit 0
    fi
    base="https://github.com/$REPO/releases/download/$VERSION"
    asset="buoycast-${VERSION#v}.tar.gz"
    info "Downloading $asset..."
    curl -fsSL -o "$WORK/release.tar.gz" "$base/$asset" || die "Download failed: $base/$asset"
    curl -fsSL -o "$WORK/release.tar.gz.sha256" "$base/$asset.sha256" || die "Checksum download failed"
    (cd "$WORK" && echo "$(cut -d' ' -f1 release.tar.gz.sha256)  release.tar.gz" | sha256sum -c --quiet) \
        || die "Checksum mismatch for $asset"
fi

# ── Unpack ───────────────────────────────────────────────────────────
mkdir -p "$WORK/x"
tar -xzf "$WORK/release.tar.gz" -C "$WORK/x"
src_dir="$(find "$WORK/x" -mindepth 1 -maxdepth 1 -type d | head -1)"
[[ -f "$src_dir/pyproject.toml" && -d "$src_dir/dashboard/dist" ]] || die "Tarball is not a BuoyCast release"
NEW="$(project_version "$src_dir")"
[[ -n "$NEW" ]] || die "Could not read version from tarball"

PREVIOUS="$(current_release)"
if [[ "$NEW" == "$(current_version)" ]] && ! $FORCE; then
    info "Already on $NEW; nothing to do (use --force to reinstall)"
    install_system_files "$CURRENT_LINK"
    exit 0
fi

# The virtualenv records absolute paths, so it is built in its final
# location. Never build into the directory 'current' points at: a forced
# reinstall of the running version gets a fresh directory name.
mkdir -p "$RELEASES_DIR" "$UV_CACHE_DIR"
name="$NEW"
if [[ "$name" == "$PREVIOUS" || -e "$RELEASES_DIR/$name" ]]; then
    name="$NEW-$(date +%Y%m%d%H%M%S)"
fi
target="$RELEASES_DIR/$name"
mv "$src_dir" "$target"

# ── Python environment (exact versions from uv.lock; wheels only) ────
info "Installing Python dependencies for $NEW..."
(cd "$target" && uv sync --frozen --no-dev --compile-bytecode --quiet) \
    || { rm -rf "$target"; die "Dependency install failed"; }

chown -R root:root "$target"
chmod -R go-w "$target"

# ── Activate ─────────────────────────────────────────────────────────
info "Activating $NEW (previous: ${PREVIOUS:-none})"
switch_to "$name"
install_system_files "$target"
restart_and_verify "$PREVIOUS"
prune_releases "$PREVIOUS"
info "BuoyCast $NEW installed"
