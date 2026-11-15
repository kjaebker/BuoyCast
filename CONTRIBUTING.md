# Contributing to BuoyCast

Thanks for helping! BuoyCast is a small hobby project, so issues and pull
requests are reviewed in spare time. For anything bigger than a bug fix,
please open an issue first so we can agree on the approach before you write
code.

Report security problems privately, as described in [SECURITY.md](SECURITY.md).

## You don't need a rower

Everything runs on a laptop. `--simulate` replaces the WaterRower S4 and the
heart-rate strap with a realistic fake workout, and the tests use mock
hardware.

## Setup

You need Python 3.11+, Node.js 22 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/kjaebker/BuoyCast.git
cd BuoyCast
uv sync                              # Python deps + dev tools into .venv
(cd dashboard && npm ci)
```

With Nix, `nix develop` (or `direnv allow`) gives you all of this in one step.

## Run it

```bash
uv run python -m src.main --simulate     # backend on :8080, fake rower + HR
cd dashboard && npm run dev              # dashboard on http://localhost:5173
```

Without a `config.toml`, `--simulate` uses `config.toml.example`. To try the
HTTP export, copy the example, set `[export] url`, and pass
`--config my-config.toml`. [docs/export.md](docs/export.md#testing-a-receiver)
explains how.

## Checks

CI runs these on every push and pull request. Run them before you open a PR:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest tests/ -q
(cd dashboard && npm run lint && npm run build)
shellcheck deploy/*.sh
```

## Conventions

- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `chore:`, and so on.
- **Changelog:** add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md)
  for anything a user would notice.
- **Never block the event loop.** All I/O is `async`. CPU-heavy work (FIT
  generation, for example) goes through `asyncio.to_thread`.
- **Components talk through the event bus** (`src/events.py`), never by
  calling each other directly.
- **Pydantic models at every boundary:** serial parsing, Bluetooth, the API,
  SQLite. The TypeScript types in `dashboard/src/types.ts` mirror
  `src/models.py` exactly. Change both together.
- **Database changes** go in a new numbered migration in
  `src/storage/db.py`. Never edit an existing one, because Pis in the field
  have already applied it.
- **The export payload is a public contract.** When changing
  `src/export/payload.py`, update [docs/export.md](docs/export.md) and
  regenerate `docs/export.schema.json` (the test failure prints the
  command). A breaking change bumps `SCHEMA_VERSION`.
- **Budget:** a Raspberry Pi Zero 2W with 512 MB RAM. Keep an active
  workout under 50% CPU and 200 MB RAM. Avoid new heavy dependencies.
- **Dashboard:** dark mode only, touch targets of at least 64 px, mobile
  first. People use it mid-workout, at arm's length.

[CLAUDE.md](CLAUDE.md) has more detail on the architecture and the design
direction. It's written for AI coding agents, but it's useful for people too.

## Hardware testing

Changes to the S4 reader, Bluetooth or the installer need testing on a real
Pi. [docs/hardware-checklist.md](docs/hardware-checklist.md) walks through it.
If you don't have the hardware, say so in the PR and someone who does can
test it.

## Releases

Maintainers release by bumping `version` in `pyproject.toml`, moving the
"Unreleased" changelog entries under the new version, and pushing a matching
`vX.Y.Z` tag. The release workflow runs the tests, builds the bundle, and
publishes a GitHub Release, which Pis then offer under Settings → Software
Update.
