# BuoyCast

A self-hosted Raspberry Pi bridge for the WaterRower S4. Reads the rower's USB serial data, broadcasts it over Bluetooth LE (FTMS) to a Peloton, captures heart rate from a Wahoo TICKR, serves a live PWA dashboard, and uploads workouts to Strava.

---

## What it does

```
WaterRower S4  ──USB──►  Pi Zero 2W  ──BLE FTMS──►  Peloton
                              │
                        ◄─ BLE HRS ─  Wahoo TICKR
                              │
                         SQLite DB
                         FIT files
                              │
                         REST / WS ──►  Dashboard (PWA)
                              │
                         Strava API ──►  Strava
```

| Feature | Detail |
|---|---|
| S4 serial reader | USB CDC at 19200 baud, ~1 Hz poll, auto-reconnect |
| FTMS broadcast | BLE peripheral advertising Rower Data (0x2AD1) to Peloton / WaterRower app |
| Heart rate | Wahoo TICKR via BLE HRS; BPM + RR intervals merged into the metrics stream |
| Dashboard | React PWA at `http://waterrower.local:8080`; optimised for iPhone + iPad |
| WebSocket | Live metrics pushed over `/ws/live`; no polling |
| Workout recording | Stroke-level data flushed to SQLite every 10 s; survives unexpected shutdown |
| FIT export | `Sport.ROWING / SubSport.INDOOR_ROWING` with full HR time series |
| Strava upload | Manual OAuth2 flow (one-time); FIT upload via Strava API v3 |
| Smart detection | Auto-pause after 30 s idle; auto-resume on stroke; prompts to start/end |
| Wake lock | Screen stays on during active workout (iOS 16.4+ / Android Chrome) |

---

## Hardware

| Item | Notes |
|---|---|
| Raspberry Pi Zero 2W | Single BT chip; supports central + peripheral simultaneously |
| microSD ≥ 16 GB (A1) | Samsung Endurance or SanDisk Max Endurance recommended |
| USB OTG cable (micro-USB → USB-A) | Connects to the S4; use the OTG port, not the power port |
| 5 V / 2.5 A USB-C supply | Via the dedicated PWR micro-USB port |
| Wahoo TICKR | Optional — workouts proceed without HR |
| Peloton | Optional — FTMS BLE client |

---

## Quick start

Full step-by-step instructions are in [`docs/pi-setup.md`](docs/pi-setup.md).

```bash
# 1. Flash Raspberry Pi OS Lite (64-bit) with Raspberry Pi Imager
#    Set hostname: waterrower  |  Enable SSH  |  Configure Wi-Fi

# 2. SSH in after first boot
ssh pi@waterrower.local

# 3. Clone and install
git clone https://github.com/your-org/BuoyCast.git
cd BuoyCast
sudo bash install.sh

# 4. Edit config (TICKR MAC + Strava credentials)
nano /opt/buoycast/config.toml

# 5. Strava OAuth — one-time from a browser
# http://waterrower.local:8080/api/strava/auth

# 6. Verify
curl http://waterrower.local:8080/api/status
```

---

## Daily use

1. Pi is always on — no action needed
2. Put on TICKR strap — Pi connects automatically
3. Open `http://waterrower.local:8080` on your iPhone or iPad
4. Tap **Start Workout**
5. Row
6. Tap **End Workout** → review summary → optionally upload to Strava

---

## Workout state machine

```
IDLE
 │  [Start / rowing detected]
ACTIVE
 │  [Pause / 30 s no strokes]     PAUSED
 │        ◄──────────────────────────┘
 │         [Resume / stroke detected]
 │  [End / 5 min idle]
SUMMARY
 │  [Upload / Skip]
IDLE
```

---

## Configuration

`/opt/buoycast/config.toml` — template at [`config.toml.example`](config.toml.example):

