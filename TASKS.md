# TASKS.md â€” BuoyCast Work Tracker

Before starting any task, set its status to `in_progress`. Mark `done` when complete and tests pass. Never start a task already marked `in_progress` or `done`.

**Statuses:** `available` Â· `in_progress` Â· `done` Â· `blocked`

---

## Phase 1 â€” Foundation: Data Models, Config & Project Setup

| ID | Task | Status |
|---|---|---|
| 1.1 | Repo & tooling setup (pyproject.toml, venv, pytest config, Vite+React scaffold, Tailwind, shadcn/ui, Impeccable, Recharts) | done |
| 1.2 | Pydantic models â€” RowingMetrics, StrokeRecord, WorkoutRecord, WorkoutState enum, WSMessage envelope (`src/models.py`) | done |
| 1.3 | Config â€” pydantic-settings Settings class + config.toml template (`src/config.py`) | done |
| 1.4 | Event bus â€” EventType enum, Event model, EventBus with asyncio.Queue, multiple subscribers (`src/events.py`) | done |
| 1.5 | Tests â€” models, config, events (`tests/unit/test_models.py`, `test_config.py`, `test_events.py`) | done |

**Phase 1 exit criteria:** `pytest tests/unit/` passes. Models reject invalid data. Config loads cleanly. âœ…

---

## Phase 2 â€” S4 Serial Protocol Layer

| ID | Task | Status |
|---|---|---|
| 2.1 | Protocol constants + parsers â€” all memory addresses, command bytes, parse functions, pace/distance utils (`src/s4/protocol.py`) | done |
| 2.2 | Serial reader â€” S4Reader class, USB CDC detection, handshake, poll loop, METRICS_UPDATE publish, reconnect logic (`src/s4/reader.py`) | done |
| 2.3 | MockSerial fixtures â€” steady-state, disconnect, corrupt bytes, idle (`tests/conftest.py`) | done |
| 2.4 | Tests â€” S4 protocol unit tests + reader integration tests (`tests/unit/test_s4_protocol.py`, `tests/integration/test_s4_reader.py`) | done |

**Phase 2 exit criteria:** S4 unit + integration tests pass. Byte parsing correct for all known address types. âœ…

---

## Phase 3 â€” TICKR Heart Rate Reader

| ID | Task | Status |
|---|---|---|
| 3.1 | TICKR BLE reader â€” TickrReader class, connect by MAC, HRS characteristic subscribe, BPM + RR parsing, exponential backoff reconnect, events (`src/ble/tickr.py`) | done |
| 3.2 | Data merger â€” merges S4 + TICKR streams, staleness check (> 3s â†’ None), publishes MERGED_METRICS (`src/merger.py`) | done |
| 3.3 | MockBLEClient fixtures â€” stable HR, disconnect mid-workout, unavailable at startup (`tests/conftest.py`) | done |
| 3.4 | Tests â€” TICKR parser unit, TICKR reader integration, merger unit (`tests/unit/test_tickr_parser.py`, `tests/integration/test_tickr_reader.py`, `tests/unit/test_merger.py`) | done |

**Phase 3 exit criteria:** TICKR + merger tests pass. âœ…

---

## Phase 4 â€” Storage Layer

| ID | Task | Status |
|---|---|---|
| 4.1 | Database setup â€” async Database class, schema migrations, in-memory test mode, get_db() dependency (`src/storage/db.py`) | done |
| 4.2 | SQL queries â€” insert/update/get/list/delete workout, bulk insert strokes, get strokes, get_incomplete_workout (`src/storage/queries.py`) | done |
| 4.3 | Tests â€” full workout round-trip, pagination, status updates, delete cascade, bulk strokes, recovery detection, concurrent writes (`tests/integration/test_storage.py`) | done |

**Phase 4 exit criteria:** `pytest tests/integration/test_storage.py` passes. All query functions tested. âœ…

---

## Phase 5 â€” Workout State Machine & Recorder

