# BuoyCast — Hardware Verification Checklist

Run through this checklist after `install.sh` completes and the service is running.
Each section is independent — work through them in order.

Prerequisites:
- Pi is running BuoyCast (`sudo systemctl status buoycast` → `active (running)`)
- You are SSH'd in or watching logs: `journalctl -u buoycast -f`
- API is reachable: `curl -s http://buoycast.local:8080/api/status`

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
journalctl -u buoycast -f
```

**Expected log line:**
```
INFO  src.s4.reader  S4 connected on /dev/ttyACM0
```

### 1.4 API status — s4_connected true

```bash
curl -s http://buoycast.local:8080/api/status | python3 -m json.tool
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
curl -s http://buoycast.local:8080/api/status | python3 -m json.tool
```

**Expected:** `last_metrics_ts` is a recent ISO timestamp (within the last few seconds)

### 1.6 S4 disconnect and auto-reconnect

- [ ] Unplug the USB OTG cable from the S4
- **Expected log:** `S4 disconnected — will retry`; `s4_connected: false` in `/api/status`
- [ ] Plug the cable back in
- **Expected log:** `S4 connected on /dev/ttyACM0`; `s4_connected: true` in `/api/status`
- [ ] Service must still be running (`systemctl status buoycast` → no crash)

---

## 2 — Wahoo TICKR Heart Rate

### 2.1 Physical setup

- [ ] TICKR strap moistened and worn
- [ ] TICKR device_mac set in `/opt/buoycast/config.toml` (see `docs/pi-setup.md` § 5)

### 2.2 Service log — TICKR connected

```bash
journalctl -u buoycast -f
```

**Expected log line (within ~30 seconds of service start):**
```
INFO  src.ble.tickr  TICKR connected: A4:34:F1:XX:XX:XX
```

### 2.3 API status — tickr_connected true

```bash
curl -s http://buoycast.local:8080/api/status | python3 -m json.tool
```

**Expected:**
```json
{
  "tickr_connected": true,
  ...
}
```

### 2.4 HR in live metrics

Open the dashboard at `http://buoycast.local:8080` — the HR tile in the status bar should show a live BPM value (not `–`).

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

BuoyCast advertises over Bluetooth LE as an FTMS (Fitness Machine Service)
rower named **BuoyCast**. The Peloton **app** (iPad, iPhone or Android) can pair
with third-party FTMS rowers from inside a rowing class. This needs an App+ or
All-Access membership. Pairing is done in the app, not in the Bike or Tread
touchscreen's Bluetooth settings.

> **Status:** Peloton pairing has not been confirmed to work yet. With v0.3.0,
> BuoyCast did not appear in the Peloton iPad app's device list. Work through
> 3.2 → 3.4 in order and note where it stops working: that tells us whether the
> problem is the advertisement, the data, or Peloton's device filter.

### 3.1 FTMS data packing — unit test verification

On your development machine (not the Pi):

```bash
pytest tests/unit/test_ftms_packing.py -v
```

**Expected:** all tests pass

### 3.2 BLE advertising visible (nRF Connect)

First check that advertising started on the Pi:

```bash
journalctl -u buoycast | grep -i ftms
```

**Expected:** `FTMS advertising as 'BuoyCast' — service UUID 00001826-…`. A
`FTMS BLE setup failed after 4 attempts` line means the adapter refused the
registration. Run `bluetoothctl show` and check `Powered: yes`.

Install **nRF Connect for Mobile** on the **same iPad** you'll use for Peloton,
so both apps see the same radio.

- [ ] Open nRF Connect → **Scanner** tab → **Scan**
- [ ] A device named **BuoyCast** appears
- [ ] Tap the row (not **Connect**) to expand the advertisement details:
  - [ ] **Complete Local Name:** `BuoyCast`
  - [ ] **Service UUIDs** include **Fitness Machine** (`0x1826`)
  - [ ] **Service Data:** write down whether there is an entry for `0x1826`
    and its bytes. The FTMS spec has a rower advertise `01 10 00` there
    ("available", machine type = rower). BuoyCast doesn't send this yet,
    and its absence is the main suspect for Peloton not listing BuoyCast.

> If BuoyCast doesn't appear at all, restart the service
> (`sudo systemctl restart buoycast`), wait ~10 s, and scan again.

### 3.3 Rower Data characteristic — nRF Connect

- [ ] Tap **BuoyCast** in the scanner → **Connect**
- [ ] Browse to **Fitness Machine Service** (0x1826)
- [ ] Read **Fitness Machine Feature** (0x2ACC): it should return 8 bytes
- [ ] Tap **Rower Data** characteristic (0x2AD1)
- [ ] Tap the subscribe (notify) icon ▶
- [ ] Take a few strokes on the rower

**Expected:** The raw hex value updates approximately once per second.
Decode the first two bytes as a little-endian uint16 — these are the FTMS flags indicating which fields are present (stroke rate, distance, pace, power, HR).

- [ ] **Disconnect** in nRF Connect, then force-quit it. Peloton needs to be
  the only app connected to BuoyCast.

### 3.4 Peloton pairing

Before you start: BuoyCast is running, the S4 is connected, the iPad's
Bluetooth is on, and the iPad is within a few metres of the Pi.

- [ ] Open the **Peloton app** on the iPad → **Rowing** → pick any class
- [ ] On the class screen, choose **Connect a Bluetooth Device**
  _(the wording can vary slightly between app versions; it's the
  Bluetooth / device option shown for rowing classes)_
- [ ] **BuoyCast** appears in the list → select it
- [ ] Start the class and row: **stroke rate** and **pace** from the S4 show on screen
- [ ] After the class, the workout summary shows the rowing data

**If BuoyCast doesn't appear in Peloton's list:**

- [ ] Confirm it still shows in nRF Connect's scanner on the same iPad
  (3.2). If nRF Connect sees it but Peloton doesn't, Peloton is filtering it
  out. Note the **Service Data** result from 3.2, since that's the likely
  reason.
- [ ] Turn the iPad's Bluetooth off and on, and force-quit the Peloton app
  (iOS caches Bluetooth scan results).
- [ ] Make sure nothing else is connected to BuoyCast (nRF Connect, the
  WaterRower app).
- [ ] Rule out the shared radio: the Pi Zero 2W has one Bluetooth chip that
  also reads the TICKR. Set `[heart_rate] enabled = false` in
  `/opt/buoycast/config.toml`, run `sudo systemctl restart buoycast`, and try
  again.
- [ ] Check that the Peloton membership is App+ or All-Access. Third-party
  rower pairing isn't offered on the free or App One tiers.

---

## 4 — Full workout flow

### 4.1 Start a workout via dashboard

- [ ] Open `http://buoycast.local:8080` on your phone
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
curl -s http://buoycast.local:8080/api/workouts | python3 -m json.tool
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
curl -X POST http://buoycast.local:8080/api/workouts/$WORKOUT_ID/upload
# → 202 Accepted

# Poll for result
curl -s http://buoycast.local:8080/api/workouts/$WORKOUT_ID | python3 -m json.tool
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
systemctl show buoycast --property=MemoryMax
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
| FTMS advertising | BuoyCast visible in nRF Connect with service `0x1826`; Service Data result noted |
| Peloton pairing | BuoyCast listed in a Peloton app rowing class; stroke rate + pace shown |
| Full workout | Start → row → pause → resume → end → summary |
| Data persistence | Workout in `/api/workouts` with correct stats |
| FIT file | `.fit` file present in `data/fit/` |
| Strava upload | Activity appears in Strava |
| Resource usage | CPU < 50%, RAM < 200 MB |
