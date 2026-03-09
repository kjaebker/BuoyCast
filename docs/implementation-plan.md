# BuoyCast — Implementation Plan

## Guiding Principles

- **Data flow first.** The serial reader, data models, event bus, and storage layer must be rock solid before anything else is built on top of them.
- **Test as you go.** Every module gets tests before moving to the next. No catching up later.
- **Simulate hardware early.** Mock serial and BLE interfaces are built in Phase 1 so all subsequent development and testing can happen without the Pi or the rower attached.
- **Vertical slices.** Each phase delivers something runnable and verifiable, not just scaffolding.

---

## Phase 1 — Foundation: Data Models, Config & Project Setup
> Goal: The project skeleton exists, models are defined and validated, config loads correctly, test infrastructure is in place. Nothing touches hardware yet.

### Tasks

- [ ] **1.1 — Repo & tooling setup**
  - Init git repo, `pyproject.toml`, `.gitignore`
  - Create Python virtual environment, `requirements.txt`
  - Configure `pytest` + `pytest-asyncio` in `pyproject.toml`
  - Set up Vite + React + TypeScript frontend scaffold
  - Install Tailwind CSS, shadcn/ui init
  - Install Impeccable: `npx skills add pbakaus/impeccable`
  - Install Recharts via shadcn charts

- [ ] **1.2 — Pydantic models (`src/models.py`)**
  - `RowingMetrics` — all S4 fields + TICKR HR fields with validators
  - `StrokeRecord` — time series entry with field constraints
  - `WorkoutRecord` — summary record with `StravaUploadStatus` enum
  - `WorkoutState` enum: `IDLE`, `ACTIVE`, `PAUSED`, `SUMMARY`
  - WebSocket message envelope model: `WSMessage[T]`

- [ ] **1.3 — Config (`src/config.py`)**
  - `pydantic-settings` `Settings` class with nested models per section
  - Load from `config.toml` with env var override support
  - `config.toml` template with all fields and inline comments
  - Settings singleton pattern — one load at startup, passed via dependency injection

- [ ] **1.4 — Event bus (`src/events.py`)**
  - `EventType` enum covering all system events
  - `Event` Pydantic model with `type` + `payload`
  - `EventBus` class using `asyncio.Queue` with typed publish/subscribe
  - Support multiple subscribers per event type

- [ ] **1.5 — Tests: models & config**
  - `tests/unit/test_models.py`
    - Valid `RowingMetrics` construction
    - Rejects out-of-range stroke rate (< 0, > 60)
    - Rejects invalid heart rate (< 20, > 250)
    - Rejects malformed RR intervals
    - Null fields are accepted and serialise correctly
    - `StravaUploadStatus` enum transitions
  - `tests/unit/test_config.py`
    - Config loads from TOML correctly
    - Missing optional fields use defaults
    - Invalid values raise `ValidationError`
  - `tests/unit/test_events.py`
    - Events publish and deliver to subscribers
    - Multiple subscribers each receive events independently
    - Unknown event types are rejected

**Exit criteria:** `pytest tests/unit/` passes. Models reject invalid data. Config loads cleanly.

---

## Phase 2 — S4 Serial Protocol Layer
> Goal: The full S4 USB protocol is implemented, parseable, and fully tested against captured byte sequences — with no hardware required.

### Tasks

- [ ] **2.1 — Protocol constants (`src/s4/protocol.py`)**
  - All memory addresses from the official WaterRower S4/S5 USB Protocol PDF
  - Command byte constants: `USB_HELLO`, `USB_CLEARMEM`, `IRD`, `IRS`, `IRD3` etc.
  - Response byte constants and expected prefixes
  - Parser functions: raw bytes → typed Python values for each data type (single, double, triple byte integers)
  - Pace → seconds/500m conversion utility
  - Distance high/low byte assembly

- [ ] **2.2 — Serial reader (`src/s4/reader.py`)**
  - `S4Reader` class with async `connect()`, `disconnect()`, `read_loop()` methods
  - USB CDC serial port detection (scan for WaterRower device string)
  - Connection handshake sequence: send `USB_HELLO`, await `S4_HELLO`, send `USB_CLEARMEM`
  - Poll loop: `IRD` commands for all key addresses at configured `poll_interval_hz`
  - Assemble polled values into `RowingMetrics` and publish `METRICS_UPDATE` event
  - Disconnect detection and clean reconnect with configurable delay
  - On S4 disconnect during active workout: publish `S4_DISCONNECTED` event (triggers auto-pause)