| ID | Task | Status |
|---|---|---|
| 5.1 | Workout state machine â€” WorkoutStateMachine, start/pause/resume/end, smart detection inputs, event publishing, transition guards (`src/workout/state.py`) | done |
| 5.2 | Smart detection â€” idle detection (auto-pause after N seconds), rowing detection (auto-resume), idle warning event | done |
| 5.3 | Stroke recorder â€” subscribes to MERGED_METRICS, ACTIVE-only recording, 10s flush to SQLite, final flush + summary stats on end (`src/workout/recorder.py`) | done |
| 5.4 | FIT file generation â€” Sport.ROWING + SubSport.INDOOR_ROWING, session message, record messages per stroke, HR time series (`src/workout/fit.py`) | done |
| 5.5 | Tests â€” state machine unit, recorder unit, FIT unit, full e2e workout flow (`tests/unit/test_workout_state.py`, `test_recorder.py`, `test_fit.py`, `tests/e2e/test_workout_flow.py`) | done |

**Phase 5 exit criteria:** `pytest tests/unit/test_workout_state.py tests/unit/test_recorder.py tests/unit/test_fit.py tests/e2e/test_workout_flow.py` passes.

---

## Phase 6 â€” BLE FTMS Broadcaster

| ID | Task | Status |
|---|---|---|
| 6.1 | FTMS broadcaster â€” BlueZ D-Bus GATT server, advertise as BuoyCast, Rower Data characteristic 0x2AD1, ~1Hz updates, client disconnect â†’ restart advertising (`src/ble/ftms.py`) | done |
| 6.2 | FTMS byte packing â€” flags field, stroke rate uint8 (Ã—2), distance uint24, pace uint16, power int16, HR uint8 conditional | done |
| 6.3 | Tests â€” FTMS packing unit tests (`tests/unit/test_ftms_packing.py`) + manual Peloton connection checklist | done |

**Phase 6 exit criteria:** `pytest tests/unit/test_ftms_packing.py` passes. Manual BLE connection verified with Peloton app on device.

---

## Phase 7 â€” REST API & WebSocket

| ID | Task | Status |
|---|---|---|
| 7.1 | FastAPI app â€” app factory, lifespan manager, static file serving, CORS, global exception handler (`src/web/server.py`) | done |
| 7.2 | Workout routes â€” all CRUD + control + upload endpoints, Pydantic response models (`src/web/routes/workouts.py`) | done |
| 7.3 | WebSocket â€” WS /ws/live, broadcast on MERGED_METRICS, state change events, multi-client support, clean disconnect handling | done |
| 7.4 | System status endpoint â€” GET /api/status with S4/TICKR state, workout state, uptime, last metrics timestamp | done |
| 7.5 | Tests â€” all endpoints, state transitions, 409 handling, 202 upload, WebSocket (`tests/integration/test_api.py`) | done |

**Phase 7 exit criteria:** `pytest tests/integration/test_api.py` passes. All endpoints returning correct Pydantic response shapes.

---

## Phase 8 â€” Strava Integration

| ID | Task | Status |
|---|---|---|
| 8.1 | OAuth flow â€” auth URL build, callback token exchange, token storage, auto-refresh, revoke (`src/strava/auth.py`) | done |
| 8.2 | Upload â€” FIT upload to Strava API, status polling, UPLOADED/FAILED handling, retry support (`src/strava/upload.py`) | done |
| 8.3 | Tests â€” OAuth URL, token exchange, auto-refresh, upload with correct sport type, status polling, failure handling (`tests/integration/test_strava.py`) | done |

**Phase 8 exit criteria:** `pytest tests/integration/test_strava.py` passes. Manual end-to-end Strava upload verified.

---

## Phase 9 â€” Dashboard

