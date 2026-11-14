{
  description = "BuoyCast - Raspberry Pi bridge for WaterRower S4";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Python (uv manages the venv from uv.lock)
            pkgs.python312
            pkgs.uv

            # SQLite
            pkgs.sqlite

            # Node.js for dashboard
            pkgs.nodejs_22

            # Playwright (headless browser for screenshots)
            pkgs.playwright-driver.browsers

            # Linting (also in venv, but useful standalone)
            pkgs.ruff

            # Dev tools
            pkgs.git
          ];

          PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
          PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
          PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";

          shellHook = ''
            # Sync the venv from uv.lock (fast no-op when already up to date)
            export UV_PYTHON=${pkgs.python312}/bin/python3
            export UV_PYTHON_DOWNLOADS=never
            uv sync --quiet
            source .venv/bin/activate

            # Install npm dependencies if needed
            if [ ! -d dashboard/node_modules ]; then
              echo "Installing dashboard dependencies..."
              (cd dashboard && npm install)
            fi

            echo "BuoyCast dev environment ready!"
            echo "  Python: $(python --version)"
            echo "  Node:   $(node --version)"
            echo ""
            echo "Commands:"
            echo "  pytest tests/ -q                    # Run tests"
            echo "  cd dashboard && npm run dev          # Start dashboard dev server"
            echo "  cd dashboard && npm run screenshot   # Capture mobile + tablet screenshots"
          '';
        };
      }
    );
}