- [ ] **2.3 — Mock serial interface (`tests/conftest.py`)**
  - `MockSerial` class that replays pre-captured S4 byte sequences
  - Fixture for steady-state rowing data (constant stroke rate, increasing distance)
  - Fixture for disconnection mid-stream
  - Fixture for malformed/corrupt bytes
  - Fixture for idle S4 (no strokes)

- [ ] **2.4 — Tests: S4 protocol**
  - `tests/unit/test_s4_protocol.py`
    - Parse each address type: single, double, triple byte
    - Pace conversion: raw bytes → correct seconds/500m value
    - Distance assembly: high byte + low byte → correct meters
    - Stroke rate decoding with known byte sequences
    - Power calculation correctness
    - Malformed bytes raise `ProtocolError` not crash
  - `tests/integration/test_s4_reader.py`
    - Reader connects and performs handshake against `MockSerial`
    - Emits `METRICS_UPDATE` events at expected frequency
    - All `RowingMetrics` fields populated from mock data
    - Reader auto-reconnects after `MockSerial` drops connection
    - Reader handles corrupt byte stream gracefully — continues after bad data
    - `S4_DISCONNECTED` event fires on disconnect

**Exit criteria:** `pytest tests/unit/test_s4_protocol.py tests/integration/test_s4_reader.py` passes. Byte parsing is correct for all known address types.

---

## Phase 3 — TICKR Heart Rate Reader
> Goal: BLE central role reads HR and RR interval data from the TICKR, merges into the metrics stream.

### Tasks

- [ ] **3.1 — TICKR BLE reader (`src/ble/tickr.py`)**
  - `TickrReader` class with async `connect()`, `disconnect()`, `start_notify()` methods
  - Connect by MAC address from config (not scan)
  - Subscribe to Heart Rate Measurement characteristic (`0x2A37`)
  - Parse HRS characteristic bytes: flags byte → BPM (uint8 or uint16), RR interval list
  - Publish `METRICS_UPDATE` events with HR payload on each notification
  - Exponential backoff reconnect (1s → 2s → 4s → max 30s)
  - Publish `TICKR_CONNECTED` / `TICKR_DISCONNECTED` events

- [ ] **3.2 — Data merger (`src/merger.py`)**
  - `DataMerger` subscribes to `METRICS_UPDATE` from both S4 and TICKR
  - Maintains latest value for each source independently
  - Merges into single unified `RowingMetrics` on each S4 tick
  - If TICKR data is stale (> 3 seconds old), sets HR fields to `None` rather than using stale value
  - Publishes merged `RowingMetrics` to event bus

- [ ] **3.3 — Mock BLE interface (`tests/conftest.py`)**
  - `MockTickr` that fires BLE HR notifications on a timer
  - Fixture for stable HR (constant BPM, valid RR intervals)
  - Fixture for TICKR disconnect mid-workout
  - Fixture for TICKR unavailable at startup

- [ ] **3.4 — Tests: TICKR and merger**
  - `tests/unit/test_tickr_parser.py`
    - Parse uint8 BPM format
    - Parse uint16 BPM format (flags byte handling)
    - Parse single RR interval
    - Parse multiple RR intervals in one notification
    - Reject out-of-range BPM values
    - Reject invalid RR interval values
  - `tests/integration/test_tickr_reader.py`
    - Connects to `MockTickr` and receives notifications
    - Fires `TICKR_CONNECTED` / `TICKR_DISCONNECTED` events
    - Reconnects after mock disconnect
  - `tests/unit/test_merger.py`
    - Merges S4 metrics + TICKR HR into unified model
    - Falls back to `None` HR when TICKR data is stale
    - S4 metrics flow through when TICKR is disconnected
    - No stale HR bleeds across workout boundaries

**Exit criteria:** `pytest tests/unit/test_tickr_parser.py tests/unit/test_merger.py tests/integration/test_tickr_reader.py` passes.

---

## Phase 4 — Storage Layer
> Goal: SQLite schema, migrations, and all queries are implemented and tested against an in-memory database.

### Tasks

- [ ] **4.1 — Database setup (`src/storage/db.py`)**
  - Async `Database` class wrapping `aiosqlite`
  - Schema migration runner (versioned, idempotent)
  - In-memory mode for tests (`":memory:"`)
  - `get_db()` FastAPI dependency

