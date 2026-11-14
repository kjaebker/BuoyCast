#!/usr/bin/env bash
# Build a BuoyCast release tarball: committed source + freshly built dashboard.
#
#   deploy/package.sh            # -> release/buoycast-<version>.tar.gz (+ .sha256)
#   deploy/package.sh --skip-dashboard-build   # reuse an existing dashboard/dist
#
# Install it on a Pi for testing without publishing a release:
#   scp release/buoycast-*.tar.gz deploy/install.sh deploy/update.sh pi@buoycast.local:
#   ssh pi@buoycast.local 'sudo bash install.sh --tarball buoycast-*.tar.gz'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/release"
BUILD_DASHBOARD=true
[[ "${1:-}" == "--skip-dashboard-build" ]] && BUILD_DASHBOARD=false

VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
NAME="buoycast-$VERSION"

if $BUILD_DASHBOARD; then
    echo "Building dashboard..."
    (cd dashboard && npm ci --no-audit --no-fund && npm run build)
fi
[[ -f dashboard/dist/index.html ]] || { echo "dashboard/dist missing; build it first" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$NAME"

# Only committed files: no local config, data, venvs or node_modules.
git ls-files -- src deploy pyproject.toml uv.lock README.md LICENSE config.toml.example \
    | while IFS= read -r f; do
        mkdir -p "$STAGE/$NAME/$(dirname "$f")"
        cp "$f" "$STAGE/$NAME/$f"
    done
mkdir -p "$STAGE/$NAME/dashboard"
cp -R dashboard/dist "$STAGE/$NAME/dashboard/dist"

mkdir -p "$OUT"
# Reproducible-ish: fixed owner and sorted entries.
tar --version 2>/dev/null | grep -q GNU && TAR_OPTS=(--owner=0 --group=0 --numeric-owner --sort=name) || TAR_OPTS=(--no-xattrs --no-mac-metadata)
COPYFILE_DISABLE=1 tar "${TAR_OPTS[@]}" -czf "$OUT/$NAME.tar.gz" -C "$STAGE" "$NAME"
(cd "$OUT" && { sha256sum "$NAME.tar.gz" 2>/dev/null || shasum -a 256 "$NAME.tar.gz"; } > "$NAME.tar.gz.sha256")

echo "Built $OUT/$NAME.tar.gz"
cat "$OUT/$NAME.tar.gz.sha256"
