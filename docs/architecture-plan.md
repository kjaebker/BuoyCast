# BuoyCast — Architecture Plan

> This is the original design document. The code is the source of truth where
> they differ; it's kept for the reasoning behind the design.

## System Overview

BuoyCast runs entirely on a Raspberry Pi Zero 2W. It reads workout data from a WaterRower S4 monitor over USB serial, merges in heart rate data from a Wahoo TICKR chest strap over BLE, and fans that data out to a BLE FTMS broadcast, a local WebSocket dashboard, and a SQLite workout store. Strava upload is triggered manually via the dashboard.

```
┌─────────────────┐     USB Serial      ┌──────────────────────────────────────────┐
│  WaterRower S4  │────────────────────►│                                          │
└─────────────────┘                     │           Raspberry Pi Zero 2W           │
                                        │                                          │
┌─────────────────┐     BLE (HRS)       │  ┌────────────┐    ┌─────────────────┐  │
│  Wahoo TICKR    │────────────────────►│  │ S4 Reader  │    │  TICKR Reader   │  │
└─────────────────┘                     │  └─────┬──────┘    └───────┬─────────┘  │
                                        │        │                   │            │
                                        │        └────────┬──────────┘            │
                                        │                 │                       │
                                        │          ┌──────▼──────┐                │
                                        │          │ Data Merger │                │
                                        │          └──────┬──────┘                │
                                        │                 │                       │
                                        │          ┌──────▼──────┐                │
                                        │          │  Event Bus  │                │
                                        │          └──┬───┬───┬──┘                │
                                        │             │   │   │                   │
                                        │    ┌────────┘   │   └──────────┐        │
                                        │    │            │              │        │
                                        │ ┌──▼───┐  ┌────▼─────┐  ┌────▼──────┐  │
                                        │ │ BLE  │  │   Web    │  │  Workout  │  │
                                        │ │ FTMS │  │  Server  │  │ Recorder  │  │
                                        │ └──────┘  └────┬─────┘  └────┬──────┘  │
                                        │                │             │         │
                                        └────────────────┼─────────────┼─────────┘
                                                         │             │
                                               ┌─────────▼──┐   ┌─────▼──────┐
                                               │  Dashboard  │   │   SQLite   │
                                               │  (PWA)      │   │   (local)  │
                                               └─────────────┘   └─────┬──────┘
                                                                        │
                                                                 ┌──────▼──────┐
                                                                 │   Strava    │
                                                                 │  (manual)   │
                                                                 └─────────────┘
```

---

## Technology Stack

### Backend

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Best BLE/BlueZ ecosystem; existing community code in Python |
| Data models | Pydantic v2 | Validation at every boundary; native FastAPI integration; replaces plain dataclasses throughout |
| Config management | `pydantic-settings` | Type-safe config from TOML + env var override; replaces raw `tomllib` |
| BLE | BlueZ via D-Bus (`dbus-python`) | Linux-native, most stable BLE stack for Pi |
| Serial | `pyserial` | Standard, well-tested serial library |
| Async runtime | `asyncio` | Native Python async; avoids heavyweight threading |
| Web server | FastAPI | Lightweight, async-native, WebSocket support built in; shares Pydantic models with data layer |
| Storage | SQLite via `aiosqlite` | Reliable, embedded, handles write pattern well |
| FIT generation | `garmin-fit-sdk` | Official Garmin SDK for FIT file generation |
| Strava API | `httpx` (async HTTP client) | Async-compatible, clean API |
| Testing | `pytest` + `pytest-asyncio` | Async-native test runner; `pytest-mock` for serial/BLE mocking |
| Process manager | systemd | Reliable service management; auto-restart on crash |

### Frontend

| Layer | Technology | Rationale |
|---|---|---|
| Framework | React 18 + TypeScript | Component model, strong typing, good mobile PWA support |
| Build tool | Vite | Fast HMR in dev, optimised production builds |
| Styling | Tailwind CSS | Utility-first, responsive breakpoints, dark mode |
| Component library | shadcn/ui | Owns the code, Radix UI accessibility primitives, Tailwind-native |
| Data visualisation | Recharts (via shadcn charts) | Real-time sparklines, post-workout HR/pace graphs; matches shadcn aesthetic |
| Design tooling | Impeccable (impeccable.style) | 17 design commands (`/polish`, `/audit`, `/bolder` etc.) for non-generic UI quality |
| State management | React `useReducer` | Mirrors backend workout state machine; driven by WebSocket events |

