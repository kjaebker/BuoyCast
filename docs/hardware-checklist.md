# BuoyCast — Hardware Verification Checklist

Run through this checklist after `install.sh` completes and the service is running.
Each section is independent — work through them in order.

Prerequisites:
- Pi is running BuoyCast (`sudo systemctl status waterrower` → `active (running)`)
- You are SSH'd in or watching logs: `journalctl -u waterrower -f`
- API is reachable: `curl -s http://waterrower.local:8080/api/status`

---

## 1 — WaterRower S4 via USB OTG

### 1.1 Physical connection

- [ ] Power supply connected to the **right** (PWR) micro-USB port on the Pi Zero 2W
- [ ] USB OTG cable connected to the **left** (OTG) micro-USB port — this is the data port
- [ ] Other end of OTG cable connected to the S4 USB port (back of the monitor)
- [ ] WaterRower monitor powered on (or press any button to wake it)

**Expected:** Within ~5 seconds the S4 monitor emits a short beep, confirming USB handshake.

### 1.2 Kernel device detection

```bash
ls /dev/ttyACM*
```

**Expected:** `/dev/ttyACM0` (or `/dev/ttyACM1` if another CDC device is present)

If missing:

```bash
dmesg | grep -E "tty|cdc|ACM" | tail -20
```

Look for lines like:
```
usb 1-1: new full-speed USB device
cdc_acm 1-1:1.0: ttyACM0: USB ACM device
```

### 1.3 Service log — S4 connected

```bash
journalctl -u waterrower -f
```

**Expected log line:**
```
INFO  src.s4.reader  S4 connected on /dev/ttyACM0
```

### 1.4 API status — s4_connected true

```bash
curl -s http://waterrower.local:8080/api/status | python3 -m json.tool
```

**Expected:**
```json
{
  "s4_connected": true,
  ...
}
```

### 1.5 Live metrics flowing

Sit on the rower and take a few strokes, then:

```bash
curl -s http://waterrower.local:8080/api/status | python3 -m json.tool
```

**Expected:** `last_metrics_ts` is a recent ISO timestamp (within the last few seconds)

### 1.6 S4 disconnect and auto-reconnect

- [ ] Unplug the USB OTG cable from the S4
- **Expected log:** `S4 disconnected — will retry`; `s4_connected: false` in `/api/status`
- [ ] Plug the cable back in
- **Expected log:** `S4 connected on /dev/ttyACM0`; `s4_connected: true` in `/api/status`
- [ ] Service must still be running (`systemctl status waterrower` → no crash)

---

## 2 — Wahoo TICKR Heart Rate

### 2.1 Physical setup

- [ ] TICKR strap moistened and worn
- [ ] TICKR device_mac set in `/opt/buoycast/config.toml` (see `docs/pi-setup.md` § 5)

### 2.2 Service log — TICKR connected

```bash
journalctl -u waterrower -f
```

**Expected log line (within ~30 seconds of service start):**
```
INFO  src.ble.tickr  TICKR connected: A4:34:F1:XX:XX:XX
```

### 2.3 API status — tickr_connected true

```bash
curl -s http://waterrower.local:8080/api/status | python3 -m json.tool
```

**Expected:**
```json
{
  "tickr_connected": true,
  ...
}
```

### 2.4 HR in live metrics

Open the dashboard at `http://waterrower.local:8080` — the HR tile in the status bar should show a live BPM value (not `–`).

### 2.5 TICKR staleness handling

- [ ] Remove the TICKR strap (simulate signal loss)
- **Expected:** after ~3 seconds, HR tile in dashboard shows `–`
- [ ] Put the strap back on
- **Expected:** HR resumes within one poll cycle

### 2.6 TICKR disconnect and auto-reconnect

- [ ] Turn off the TICKR (hold button until LED flashes)
- **Expected log:** `TICKR disconnected — retrying...`; `tickr_connected: false` in `/api/status`
- [ ] Turn TICKR back on
- **Expected log:** `TICKR connected: A4:34:F1:XX:XX:XX` (may take up to 30 seconds)
- [ ] Service must still be running — no crash

---

## 3 — FTMS BLE broadcast to Peloton

> **Note:** The BlueZ D-Bus GATT server is implemented as a placeholder in this release.
> The byte-packing logic is complete and tested. Full advertising requires BlueZ registration
> (see `src/ble/ftms.py` `_setup_ble`). Until that is completed, use **nRF Connect** to verify
> the data stream is being packed correctly, and perform Peloton pairing manually once the
> BlueZ implementation is finalised.

### 3.1 FTMS data packing — unit test verification

On your development machine (not the Pi):

```bash
.venv/Scripts/python.exe -m pytest tests/unit/test_ftms_packing.py -v
```

**Expected:** all tests pass

### 3.2 BLE advertising visible (nRF Connect)

Install **nRF Connect for Mobile** (iOS or Android) on your phone.

- [ ] Open nRF Connect → **Scanner** tab
- [ ] Tap **Scan**
- Look for a device named **BuoyCast**
- [ ] It should appear with **Fitness Machine** (UUID `0x1826`) in its advertised services