- [ ] **4.2 — SQL queries (`src/storage/queries.py`)**
  - `insert_workout(record: WorkoutRecord)`
  - `update_workout(id, **fields)` — partial update for Strava status etc.
  - `get_workout(id) → WorkoutRecord | None`
  - `list_workouts(limit, offset) → list[WorkoutRecord]`
  - `delete_workout(id)`
  - `insert_strokes(strokes: list[StrokeRecord])` — bulk insert
  - `get_strokes(workout_id) → list[StrokeRecord]`
  - `get_incomplete_workout() → WorkoutRecord | None` — boot-time recovery check

- [ ] **4.3 — Tests: storage**
  - `tests/integration/test_storage.py`
    - Full workout record round-trip (insert → fetch → compare)
    - `list_workouts` pagination
    - `update_workout` Strava status transition
    - `delete_workout` removes record and strokes
    - Bulk stroke insert and retrieval (1000+ strokes)
    - `get_incomplete_workout` detects workout missing `ended_at`
    - Concurrent writes do not corrupt data

**Exit criteria:** `pytest tests/integration/test_storage.py` passes. All query functions tested.

---

## Phase 5 — Workout State Machine & Recorder
> Goal: The workout lifecycle is correctly managed. State transitions are validated. Stroke data is buffered and flushed reliably.

### Tasks

- [ ] **5.1 — Workout state machine (`src/workout/state.py`)**
  - `WorkoutStateMachine` class with explicit transition methods
  - `start()`, `pause()`, `resume()`, `end()` — manual controls
  - `on_idle_detected()`, `on_rowing_detected()` — smart detection inputs
  - Publishes state change events to event bus
  - Guards invalid transitions (e.g. `pause()` when already `PAUSED`)
  - Timestamps: records `started_at` on start, `ended_at` on end

- [ ] **5.2 — Smart detection**
  - Subscribe to `METRICS_UPDATE` events
  - Track time since last non-zero stroke rate
  - Fire `on_idle_detected()` after `auto_pause_idle_s` of no strokes (during `ACTIVE`)
  - Fire `on_rowing_detected()` on stroke detection (during `PAUSED`)
  - Fire idle warning event after `auto_end_idle_s` (does not auto-end — prompts dashboard)

- [ ] **5.3 — Stroke recorder (`src/workout/recorder.py`)**
  - Subscribes to merged `METRICS_UPDATE` events
  - Only records during `ACTIVE` state
  - Appends `StrokeRecord` to in-memory deque buffer
  - Flushes to SQLite every 10 seconds via bulk insert
  - On workout `end`: final flush, compute summary stats, write `WorkoutRecord`
  - On unexpected shutdown: partial data survives via 10s batch writes

- [ ] **5.4 — FIT file generation (`src/workout/fit.py`)**
  - `generate_fit(workout: WorkoutRecord, strokes: list[StrokeRecord]) → Path`
  - Sets `Sport.ROWING` + `SubSport.INDOOR_ROWING`
  - Session message: total distance, elapsed time, avg HR, avg pace, calories
  - Record messages: one per `StrokeRecord` with timestamp, HR, cadence (stroke rate), power, distance
  - HR time series included when available
  - Saves to configured FIT output directory, path stored in `WorkoutRecord`

- [ ] **5.5 — Tests: state machine, recorder, FIT**
  - `tests/unit/test_workout_state.py`
    - All valid transitions succeed
    - All invalid transitions are rejected with clear error
    - `started_at` set on start, `ended_at` set on end
    - Smart detection fires correct transitions
    - Events published for each state change
  - `tests/unit/test_recorder.py`
    - Records only during `ACTIVE` state
    - Buffer flushes every 10 seconds
    - Final flush on workout end
    - Summary stats computed correctly (avg pace, avg HR, max HR, total strokes)
    - Handles workout with no HR data gracefully
  - `tests/unit/test_fit.py`
    - Generated FIT file parses without errors
    - Session sport/subsport set correctly
    - Stroke count matches input data
    - HR time series present when input includes HR
    - HR omitted cleanly when input has no HR
  - `tests/e2e/test_workout_flow.py`
    - Full flow: start → 5 minutes mock rowing → end → FIT generated → SQLite record complete
    - Auto-pause fires after configured idle seconds
    - Auto-resume fires on stroke detection
    - Workout survives mock S4 disconnect mid-row (pauses, resumes)

**Exit criteria:** `pytest tests/unit/test_workout_state.py tests/unit/test_recorder.py tests/unit/test_fit.py tests/e2e/test_workout_flow.py` passes.