---

## Project Structure

```
buoycast/
├── config.toml                  # All user configuration
├── install.sh                   # One-shot setup script
├── waterrower.service           # systemd service definition
├── requirements.txt
├── pyproject.toml               # Project metadata, pytest config
├── src/
│   ├── main.py                  # Entry point, wires everything together
│   ├── config.py                # pydantic-settings Settings class (replaces tomllib)
│   ├── models.py                # Pydantic models: RowingMetrics, WorkoutRecord, StrokeRecord
│   ├── events.py                # Event bus definitions and types
│   ├── s4/
│   │   ├── reader.py            # USB serial reader, S4 protocol polling loop
│   │   └── protocol.py          # S4 memory addresses, command constants, parsing
│   ├── ble/
│   │   ├── ftms.py              # FTMS Rower peripheral broadcaster
│   │   └── tickr.py             # TICKR HRS central reader
│   ├── merger.py                # Combines S4 + TICKR streams into RowingMetrics
│   ├── workout/
│   │   ├── state.py             # WorkoutState machine + transition logic
│   │   ├── recorder.py          # Writes stroke data to SQLite during workout
│   │   └── fit.py               # Generates FIT file from completed WorkoutRecord
│   ├── web/
│   │   ├── server.py            # FastAPI app, WebSocket handler, REST endpoints
│   │   ├── routes/
│   │   │   ├── workouts.py      # Workout CRUD, history, upload trigger
│   │   │   └── config.py        # Config read/update endpoints
│   │   └── dashboard/           # React PWA static build (served by FastAPI)
│   ├── strava/
│   │   ├── auth.py              # OAuth2 flow, token storage, refresh
│   │   └── upload.py            # FIT file upload, status tracking
│   └── storage/
│       ├── db.py                # SQLite connection, migrations
│       └── queries.py           # All SQL queries in one place
├── tests/
│   ├── conftest.py              # Shared fixtures (mock serial, mock BLE, in-memory DB)
│   ├── unit/
│   │   ├── test_s4_protocol.py  # S4 byte parsing, memory address decoding
│   │   ├── test_models.py       # Pydantic model validation edge cases
│   │   ├── test_merger.py       # Data merger logic, null handling
│   │   ├── test_workout_state.py # State machine transitions
│   │   ├── test_recorder.py     # Stroke buffering, batch write logic
│   │   └── test_fit.py          # FIT file generation correctness
│   ├── integration/
│   │   ├── test_s4_reader.py    # Reader with mock serial port
│   │   ├── test_storage.py      # SQLite queries against in-memory DB
│   │   ├── test_strava.py       # Strava upload flow with httpx mock
│   │   └── test_api.py          # FastAPI endpoints with TestClient
│   └── e2e/
│       └── test_workout_flow.py # Full workout lifecycle: start → row → end → upload
└── dashboard/                   # Frontend source
    ├── src/
    │   ├── App.tsx
    │   ├── components/
    │   │   ├── ui/               # shadcn/ui installed components
    │   │   ├── LiveMetrics.tsx
    │   │   ├── WorkoutControls.tsx
    │   │   ├── CompletionScreen.tsx
    │   │   ├── WorkoutHistory.tsx
    │   │   ├── MetricSparkline.tsx   # Recharts real-time sparkline
    │   │   └── StatusBar.tsx         # TICKR + Strava connection status
    │   ├── hooks/
    │   │   ├── useWorkoutSocket.ts   # WebSocket connection + reconnect
    │   │   └── useWakeLock.ts        # Screen wake lock API
    │   └── types.ts
    ├── package.json
    └── vite.config.ts
```

---

## Core Data Models

All models use **Pydantic v2 `BaseModel`**. Validation runs at every boundary — serial parsing, BLE data ingestion, API request/response, and SQLite serialisation. FastAPI uses these models directly for request and response schemas with no translation layer.

