# AGENTS.md — BuoyCast

Read this before writing any code. For full specs, see `docs/`.

---

## Docs to Read First

| Doc | When to read |
|---|---|
| `docs/product-plan.md` | Understand what BuoyCast is and what it must do |
| `docs/architecture-plan.md` | Tech stack, data models, event bus, API spec, BLE, S4 protocol, DB schema |
| `docs/implementation-plan.md` | Phase-by-phase task breakdown with exit criteria |

---

## Project at a Glance

Raspberry Pi Zero 2W — reads WaterRower S4 over USB serial, merges Wahoo TICKR HR over BLE, fans data to: BLE FTMS broadcast (Peloton), WebSocket dashboard (React PWA), SQLite store. Strava upload is manual. Runs headless, managed by systemd.

**Target hardware is constrained:** < 50% CPU, < 200MB RAM during an active workout.

---

## Source Layout

```
src/
├── main.py           # Entry point — wires all async tasks
├── config.py         # pydantic-settings Settings (loads config.toml)
├── models.py         # RowingMetrics, WorkoutRecord, StrokeRecord (Pydantic v2)
├── events.py         # EventBus + EventType enum
├── merger.py         # Merges S4 + TICKR streams into unified RowingMetrics
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
├── conftest.py       # MockSerial, MockTickr, in-memory DB
├── unit/
├── integration/
└── e2e/
```

---

## Build Order

Follow the phases in `docs/implementation-plan.md`. Do not skip ahead — each phase builds on the last.

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | Models, config, event bus, project scaffold | `pytest tests/unit/` passes |
| 2 | S4 serial protocol + reader | S4 unit + integration tests pass |
| 3 | TICKR BLE reader + data merger | TICKR + merger tests pass |
| 4 | SQLite storage layer | Storage integration tests pass |
| 5 | Workout state machine, recorder, FIT file | State + recorder + FIT + e2e flow pass |
| 6 | BLE FTMS broadcaster | FTMS packing tests pass + manual Peloton verify |
| 7 | REST API + WebSocket | API integration tests pass |
| 8 | Strava OAuth + upload | Strava integration tests pass + manual upload verified |
| 9 | React PWA dashboard | Works on iPhone + iPad Safari; installable to home screen |
| 10 | Pi install script + systemd service | Fresh Pi → `install.sh` → working system |
| 11 | Hardening: logging, recovery, perf | Full suite passes on Pi hardware |

---

## Non-Negotiable Conventions

### Async
- **Never block the event loop.** All I/O must be `await`ed.
- Four top-level coroutines: `s4_reader_task`, `tickr_reader_task`, `ftms_broadcaster_task`, `web_server_task`. See architecture doc for details.
- `ftms_broadcaster_task` is isolated — a crash in the web server must not affect BLE broadcast.

### Data models
- **Pydantic v2 everywhere.** Never pass raw dicts between components.
- Validation runs at every boundary: serial parsing, BLE ingestion, API request/response, SQLite serialisation.
- FastAPI uses the same Pydantic models — no translation layer.
- TypeScript types in `dashboard/src/types.ts` must mirror Pydantic models exactly.

### Event bus
- Components communicate only through the event bus. They never call each other directly.
- Use `asyncio.Queue` internally. Support multiple subscribers per event type.

### Errors and failures
- Raise `ValidationError` or `ProtocolError` at boundaries — never silently swallow bad data.
- Invalid state machine transitions must be rejected (return `409 Conflict` from API).
- Malformed S4 bytes raise `ProtocolError`, not crash.

### Hardware resilience
- **S4 disconnect during active workout:** pause (not end) the workout, publish `S4_DISCONNECTED`, auto-resume on reconnect.
- **TICKR disconnect:** set HR fields to `None` after data is > 3 seconds stale. Never use stale HR values.
- **Stroke data:** flush to SQLite every 10 seconds so partial data survives unexpected shutdown.
- **Boot-time recovery:** check for workouts with `started_at` but no `ended_at`; surface recovery prompt in dashboard.

### Logging
- Use `structlog` throughout.
- Levels: DEBUG for protocol bytes, INFO for state changes, WARNING for reconnects, ERROR for failures.
- Rotating file handler — do not fill the SD card.

---

## Testing Conventions

- Mock hardware first: `MockSerial` and `MockTickr` fixtures in `tests/conftest.py` must exist before any reader tests.
- All async tests use `pytest-asyncio`.
- Integration tests use an in-memory SQLite DB (`:memory:`).
- Strava tests use `httpx` mock transport — no real API calls.
- Run the full suite: `pytest`

Required test files are listed in `docs/implementation-plan.md` under each phase.

---

## Dashboard Notes

- Minimum touch target: 64px — the UI must be usable mid-workout at arm's length.
- Mobile (< 768px): single column, large metrics, bottom-pinned controls.
- Tablet (≥ 768px): two-column, metrics left, Recharts sparkline right.
- `useWorkoutSocket` must reconnect on `visibilitychange` (iOS tab suspension).
- `useWakeLock` — acquire on `ACTIVE`, release on `PAUSED` / `IDLE` / `SUMMARY`.
- shadcn/ui components are **copied into the repo** (owned code, not a dependency).
- Run Impeccable commands (`/polish`, `/audit`, `/bolder`) during Phase 9 to reach non-generic UI quality.
