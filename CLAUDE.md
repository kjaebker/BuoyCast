# BuoyCast — Claude Code Instructions

Guidance for AI coding agents working on this repo. Human contributors: see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Workflow
- Read [CONTRIBUTING.md](CONTRIBUTING.md) first; it applies to AI agents too.
- Commit messages follow conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:`, etc.
- Run the full test suite before committing: `pytest tests/ -q`
- User-facing changes get a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).

---

## Build/Run Commands

### Environment Setup (NixOS with Flake)
This project uses a Nix flake for reproducible development. With `direnv` installed:
```bash
cd /path/to/BuoyCast
direnv allow  # automatically enters dev shell
```

Or manually:
```bash
nix develop
```

The shell hook automatically:
- Creates `.venv` if missing
- Installs Python packages (including pip-only deps like `garmin-fit-sdk`)
- Installs dashboard npm dependencies

### Python
Run tests:
```bash
pytest tests/ -q
```
Verbose: `pytest tests/ -v`

### Dashboard (from `dashboard/` directory)
Dev server: `npm run dev`
Type-check: `npm run build` (runs tsc then vite)
Build only: `npx vite build`

### Running locally without hardware (simulation mode)

Start the backend with simulated S4 + HR data (no WaterRower or TICKR required):
```bash
python -m src.main --simulate
```

No `config.toml` needed — `--simulate` falls back to `config.toml.example` automatically.

In a second terminal, start the dashboard dev server:
```bash
cd dashboard && npm run dev
```

Open `http://localhost:5173` (the Vite proxy forwards `/api` and `/ws` to the backend on port 8080, keeping the browser's Host header so the cross-site guard accepts it).

The simulator generates a realistic ~12-minute workout:
- **0–1 min** — warmup: stroke rate 18–20 SPM, HR 95→120 BPM
- **1–10 min** — main effort: stroke rate ~22 SPM with undulation, HR 120→155 BPM
- **10–12 min** — cooldown: stroke rate dropping, HR recovering
- **12+ min** — light ongoing rowing (loops indefinitely until you stop the process)

Both S4 and TICKR connect events are emitted at startup (~0.5 s delay), so the dashboard sees them as connected. All API control endpoints (`/api/s4/connect`, `/api/hr/connect`, etc.) work normally in simulation mode.

### What's in the flake
- Python 3.12 + all dependencies from pyproject.toml
- Node.js 22 + npm
- SQLite
- ruff, pytest, pytest-asyncio, pytest-mock

---

## Key Docs

| Doc | When to read |
|---|---|
| `docs/architecture-plan.md` | Original design: data models, event bus, API, BLE, DB schema |
| `docs/s4-protocol.md` | WaterRower S4 serial protocol |
| `docs/export.md` | HTTP export contract (public; change it deliberately) |
| `SECURITY.md` | Threat model: no login, cross-site and DNS-rebinding guard |

---

## Source Layout

```
src/
├── main.py           # Entry point — wires all async tasks
├── config.py         # pydantic-settings Settings (loads config.toml)
├── models.py         # RowingMetrics, WorkoutRecord, StrokeRecord (Pydantic v2)
├── events.py         # EventBus + EventType enum
├── merger.py         # Merges S4 + TICKR streams → MERGED_METRICS
├── s4/
│   ├── protocol.py   # S4 memory addresses, command constants, byte parsers
│   └── reader.py     # Async serial reader, ~1Hz poll loop
├── ble/
│   ├── ftms.py       # FTMS Rower peripheral (Pi → Peloton)
│   └── tickr.py      # HRS central reader (TICKR → Pi)
├── workout/
│   ├── state.py      # WorkoutStateMachine
│   ├── recorder.py   # Buffers strokes, flushes to SQLite every 10s
│   ├── counters.py   # Rebases S4 counters to the workout
│   └── fit.py        # FIT file generation
├── web/
│   ├── server.py     # FastAPI app, WebSocket, lifespan
│   ├── guard.py      # Blocks cross-site commands + DNS rebinding (see SECURITY.md)
│   └── routes/       # workouts.py, settings.py, strava.py, export.py
├── export/
│   ├── http.py       # HTTP export: send on WORKOUT_SAVED, retry queue
│   └── payload.py    # JSON body; public contract in docs/export.md
├── strava/
│   ├── auth.py       # OAuth2, token storage + refresh
│   └── upload.py     # FIT upload, status polling
└── storage/
    ├── db.py         # aiosqlite wrapper, migrations
    └── queries.py    # All SQL queries

dashboard/            # React PWA (Vite + TypeScript + Tailwind + shadcn/ui)
tests/
├── conftest.py       # MockSerial, MockBLEClient, in-memory DB
├── unit/
├── integration/
└── e2e/
```

