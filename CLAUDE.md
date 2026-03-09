# BuoyCast — Claude Code Instructions

Read this before writing any code. For full specs, see `docs/`.

---

## Task Tracking (TASKS.md)

All work is tracked in `TASKS.md`. Follow this protocol every time.

**Before starting any task:**
1. Read `TASKS.md` in full
2. Find an `available` task that fits your scope
3. Set its status to `in_progress`
4. Only then start coding

**When done:**
- Run the phase's exit criteria tests before marking done
- Never mark done if tests are failing
- Set status to `done`
- Commit after each task (not at the end of a phase)

**If blocked:** set status to `blocked` and add a note explaining why.

**Never:**
- Start a task already marked `in_progress` or `done`
- Skip updating TASKS.md — do it at start AND end of every task

---

## Workflow
- Commit messages follow conventional commits: `feat:`, `fix:`, `chore:`, `test:`, etc.
- Run the full test suite before committing: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Follow the phases in `docs/implementation-plan.md` — do not skip ahead

---

## Build/Run Commands
- Python tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Dashboard build: `export PATH="/c/Program Files/nodejs:$PATH" && npm run build` (from dashboard/)
- Dashboard type-check: `npx tsc --noEmit` (from dashboard/)
- Install Python deps: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`

---

## Key Docs

| Doc | When to read |
|---|---|
| `docs/product-plan.md` | Understand what BuoyCast is and what it must do |
| `docs/architecture-plan.md` | Tech stack, data models, event bus, API spec, BLE, S4 protocol, DB schema |
| `docs/implementation-plan.md` | Phase-by-phase task breakdown with exit criteria |

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
│   └── fit.py        # FIT file generation
├── web/
│   ├── server.py     # FastAPI app, WebSocket, lifespan
│   └── routes/       # workouts.py, config.py
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
- Required test files are listed in `docs/implementation-plan.md` under each phase

---

## Target Hardware

Raspberry Pi Zero 2W — constrained: < 50% CPU, < 200MB RAM during an active workout.