---

## Phase 6 — BLE FTMS Broadcaster
> Goal: Pi advertises as FTMS Rower peripheral. Peloton and WaterRower app can connect and receive live metrics.

### Tasks

- [ ] **6.1 — FTMS broadcaster (`src/ble/ftms.py`)**
  - `FTMSBroadcaster` class using BlueZ D-Bus GATT server
  - Advertise as `BuoyCast` with FTMS Rower service UUID
  - Implement Rower Data characteristic (`0x2AD1`) with correct flag bits
  - Pack `RowingMetrics` into FTMS Rower Data byte format on each update
  - Subscribe to merged `METRICS_UPDATE` events, update characteristic at ~1Hz
  - On client connect: log connection, continue advertising for second client
  - On client disconnect: immediately restart advertising
  - Runs independently — web server errors cannot affect this task

- [ ] **6.2 — FTMS byte packing**
  - Flags field: stroke rate present, total distance present, instantaneous pace present, instantaneous power present, heart rate present (conditional)
  - Stroke rate: uint8, resolution 0.5 SPM (value × 2)
  - Total distance: uint24, meters
  - Instantaneous pace: uint16, seconds/500m
  - Instantaneous power: int16, watts
  - Heart rate: uint8, BPM (omit if not available)

- [ ] **6.3 — Tests: FTMS**
  - `tests/unit/test_ftms_packing.py`
    - Stroke rate encoded at correct resolution
    - Distance packed into uint24 correctly
    - Pace conversion correct
    - Power sign handling (negative power not valid, clamp to 0)
    - Flags byte correctly reflects which fields are present
    - HR omitted when `None`, flags bit cleared
  - Manual verification checklist (cannot fully automate BLE peripheral testing):
    - Peloton app discovers and connects
    - WaterRower Connect app discovers and connects
    - Metrics update live during mock workout
    - Reconnection after app closes and reopens

**Exit criteria:** `pytest tests/unit/test_ftms_packing.py` passes. Manual BLE connection verified with Peloton app on device.

---

## Phase 7 — REST API & WebSocket
> Goal: FastAPI server exposes all endpoints. WebSocket pushes live data. Dashboard can be built against a real API.

### Tasks

- [ ] **7.1 — FastAPI app (`src/web/server.py`)**
  - App factory with lifespan manager (starts background tasks)
  - Static file serving for built dashboard
  - CORS config for dev (dashboard on different port)
  - Global exception handler — returns clean JSON errors

- [ ] **7.2 — Workout routes (`src/web/routes/workouts.py`)**
  - All endpoints from the REST API spec
  - Pydantic response models for all endpoints
  - `POST /api/workout/start|pause|resume|end` — delegates to state machine
  - `POST /api/workouts/{id}/upload` — triggers Strava upload as background task
  - `POST /api/workouts/{id}/skip` — updates upload status

- [ ] **7.3 — WebSocket (`src/web/server.py`)**
  - `WS /ws/live` — accepts connection, adds to subscriber set
  - Broadcasts `WSMessage` on each `METRICS_UPDATE` event
  - Broadcasts state change events immediately (not rate-limited)
  - Graceful client disconnect handling — remove from set, no crash
  - Supports multiple simultaneous connections (iPhone + iPad)

- [ ] **7.4 — System status endpoint**
  - `GET /api/status` returns: S4 connected, TICKR connected, workout state, uptime, last metrics timestamp

- [ ] **7.5 — Tests: API**
  - `tests/integration/test_api.py` using FastAPI `TestClient`
    - All workout CRUD endpoints return correct status codes and response shapes
    - Workout control endpoints trigger correct state transitions
    - Invalid state transitions return `409 Conflict`
    - Upload endpoint returns `202 Accepted` and triggers background task
    - Status endpoint returns all expected fields
    - WebSocket test: connect, receive metrics event, disconnect cleanly

**Exit criteria:** `pytest tests/integration/test_api.py` passes. All endpoints documented and returning correct Pydantic response shapes.

---

## Phase 8 — Strava Integration
> Goal: OAuth flow works. FIT files upload correctly. Status tracking is reliable.

### Tasks

- [ ] **8.1 — OAuth flow (`src/strava/auth.py`)**
  - `GET /api/strava/auth` — build OAuth URL with `activity:write` scope, return to dashboard
  - `GET /api/strava/callback` — exchange code for tokens, store encrypted in SQLite
  - Token refresh: auto-refresh access token when within 5 minutes of expiry
  - `DELETE /api/strava/auth` — revoke and clear tokens
  - `GET /api/strava/status` — connected state, athlete name if connected