> If BuoyCast is not visible, the BlueZ registration needs to be completed first.
> Check logs: `journalctl -u waterrower | grep -i btms`

### 3.3 Rower Data characteristic — nRF Connect

- [ ] Tap **BuoyCast** in the scanner → **Connect**
- [ ] Browse to **Fitness Machine Service** (0x1826)
- [ ] Tap **Rower Data** characteristic (0x2AD1)
- [ ] Tap the subscribe (notify) icon ▶
- [ ] Take a few strokes on the rower

**Expected:** The raw hex value updates approximately once per second.
Decode the first two bytes as a little-endian uint16 — these are the FTMS flags indicating which fields are present (stroke rate, distance, pace, power, HR).

### 3.4 Peloton pairing

- [ ] On the Peloton touchscreen: **More** → **Bluetooth** → **Heart Rate Monitor**
  _(Peloton uses FTMS for row data, but surfaces it via the heart rate source selection for some models)_
- [ ] Alternatively: **More** → **Settings** → **Fitness Equipment** → scan for BLE rowers
- [ ] Select **BuoyCast** from the list
- [ ] The Peloton should display stroke rate, pace, and distance from the S4 during rowing

> Peloton's exact menu path varies by software version. If the device does not appear,
> ensure the Pi's Bluetooth is not connected to the TICKR on the same adapter — the Pi Zero 2W
> has a single BT chip and supports simultaneous central + peripheral roles, but driver
> stability may vary.

---

## 4 — Full workout flow

### 4.1 Start a workout via dashboard

- [ ] Open `http://waterrower.local:8080` on your phone
- [ ] Tap **Start Workout**
- [ ] `/api/status` → `workout_state: "ACTIVE"`

### 4.2 Row for 2 minutes

- [ ] Metrics (stroke rate, pace, distance, HR) update in the dashboard in real time
- [ ] Sparkline chart (tablet) updates continuously

### 4.3 Pause and resume

- [ ] Tap **Pause** — `workout_state: "PAUSED"` in API; dashboard shows paused state
- [ ] Stop rowing for > 3 seconds — auto-pause should trigger if not already paused
- [ ] Tap **Resume** — `workout_state: "ACTIVE"`

### 4.4 End and completion screen

- [ ] Tap **End Workout** → confirm in the dialog
- [ ] Dashboard transitions to completion screen with summary stats
- [ ] `/api/status` → `workout_state: "SUMMARY"`

### 4.5 Data persisted to SQLite

```bash
curl -s http://waterrower.local:8080/api/workouts | python3 -m json.tool
```

**Expected:** the just-completed workout appears with `ended_at` set, `total_distance_m > 0`, and `total_strokes > 0`

### 4.6 FIT file generated

```bash
ls -lh /opt/buoycast/data/fit/
```

**Expected:** a `.fit` file named with the workout ID and a non-zero size

---

## 5 — Strava upload

(Requires Strava OAuth completed — see `docs/pi-setup.md` § 6)

- [ ] From the completion screen, tap **Upload to Strava**
- [ ] Status indicator cycles through `UPLOADING` → `UPLOADED`
- [ ] Tap the Strava deep link to confirm the activity appears in Strava

Alternatively, upload a past workout from the history sheet:

```bash
WORKOUT_ID="<id from /api/workouts>"
curl -X POST http://waterrower.local:8080/api/workouts/$WORKOUT_ID/upload
# → 202 Accepted

# Poll for result
curl -s http://waterrower.local:8080/api/workouts/$WORKOUT_ID | python3 -m json.tool
# strava_upload_status should become "UPLOADED"
```

---

## 6 — Resource usage on Pi Zero 2W

Run a 10-minute active workout then check:

```bash
# CPU and memory snapshot
top -bn1 | grep python

# Or with more detail (install if missing: sudo apt install sysstat)
pidstat -u -r -p $(pgrep -f "src.main") 5 3
```

**Targets:**
- CPU average: < 50%
- RSS memory: < 200 MB

```bash
# Memory cap from systemd (should not be hit)
systemctl show waterrower --property=MemoryMax
# → MemoryMax=209715200  (200 MiB)
```

If resource usage is too high, see task 11.2 (performance profiling).

---

## Pass criteria summary

| Check | Pass condition |
|---|---|
| S4 USB OTG | Beep on connect; `s4_connected: true` in API; metrics flowing |
| S4 reconnect | Disconnect + reconnect without service crash |
| TICKR HR | `tickr_connected: true`; HR visible in dashboard |
| TICKR staleness | HR → `–` within 3 s of signal loss |
| TICKR reconnect | Auto-reconnects without service crash |
| FTMS packing | Unit tests pass |
| FTMS advertising | BuoyCast visible in nRF Connect (once BlueZ impl complete) |
| Peloton pairing | Rower data visible on Peloton (once BlueZ impl complete) |
| Full workout | Start → row → pause → resume → end → summary |
| Data persistence | Workout in `/api/workouts` with correct stats |
| FIT file | `.fit` file present in `data/fit/` |
| Strava upload | Activity appears in Strava |
| Resource usage | CPU < 50%, RAM < 200 MB |