### RowingMetrics
The unified real-time data structure shared across all components.

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class RowingMetrics(BaseModel):
    timestamp: datetime
    # S4 data
    stroke_rate: float | None = Field(None, ge=0, le=60)
    stroke_count: int | None = Field(None, ge=0)
    distance_m: float | None = Field(None, ge=0)
    pace_s_per_500m: float | None = Field(None, ge=0)
    power_watts: float | None = Field(None, ge=0)
    calories: int | None = Field(None, ge=0)
    elapsed_seconds: int | None = Field(None, ge=0)
    drive_length_cm: float | None = Field(None, ge=0, le=200)
    # TICKR data
    heart_rate_bpm: int | None = Field(None, ge=20, le=250)
    rr_intervals_ms: list[int] | None = None

    @field_validator("rr_intervals_ms")
    @classmethod
    def validate_rr_intervals(cls, v):
        if v is not None:
            if any(i < 200 or i > 2000 for i in v):
                raise ValueError("RR intervals must be between 200ms and 2000ms")
        return v
```

### WorkoutRecord
Stored in SQLite. One record per completed workout.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class StravaUploadStatus(str, Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class WorkoutRecord(BaseModel):
    id: str                          # UUID
    started_at: datetime
    ended_at: datetime
    total_distance_m: float = Field(ge=0)
    total_strokes: int = Field(ge=0)
    elapsed_seconds: int = Field(ge=0)
    avg_pace_s_per_500m: float | None = None
    avg_stroke_rate: float | None = None
    avg_power_watts: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    calories: int = Field(default=0, ge=0)
    strava_upload_status: StravaUploadStatus = StravaUploadStatus.PENDING
    strava_activity_id: int | None = None
    strava_error: str | None = None
    fit_file_path: str | None = None
```

### StrokeRecord
Time series data. One record per second during active workout.

```python
class StrokeRecord(BaseModel):
    workout_id: str
    ts: datetime
    distance_m: float = Field(ge=0)
    stroke_rate: float = Field(ge=0, le=60)
    power_watts: float | None = None
    pace_s_per_500m: float | None = None
    heart_rate_bpm: int | None = Field(None, ge=20, le=250)
    rr_intervals_ms: list[int] | None = None
```

### Settings
Config loaded from `config.toml` via `pydantic-settings`.

```python
from pydantic_settings import BaseSettings, TomlConfigSettingsSource

class S4Settings(BaseModel):
    baud_rate: int = 19200
    poll_interval_hz: float = 1.0
    reconnect_delay_s: int = 5

class HeartRateSettings(BaseModel):
    enabled: bool = True
    device_mac: str = ""
    device_name: str = ""
    required: bool = False

class WorkoutSettings(BaseModel):
    auto_pause_idle_s: int = 30
    auto_end_idle_s: int = 300
    min_workout_distance_m: float = 100

class Settings(BaseSettings):
    s4: S4Settings = S4Settings()
    heart_rate: HeartRateSettings = HeartRateSettings()
    workout: WorkoutSettings = WorkoutSettings()
    # ... server, strava, analytics sections

    model_config = SettingsConfigDict(toml_file="config.toml")
```

---

## Thread / Task Model

All async via `asyncio`. Four main coroutines running concurrently:

```
asyncio event loop
├── s4_reader_task          # HIGH priority — serial poll loop, ~1Hz
├── tickr_reader_task       # HIGH priority — BLE central, event-driven
├── ftms_broadcaster_task   # HIGH priority — BLE peripheral, ~1Hz update
└── web_server_task         # NORMAL priority — FastAPI/uvicorn
    └── background_tasks    # LOW priority — Strava uploads, FIT generation
```

The event bus uses `asyncio.Queue` instances — the S4 reader and TICKR reader push `RowingMetrics` events; all consumers subscribe independently.

---

## Event Bus

```python
class EventType(Enum):
    METRICS_UPDATE = "metrics_update"       # New RowingMetrics available
    WORKOUT_STARTED = "workout_started"
    WORKOUT_PAUSED = "workout_paused"
    WORKOUT_RESUMED = "workout_resumed"
    WORKOUT_ENDED = "workout_ended"         # Payload: completed WorkoutRecord
    TICKR_CONNECTED = "tickr_connected"
    TICKR_DISCONNECTED = "tickr_disconnected"
    S4_CONNECTED = "s4_connected"
    S4_DISCONNECTED = "s4_disconnected"
    STRAVA_UPLOAD_STATUS = "strava_upload_status"
```