---

## Non-Negotiable Conventions

### Async
- **Never block the event loop.** All I/O must be `await`ed.
- Four top-level coroutines: `s4_reader_task`, `tickr_reader_task`, `ftms_broadcaster_task`, `web_server_task`.
- `ftms_broadcaster_task` is isolated — a crash in the web server must not affect BLE broadcast.

### Data models
- **Pydantic v2 everywhere.** Never pass raw dicts between components.
- Validation runs at every boundary: serial parsing, BLE ingestion, API request/response, SQLite serialisation.
- FastAPI uses the same Pydantic models — no translation layer.
- TypeScript types in `dashboard/src/types.ts` must mirror Pydantic models exactly.

### Event bus
- Components communicate only through the event bus. They never call each other directly.
- Use `asyncio.Queue` internally. Support multiple subscribers per event type.
- `pytest-asyncio` with `asyncio_mode = "auto"`

### Errors and failures
- Raise `ValidationError` or `ProtocolError` at boundaries — never silently swallow bad data.
- Invalid state machine transitions must be rejected (return `409 Conflict` from API).
- Malformed S4 bytes raise `ProtocolError`, not crash.

### Hardware resilience
- **S4 disconnect during active workout:** pause (not end) the workout, publish `S4_DISCONNECTED`, auto-resume on reconnect.
- **TICKR disconnect:** set HR fields to `None` after data is > 3 seconds stale. Never use stale HR values.
- **Stroke data:** flush to SQLite every 10 seconds so partial data survives unexpected shutdown.
- **Boot-time recovery:** check for workouts with `started_at` but no `ended_at`; surface recovery prompt in dashboard.

### TypeScript / Dashboard
- `erasableSyntaxOnly` is enabled — use `as const` objects instead of string enums
- shadcn/ui components go in `dashboard/src/components/ui/`
- shadcn/ui components are **copied into the repo** (owned code, not a dependency)
- Minimum touch target: 64px — the UI must be usable mid-workout at arm's length
- Mobile (< 768px): single column, large metrics, bottom-pinned controls
- Tablet (≥ 768px): two-column, metrics left, Recharts sparkline right

---

## Testing Conventions

- Mock hardware first: `MockSerial` and `MockBLEClient` fixtures in `tests/conftest.py`
- All async tests use `pytest-asyncio`
- Integration tests use an in-memory SQLite DB (`:memory:`)
- Strava tests use `httpx` mock transport — no real API calls
- Make timing configurable in readers/components so tests use fast intervals (not production timeouts)

---

## Target Hardware

Raspberry Pi Zero 2W — constrained: < 50% CPU, < 200MB RAM during an active workout.

---

## Design Context

### Users
- Primary users are individual WaterRower owners using BuoyCast during live indoor rowing workouts.
- The interface is usually viewed on an iPhone or iPad at arm's length while the user is exercising, moving, and only able to glance briefly between strokes.
- The main job to be done is to make workout status, key rowing metrics, and follow-up actions feel immediate and effortless without distracting from the workout itself.

### Brand Personality
- Fun, engaging, clear.
- The product should feel energetic and motivating like a fitness companion, while still being dependable enough for an always-on hardware bridge.
- The interface should reinforce confidence during active workouts and make post-workout actions feel rewarding instead of administrative.

### Aesthetic Direction
- Dark mode only.
- Visual references: Zwift, Strava, Apple Fitness.
- Favor high-contrast, athletic, modern presentation with strong live-data emphasis, crisp hierarchy, and polished motion.
- Avoid default-looking shadcn/Tailwind aesthetics, generic admin-dashboard styling, or anything that feels dull, clinical, or overbuilt for a focused workout flow.

### Design Principles
- Optimize for glanceability first: critical workout data should be readable in under a second on a moving body at arm's length.
- Make the experience feel active and motivating: use bold hierarchy, purposeful color, and moments of energy without sacrificing clarity.
- Keep interactions frictionless under physical strain: large touch targets, obvious states, and minimal decision overhead.
- Preserve trust through restraint: reliability and status clarity matter more than decorative complexity.
- Design mobile-first for the workout moment, then expand to richer tablet layouts without weakening the fast live-use path.