- [ ] **8.2 — Upload (`src/strava/upload.py`)**
  - `upload_workout(workout_id)` async function
  - Set `strava_upload_status` to `UPLOADING` immediately
  - Generate FIT file if not already generated
  - POST to `https://www.strava.com/api/v3/uploads` with `sport_type=Rowing`, `data_type=fit`
  - Poll upload status endpoint until `activity_id` available or error
  - On success: set `UPLOADED`, store `strava_activity_id`
  - On failure: set `FAILED`, store error message, allow retry

- [ ] **8.3 — Tests: Strava**
  - `tests/integration/test_strava.py` using `httpx` mock transport
    - OAuth URL built with correct scopes and redirect URI
    - Token exchange stores access + refresh tokens
    - Auto-refresh triggers when token is near expiry
    - Upload sends FIT file with correct sport type
    - Upload status polling handles `processing` → `ready` transition
    - `FAILED` status set correctly on API error (rate limit, invalid token)
    - Retry after failure re-attempts upload from `PENDING`

**Exit criteria:** `pytest tests/integration/test_strava.py` passes. Manual end-to-end Strava upload verified — activity appears in Strava with correct sport type and metrics.

---

## Phase 9 — Dashboard
> Goal: PWA is complete, iPhone and iPad layouts work, all interactions are connected to the live backend.

### Tasks

- [ ] **9.1 — Project setup & design foundation**
  - shadcn/ui component init, install required components
  - Tailwind dark mode config (class strategy)
  - PWA manifest + service worker (Vite PWA plugin)
  - TypeScript types mirroring all Pydantic models
  - Run `/i-audit` (Impeccable) to establish design baseline before building

- [ ] **9.2 — `useWorkoutSocket` hook**
  - Connect to `WS /ws/live`
  - Parse `WSMessage` events into typed state
  - Auto-reconnect on disconnect with exponential backoff
  - Re-connect on `visibilitychange` (handles iOS tab resume)
  - Expose `metrics`, `workoutState`, `s4Connected`, `tickrConnected`

- [ ] **9.3 — `useWakeLock` hook**
  - Acquire wake lock on workout `ACTIVE`
  - Release on `PAUSED`, `IDLE`, `SUMMARY`
  - Handle Safari wake lock API quirks

- [ ] **9.4 — Status bar component**
  - S4 connection status (green/red indicator)
  - TICKR connection status with HR preview
  - Strava auth status
  - Responsive: collapses to icons on iPhone

- [ ] **9.5 — Live metrics component (IDLE / ACTIVE / PAUSED)**
  - iPhone layout: large single-column metrics, bottom controls
  - iPad layout: metrics left, Recharts stroke rate sparkline right (last 60s)
  - Metric tiles: elapsed time, distance, pace, stroke rate, power, calories, heart rate
  - Dimmed state when `IDLE`
  - Clear `PAUSED` indicator
  - Run `/i-polish` and `/i-bolder` on typography and metric sizing

- [ ] **9.6 — Workout controls**
  - Large touch targets (minimum 64px) — usable mid-workout
  - `IDLE`: single `Start Workout` button
  - `ACTIVE`: `Pause` + `End Workout`
  - `PAUSED`: `Resume` + `End Workout`
  - Confirmation dialog on `End Workout` (shadcn `Dialog`)
  - Smart detection notifications: toast-style prompts for start/end suggestions

- [ ] **9.7 — Completion screen**
  - Full workout summary stats
  - Recharts heart rate graph (if HR data available)
  - `Upload to Strava` button — shows loading state during upload
  - `Maybe Later` dismisses to history
  - Strava deep link on success: `strava://activities/{id}`

- [ ] **9.8 — Workout history**
  - Paginated list of completed workouts
  - Per-workout `Badge` for Strava status (colour-coded)
  - Upload / Retry / Strava link actions per workout
  - Expandable detail view with pace + HR chart
  - shadcn `Sheet` for mobile slide-up detail panel
  - Run `/i-audit` to review overall design quality before finalising

- [ ] **9.9 — Offline / error states**
  - Lost connection to Pi: clear banner, auto-retry indicator
  - S4 disconnected during workout: paused state + "Reconnecting..." indicator
  - TICKR disconnected: HR tile shows "–" not stale value

