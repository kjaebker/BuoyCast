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
            # Python (venv handles all packages)
            pkgs.python312

            # SQLite
            pkgs.sqlite

            # Node.js for dashboard
            pkgs.nodejs_22

            # Linting (also in venv, but useful standalone)
            pkgs.ruff

            # Dev tools
            pkgs.git
          ];

          shellHook = ''
            # Create venv if it doesn't exist
            if [ ! -d .venv ]; then
              echo "Creating Python virtual environment..."
              python -m venv .venv
            fi

            # Activate venv (must be before any python commands)
            source .venv/bin/activate

            # Install packages (includes pip-only deps like garmin-fit-sdk, fit-tool)
            if [ ! -f .venv/.installed ]; then
              echo "Installing Python packages..."
              pip install -q --upgrade pip
              pip install -q -e ".[dev]"
              touch .venv/.installed
            fi

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
            echo "  pytest tests/ -q          # Run tests"
            echo "  cd dashboard && npm run dev  # Start dashboard dev server"
          '';
        };
      }
    );
}