| ID | Task | Status |
|---|---|---|
| 9.1 | Project setup â€” shadcn/ui init, Tailwind dark mode, PWA manifest + service worker, TypeScript types mirroring Pydantic models | done |
| 9.2 | useWorkoutSocket hook â€” WebSocket lifecycle, typed state parsing, exponential backoff reconnect, visibilitychange reconnect | done |
| 9.3 | useWakeLock hook â€” acquire on ACTIVE, release on PAUSED/IDLE/SUMMARY, Safari quirk handling | done |
| 9.4 | StatusBar component â€” S4 status, TICKR status + HR preview, Strava auth status, responsive icon collapse | done |
| 9.5 | LiveMetrics component â€” iPhone single-column, iPad two-column + sparkline, all metric tiles, IDLE/PAUSED states (run /polish /bolder) | done |
| 9.6 | WorkoutControls component â€” 64px+ touch targets, per-state button sets, end confirmation Dialog, smart detection toasts | done |
| 9.7 | CompletionScreen component â€” summary stats, HR chart, Upload to Strava button with loading state, Strava deep link | done |
| 9.8 | WorkoutHistory component â€” paginated list, Strava status badges, upload/retry/link actions, expandable detail, Sheet for mobile (run /audit) | done |
| 9.9 | Offline/error states â€” lost Pi connection banner, S4 disconnect indicator, TICKR HR tile "â€“" state | done |

**Phase 9 exit criteria:** Works on iPhone Safari + iPad Safari. PWA installable to home screen. Wake lock prevents sleep during workout.

---

## Phase 10 â€” Pi Setup, systemd & Install Script

| ID | Task | Status |
|---|---|---|
| 10.1 | Install script â€” system deps, venv, dashboard build, config.toml template, systemd service, Avahi mDNS, post-install checklist (`install.sh`) | done |
| 10.2 | systemd service â€” Restart=always, After=bluetooth.target, journald logging (`waterrower.service`) | done |
| 10.3 | Headless Pi OS setup docs â€” Imager settings, SSH, install script, Strava OAuth, TICKR MAC, verify with curl | done |
| 10.4 | Hardware verification checklist â€” USB OTG â†’ S4 beep, TICKR auto-connect, FTMS visible to Peloton | done |

**Phase 10 exit criteria:** Clean Pi install â†’ `install.sh` â†’ working system. Verified on physical hardware.

---

## Phase 11 â€” Hardening & Polish

| ID | Task | Status |
|---|---|---|
| 11.1 | Boot-time recovery â€” detect incomplete workout on startup, surface prompt in dashboard, discard â†’ SKIPPED | done |
| 11.2 | Performance profiling â€” CPU < 50% avg, RAM < 200MB, no blocking asyncio calls, BLE stable at ~1Hz under load | done |
| 11.3 | Structured logging â€” structlog setup, log levels per convention, rotating file handler (`src/`) | done |
| 11.4 | Final test pass — full pytest suite on Pi hardware, 10-min manual workout with Peloton + TICKR + Strava upload | available |
| 11.5 | Dashboard polish — align workout history detail sheet with live dashboard aesthetic (dashboard/src/components/WorkoutHistory.tsx, dashboard/src/components/ui/sheet.tsx) | done |
| 11.6 | Dashboard polish — center and size workout history detail drawer correctly (dashboard/src/components/ui/sheet.tsx) | done |
| 11.7 | Dashboard polish — make sheet overlay geometry fully controlled by the app instead of the native dialog box (dashboard/src/components/ui/sheet.tsx) | done |
| 11.8 | Dashboard polish — treat workout history detail as a centered modal instead of a drawer (dashboard/src/components/ui/sheet.tsx) | done |
| 11.9 | Dashboard polish — replace native dialog-based sheet with portal overlay panel (dashboard/src/components/ui/sheet.tsx) | done |
| 11.10 | Dashboard polish — fix portal dark-mode inheritance and modal height constraints (dashboard/src/components/ui/sheet.tsx) | done |
| 11.11 | Dashboard polish — soften harsh top glow transitions in dashboard shells (dashboard/src/App.tsx, dashboard/src/components/ui/sheet.tsx) | done |
| 11.12 | Dashboard polish — remove non-functional modal close icon (dashboard/src/components/ui/sheet.tsx) | in_progress |
| 11.13 | Fix Vite OOM on Pi Zero 2W — add manualChunks to vite.config.ts and cap Node heap in install.sh | done |
| 11.14 | Move dashboard build to GitHub Actions — dashboard/dist tracked in repo, Pi just does git pull, Node.js removed from install.sh, update.sh added | done |

**Phase 11 exit criteria:** Full `pytest` suite passes on Pi. Manual 10-minute workout verified end-to-end.

