**Exit criteria:** Dashboard works on iPhone Safari and iPad Safari. PWA installable to home screen. Wake lock prevents screen sleep during workout.

---

## Phase 10 — Pi Setup, systemd & Install Script
> Goal: Fresh Pi boots, runs the install script, and is fully operational — no manual steps after initial SSH setup.

### Tasks

- [ ] **10.1 — Install script (`install.sh`)**
  - Install system dependencies: Python 3.11+, BlueZ dev libs, `avahi-daemon`
  - Create virtualenv, install Python requirements
  - Build dashboard (`npm run build`)
  - Copy `config.toml` template if not present
  - Install and enable systemd service
  - Enable mDNS hostname via Avahi
  - Print post-install checklist (set TICKR MAC, set Strava credentials, connect Strava OAuth)

- [ ] **10.2 — systemd service (`waterrower.service`)**
  - `Restart=always`, `RestartSec=5`
  - `After=network.target bluetooth.target`
  - Working directory and venv path configured
  - Logs to journald (`journalctl -u waterrower -f`)

- [ ] **10.3 — Headless Pi OS setup documentation**
  - Raspberry Pi Imager settings (WiFi, SSH, hostname)
  - SSH in and run install script
  - One-time Strava OAuth: open `http://waterrower.local:8080/api/strava/auth` in browser
  - Set TICKR MAC address in `config.toml`
  - Verify all systems: `curl http://waterrower.local:8080/api/status`

- [ ] **10.4 — Hardware connection verification**
  - USB OTG to mini USB connected to S4
  - Confirm S4 beep on Pi boot
  - Confirm TICKR auto-connects on strap worn
  - Confirm BLE advertising visible to Peloton app

**Exit criteria:** Clean Pi install → `install.sh` → working system. Verified on physical hardware.

---

## Phase 11 — Hardening & Polish
> Goal: Edge cases handled, error messages useful, logs readable, performance acceptable on Pi Zero 2W.

### Tasks

- [ ] **11.1 — Boot-time recovery**
  - On startup, check for incomplete workout in SQLite
  - If found: surface recovery prompt in dashboard with option to complete or discard
  - Discarded incomplete workouts move to `SKIPPED` status

- [ ] **11.2 — Performance profiling on Pi**
  - Measure CPU usage during active workout (target: < 50% average)
  - Measure memory usage (target: < 200MB)
  - Identify and resolve any asyncio blocking calls
  - Validate BLE update rate is stable at ~1Hz under load

- [ ] **11.3 — Logging**
  - Structured logging with `structlog`
  - Log levels: `DEBUG` for protocol bytes, `INFO` for state changes, `WARNING` for reconnects, `ERROR` for failures
  - Rotating file handler so logs don't fill the SD card
  - Log S4 connection events, TICKR connection events, workout lifecycle events, Strava upload results

- [ ] **11.4 — Final test pass**
  - Full `pytest` suite passes on Pi hardware
  - Manual workout test: 10 minute row, Peloton connected, TICKR connected, FIT uploaded to Strava
  - Verify Strava activity: correct sport type, distance, HR graph present

---

## Test Coverage Summary

| Module | Unit | Integration | E2E |
|---|---|---|---|
| Pydantic models | ✓ | — | — |
| Config | ✓ | — | — |
| Event bus | ✓ | — | — |
| S4 protocol parser | ✓ | — | — |
| S4 reader | — | ✓ | — |
| TICKR parser | ✓ | — | — |
| TICKR reader | — | ✓ | — |
| Data merger | ✓ | — | — |
| Storage queries | — | ✓ | — |
| Workout state machine | ✓ | — | — |
| Stroke recorder | ✓ | — | — |
| FIT generation | ✓ | — | — |
| FastAPI routes | — | ✓ | — |
| Strava OAuth + upload | — | ✓ | — |
| Full workout flow | — | — | ✓ |

---

## Dependencies Reference

### Python (`requirements.txt`)
```
pydantic>=2.0
pydantic-settings>=2.0
pyserial>=3.5
aiosqlite>=0.19
fastapi>=0.110
uvicorn>=0.29
httpx>=0.27
dbus-python>=1.3
garmin-fit-sdk>=21.141
structlog>=24.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
```

### Frontend (`package.json` key deps)
```
react + react-dom (18)
typescript
vite
tailwindcss
@radix-ui/react-* (via shadcn)
recharts
vite-plugin-pwa
```