```toml
[server]
host = "0.0.0.0"
port = 8080
mdns_name = "waterrower"       # → http://waterrower.local:8080

[s4]
port = "/dev/ttyACM0"
baud_rate = 19200

[heart_rate]
device_mac = "A4:34:F1:XX:XX:XX"   # your TICKR's MAC address

[strava]
client_id     = ""
client_secret = ""

[workout]
auto_pause_idle_s = 30
auto_end_idle_s   = 300
```

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | S4 + TICKR connection state, workout state, uptime |
| `GET` | `/api/workouts` | Paginated workout history |
| `GET` | `/api/workouts/{id}` | Single workout |
| `GET` | `/api/workouts/{id}/strokes` | Stroke-level time series |
| `DELETE` | `/api/workouts/{id}` | Delete workout + strokes |
| `POST` | `/api/workout/start` | Start a workout |
| `POST` | `/api/workout/pause` | Pause |
| `POST` | `/api/workout/resume` | Resume |
| `POST` | `/api/workout/end` | End |
| `POST` | `/api/workouts/{id}/upload` | Queue Strava upload (202 Accepted) |
| `POST` | `/api/workouts/{id}/skip` | Mark SKIPPED |
| `GET` | `/api/strava/auth` | Begin OAuth flow |
| `GET` | `/api/strava/callback` | OAuth callback |
| `GET` | `/api/strava/status` | Connected athlete info |
| `DELETE` | `/api/strava/auth` | Revoke token |
| `WS` | `/ws/live` | Live metrics + state events |

---

## Source layout

```
src/
├── main.py           # Entry point — wires all async tasks
├── config.py         # pydantic-settings Settings
├── models.py         # RowingMetrics, WorkoutRecord, StrokeRecord (Pydantic v2)
├── events.py         # EventBus + EventType enum
├── merger.py         # Merges S4 + TICKR → MERGED_METRICS
├── s4/
│   ├── protocol.py   # Memory addresses, command constants, byte parsers
│   └── reader.py     # Async serial reader, ~1 Hz poll loop
├── ble/
│   ├── ftms.py       # FTMS Rower peripheral (Pi → Peloton)
│   └── tickr.py      # HRS central reader (TICKR → Pi)
├── workout/
│   ├── state.py      # WorkoutStateMachine
│   ├── recorder.py   # Stroke buffer, 10 s SQLite flush
│   └── fit.py        # FIT file generation
├── web/
│   ├── server.py     # FastAPI app, WebSocket, lifespan
│   └── routes/       # workouts.py, strava.py
├── strava/
│   ├── auth.py       # OAuth2, token storage + refresh
│   └── upload.py     # FIT upload, status polling
└── storage/
    ├── db.py         # aiosqlite wrapper, migrations
    └── queries.py    # All SQL queries

dashboard/            # React PWA (Vite + TypeScript + Tailwind + shadcn/ui)
tests/
├── unit/             # Protocol parsers, FTMS packing, models, state machine
├── integration/      # API, storage, Strava (mock transport), S4/TICKR readers
└── e2e/              # Full workout flow
```

---

## Development

```bash
# Python (requires Python 3.11+)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Dashboard
cd dashboard
npm install
npm run dev                        # dev server on :5173
npm run build                      # production build → dashboard/dist/
npx tsc --noEmit                   # type-check only
```

Hardware is never required for development — `MockSerial` and `MockBLEClient` fixtures in `tests/conftest.py` simulate the S4 and TICKR.

---

## Docs

| Document | Contents |
|---|---|
| [`docs/product-plan.md`](docs/product-plan.md) | Goals, integrations, feature spec, non-goals |
| [`docs/architecture-plan.md`](docs/architecture-plan.md) | Tech stack, data models, event bus, API spec, BLE, S4 protocol, DB schema |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | Phase-by-phase task breakdown with exit criteria |
| [`docs/pi-setup.md`](docs/pi-setup.md) | Headless Pi OS flash, SSH, install, Strava OAuth, TICKR MAC |
| [`docs/hardware-checklist.md`](docs/hardware-checklist.md) | Step-by-step hardware verification (S4, TICKR, FTMS, Peloton) |
| [`TASKS.md`](TASKS.md) | Work tracker — task status by phase |

---

## Constraints

Runs on Raspberry Pi Zero 2W: CPU < 50% average, RAM < 200 MB during an active workout. Four top-level coroutines (`s4_reader`, `tickr_reader`, `ftms_broadcaster`, `web_server`) are isolated — a crash in the web server does not affect the BLE broadcast.
