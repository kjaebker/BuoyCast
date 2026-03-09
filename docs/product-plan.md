# BuoyCast — Product Plan

## Overview

BuoyCast is a self-hosted, Raspberry Pi-based application that connects a WaterRower S4 monitor to modern fitness platforms and provides a live workout dashboard. It replaces the need for the official WaterRower COMmodule by reading data directly from the S4's USB serial port and re-broadcasting it over Bluetooth LE (FTMS), while also recording workouts locally and enabling manual upload to Strava.

---

## Goals

- Provide a rock-solid, always-on Bluetooth FTMS bridge between the WaterRower S4 and third-party apps (Peloton, WaterRower Connect)
- Capture rich workout data including heart rate from a Wahoo TICKR chest strap
- Display a responsive live dashboard accessible from iPhone and iPad
- Store workout history locally on the Pi
- Enable manual Strava upload with full rowing metrics via FIT file
- Lay groundwork for future data export to a local analytics machine

---

## Hardware

| Component | Detail |
|---|---|
| Single-board computer | Raspberry Pi Zero 2W |
| Storage | MicroSD card (16GB+) |
| Power | 5V / 1.8A+ micro USB supply |
| Rower connection | Mini USB to USB-A cable (6ft) |
| OTG adapter | Micro USB OTG host cable |
| Case | Pi Zero 2W compatible enclosure |
| Heart rate monitor | Wahoo TICKR (WFBTHR046) chest strap |

The Pi connects to the WaterRower S4 via the OTG data port using the mini USB cable. Power is supplied independently via the dedicated power micro USB port. The Pi runs headless — no monitor or keyboard required after initial setup.

---

## Integrations

### Peloton
- Protocol: Bluetooth LE FTMS Rower profile
- Data: Stroke rate, pace, distance, power
- Mode: Real-time, live during workout
- Notes: Pi advertises as an FTMS peripheral; Peloton connects as a central device

### WaterRower Connect App
- Protocol: Bluetooth LE FTMS
- Data: Full rowing metrics
- Mode: Real-time
- Notes: Same FTMS broadcast serves both Peloton and WaterRower app simultaneously where supported

### Strava
- Protocol: Strava API v3, FIT file upload
- Data: Distance, time, pace, stroke rate, stroke count, power, calories, heart rate time series
- Mode: Manual upload initiated from dashboard (completion screen or workout history)
- Auth: OAuth2 with refresh token, one-time browser setup
- Sport type: `Rowing` / `INDOOR_ROWING`

### Wahoo TICKR Heart Rate Strap
- Protocol: Bluetooth LE Heart Rate Service (HRS)
- Data: BPM, RR intervals
- Mode: Real-time, merged into unified metrics stream
- Notes: Optional — workouts proceed without HR if strap is unavailable

---

## Features

### Live Dashboard
- Responsive Progressive Web App (PWA) accessible at `waterrower.local`
- Optimised layouts for iPhone (portrait) and iPad (landscape)
- Screen wake lock to prevent display sleep during workouts
- WebSocket-driven live data — no polling
- Auto-reconnect on tab resume (handles iOS background suspension)

**Live metrics displayed:**
- Elapsed time
- Distance (meters)
- Pace (split per 500m)
- Stroke rate (SPM)
- Power (watts)
- Stroke count
- Calories
- Heart rate (BPM) — when TICKR connected
- Current workout state indicator

### Workout Controls
Manual controls are the source of truth for workout state. Smart detection is assistive.

| Control | Behaviour |
|---|---|
| Start Workout | Begins recording, starts timer |
| Pause | Freezes timer, maintains BLE broadcast |
| Resume | Resumes recording |
| End Workout | Stops recording, shows summary screen |

**Smart detection (assistive only):**
- Auto-pause after 30+ seconds of no strokes during active workout
- Auto-resume when rowing detected while paused
- Prompt to start if rowing detected while idle
- Prompt to end if idle for 5+ minutes while active or paused

### Completion Screen
Shown immediately after ending a workout:
- Full workout summary (time, distance, avg pace, avg stroke rate, avg power, avg HR, calories, total strokes)
- "Upload to Strava" button
- "Maybe Later" option (workout saved as PENDING)

### Workout History
- List of all completed workouts
- Per-workout Strava upload status badge: PENDING / UPLOADING / UPLOADED / FAILED / SKIPPED
- Upload button on PENDING workouts
- Retry button on FAILED workouts with error detail
- Deep link to Strava activity on UPLOADED workouts (`strava://activities/{id}`)

### Heart Rate
- TICKR connection status shown in dashboard at all times
- HR displayed as prominent live metric when connected
- HR time series stored in workout record and included in Strava FIT upload
- RR interval data captured locally for future HRV analysis
- TICKR identified by MAC address in config (fast reconnection, no scan required)

### Future: Analytics Export
- At workout completion, optionally POST workout JSON payload to a configured endpoint
- Intended for local analytics machine running DuckDB
- Pull-based design — analytics machine polls Pi's REST API for new workouts
- Graceful when analytics machine is offline

---

## Workout State Machine

```
IDLE
  │
  ├─ [Start button / rowing detected prompt accepted]
  │
ACTIVE
  │
  ├─ [Pause button / no strokes for 30s] ──► PAUSED
  │                                              │
  │◄──────────────────────────────────────────── ┘
  │  [Resume button / rowing detected]
  │
  ├─ [End button / idle 5min prompt accepted]
  │
SUMMARY
  │
  ├─ [Upload to Strava / Maybe Later]
  │
IDLE
```

---

## Strava Upload Status Model

Each completed workout carries one of the following upload states:

| State | Meaning |
|---|---|
| `PENDING` | Workout complete, not yet uploaded |
| `UPLOADING` | Upload in progress |
| `UPLOADED` | Successfully uploaded, Strava activity ID stored |
| `FAILED` | Upload failed, retry available |
| `SKIPPED` | User dismissed, will not auto-upload |

---

## Setup & Operation

### Initial Setup
1. Flash Raspberry Pi OS Lite to microSD using Raspberry Pi Imager
2. Pre-configure WiFi credentials and enable SSH in Imager advanced settings
3. Insert card, boot Pi, SSH in
4. Clone repo and run install script
5. Connect Strava via browser OAuth flow (one-time)
6. Note TICKR MAC address in config file
7. Connect USB cable from Pi OTG port to WaterRower S4 monitor
8. Service starts automatically on boot via systemd

### Daily Use
1. Pi is always on — no action required
2. Put on TICKR strap — Pi connects automatically
3. Open `waterrower.local` on iPhone or iPad
4. Tap Start Workout
5. Row
6. Tap End Workout
7. Review summary, upload to Strava if desired

---

## Non-Goals (v1)

- No Apple Watch heart rate support (Apple Watch does not broadcast HRS as a peripheral)
- No ANT+ support (BLE only in v1)
- No automatic Strava upload (manual by design)
- No cloud hosting — fully local / self-hosted
- No multi-user support
- No GPS / virtual course mapping on Strava