Each component registers a handler for the events it cares about. Loose coupling — components never call each other directly.

---

## SQLite Schema

```sql
CREATE TABLE workouts (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    total_distance_m REAL NOT NULL,
    total_strokes INTEGER NOT NULL,
    elapsed_seconds INTEGER NOT NULL,
    avg_pace_s_per_500m REAL,
    avg_stroke_rate REAL,
    avg_power_watts REAL,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    calories INTEGER,
    strava_upload_status TEXT NOT NULL DEFAULT 'PENDING',
    strava_activity_id INTEGER,
    strava_error TEXT,
    fit_file_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE strokes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id TEXT NOT NULL REFERENCES workouts(id),
    ts TEXT NOT NULL,
    distance_m REAL,
    stroke_rate REAL,
    power_watts REAL,
    pace_s_per_500m REAL,
    heart_rate_bpm INTEGER,
    rr_intervals_ms TEXT    -- JSON array
);

CREATE INDEX idx_strokes_workout_id ON strokes(workout_id);
CREATE INDEX idx_workouts_started_at ON workouts(started_at DESC);
```

---

## REST API Endpoints

```
GET  /api/status                    System status (S4 connected, TICKR connected, workout state)
GET  /api/workouts                  List all workouts (summary, paginated)
GET  /api/workouts/{id}             Single workout detail
GET  /api/workouts/{id}/strokes     Time series stroke data for a workout
POST /api/workouts/{id}/upload      Trigger Strava upload for a workout
POST /api/workouts/{id}/skip        Mark workout as SKIPPED (won't prompt again)
DELETE /api/workouts/{id}           Delete a workout record

POST /api/workout/start             Start workout (manual control)
POST /api/workout/pause             Pause workout
POST /api/workout/resume            Resume workout
POST /api/workout/end               End workout

GET  /api/strava/auth               Initiate OAuth flow (returns redirect URL)
GET  /api/strava/callback           OAuth callback handler
GET  /api/strava/status             Auth status (connected / token expiry)
DELETE /api/strava/auth             Disconnect Strava

GET  /api/config                    Read non-sensitive config
PUT  /api/config                    Update config values
```

### WebSocket

```
WS /ws/live
```

Pushes `RowingMetrics` JSON every second during workout and on any state change event. Client reconnects automatically on disconnect.

```json
{
  "type": "metrics_update",
  "data": {
    "stroke_rate": 24.5,
    "distance_m": 1842,
    "pace_s_per_500m": 118,
    "power_watts": 187,
    "heart_rate_bpm": 152,
    "elapsed_seconds": 723,
    "calories": 210,
    "stroke_count": 352,
    "workout_state": "active"
  }
}
```

---

## BLE Architecture

The Pi Zero 2W acts as **both** BLE central and BLE peripheral simultaneously via BlueZ.

### As Peripheral — FTMS Rower (for Peloton / WaterRower app)
- Advertises as `BuoyCast`
- Implements FTMS Rower Data characteristic (UUID `0x2AD1`)
- Updates at ~1Hz during active workout
- Auto-restarts advertising on client disconnect

### As Central — Heart Rate Service (for TICKR)
- Scans for and connects to TICKR by MAC address (config)
- Subscribes to Heart Rate Measurement characteristic (UUID `0x2A37`)
- Parses BPM and RR interval bytes per BLE HRS spec
- Auto-reconnects on disconnect with exponential backoff

---

## S4 Serial Protocol

The S4 communicates as a USB CDC virtual serial port at 19,200 baud.

**Connection handshake:**
```
Host sends:  USB_HELLO  (0x55 0x53 0x42 0x44)
S4 responds: S4_HELLO   (0x5F 0x53 0x34 0x5F)
Host sends:  USB_CLEARMEM
```
A beep from the S4 monitor confirms successful connection.

**Data polling pattern:**
The reader polls key memory addresses at ~1Hz using `IRD` (Individual Read) commands. Key addresses:

| Address | Data |
|---|---|
| 0x0140 | Stroke rate |
| 0x0057 | Distance (meters, high byte) |
| 0x0058 | Distance (meters, low byte) |
| 0x0055 | Pace |
| 0x088 | Calories |
| 0x1A0 | Heart rate (onboard, not used — TICKR preferred) |

Full address map in `s4/protocol.py`, sourced from the official WaterRower S4/S5 USB Protocol specification.

---

## Configuration

All settings live in `config.toml` on the Pi (`/opt/buoycast/config.toml`).
[`config.toml.example`](../config.toml.example) is the annotated template and
`src/config.py` holds the defaults.

---

## Stability & Reliability

### S4 Connection
- USB serial connection monitored continuously
- On disconnect: close port cleanly, wait `reconnect_delay_s`, attempt reconnect
- Active workout is paused (not ended) on S4 disconnect — resumes automatically when S4 reconnects
- Dashboard shows clear S4 connection status at all times

### BLE FTMS Broadcast
- On client disconnect: immediately restart advertising
- Advertising continues regardless of workout state — Peloton can connect at any time
- FTMS broadcaster runs in isolated task — web server errors cannot affect it

### TICKR Connection
- Reconnects with exponential backoff (1s, 2s, 4s, max 30s)
- Missing HR data degrades gracefully — metrics continue without heart rate
- RR interval buffer cleared on reconnect to avoid stale data

### Workout Data Safety
- Stroke data written to SQLite in batches every 10 seconds
- On unexpected shutdown: incomplete workout detectable on next boot via `started_at` without `ended_at`
- Boot-time check: if incomplete workout found, surface recovery prompt in dashboard

### System Service

BuoyCast runs as the unprivileged `buoycast` user under systemd. See
[`deploy/buoycast.service`](../deploy/buoycast.service) for the unit and
[`deploy/install.sh`](../deploy/install.sh) for the install layout
(`/opt/buoycast/{config.toml,data,logs,releases/<version>,current}`).

---

## Dashboard — Frontend Architecture

**PWA manifest** enables add-to-home-screen on iPhone/iPad with full-screen mode.

**Layout breakpoints:**
- `< 768px` (iPhone portrait): single column, large metrics, bottom-pinned controls
- `>= 768px` (iPad landscape): two-column split, metrics left, sparkline right

**Component library: shadcn/ui**
Components are copied into the project (owned, not a dependency) and built on Radix UI accessibility primitives. Key components in use:

| shadcn Component | Used for |
|---|---|
| `Card` | Workout history list items, metric panels |
| `Badge` | Strava upload status indicators |
| `Dialog` | End workout confirmation, recovery prompt |
| `Sheet` | Mobile workout history slide-up |
| `Progress` | Pace/stroke rate gauge |
| `Button` | All workout controls |
| `Separator`, `Skeleton` | Layout polish, loading states |

**Data visualisation: Recharts (via shadcn charts)**
- Real-time stroke rate sparkline on iPad layout (last 60 seconds)
- Post-workout heart rate graph on completion screen
- Pace over time chart in workout history detail view

**Design tooling: Impeccable**
Installed via `npx skills add pbakaus/impeccable` into the project root. Used during frontend build phase with commands like `/polish`, `/audit`, `/bolder`, and `/distill` to ensure the UI quality exceeds generic AI output — important for a fitness app that needs to be readable mid-workout from a few feet away.

**Key hooks:**
- `useWorkoutSocket` — manages WebSocket lifecycle, reconnects on visibility change (handles iOS tab suspension)
- `useWakeLock` — acquires Screen Wake Lock API on workout start, releases on end/pause

**State management:** React `useReducer` for workout state machine — mirrors backend state, driven by WebSocket events. TypeScript types mirror Pydantic models exactly.

---

## Future Considerations

### Mini PC Analytics Export
- Built as a push instead: the HTTP export (see [export.md](export.md)) POSTs each finished workout, with its full sample series, to a configured endpoint and retries until delivered

### ANT+ Support
- Adding a USB ANT+ dongle enables Garmin watch connectivity
- Architecture supports this as an additional broadcaster task on the event bus

### HRV Analysis
- RR interval data already being captured
- Surface HRV metrics in workout history once analytics layer is built

### Workout Naming
- Allow custom workout name on completion screen before Strava upload
- Default to `"Morning Row — {date}"` style auto-name
