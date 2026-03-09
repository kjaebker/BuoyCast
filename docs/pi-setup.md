# BuoyCast — Headless Raspberry Pi Setup

Step-by-step guide to flash, configure, and run BuoyCast on a Raspberry Pi Zero 2W with no monitor or keyboard.

---

## Hardware required

| Item | Notes |
|---|---|
| Raspberry Pi Zero 2W | With headers if soldering is not preferred |
| microSD card (≥ 16 GB, A1 class or better) | Samsung Endurance or SanDisk Max Endurance recommended |
| USB OTG cable (micro-USB → USB-A) | For WaterRower S4 serial connection |
| USB-C power supply (5V / 2.5A) | Via the PWR port, not the OTG port |
| Wi-Fi network | 2.4 GHz only (Pi Zero 2W has no 5 GHz radio) |
| Wahoo TICKR (optional) | Heart rate strap |
| Peloton bike (optional) | FTMS BLE client |

---

## 1 — Flash the SD card with Raspberry Pi Imager

1. Download **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Click **Choose OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (64-bit)**.
   _(Lite = no desktop, smaller footprint, better for Pi Zero 2W.)_
3. Click **Choose Storage** and select your SD card.
4. Click the **gear icon** (⚙) or press `Ctrl+Shift+X` to open **Advanced options** and set:

   | Setting | Value |
   |---|---|
   | Set hostname | `waterrower` |
   | Enable SSH | ✅ — Use password authentication |
   | Username | `pi` |
   | Password | choose a strong password |
   | Configure Wi-Fi | ✅ — enter your SSID and password |
   | Wi-Fi country | your ISO country code (e.g. `GB`, `US`) |
   | Set locale | your timezone and keyboard layout |

5. Click **Write** and wait for flashing + verification to complete.
6. Eject the card and insert it into the Pi.

---

## 2 — First boot and SSH

1. Connect the power supply to the **PWR** micro-USB port (right port).
   _Do NOT use the OTG port for power — it is for the S4 cable._
2. Wait ~60 seconds for first boot to complete.
3. Find the Pi's IP address — check your router's DHCP leases, or use mDNS:

   ```bash
   ping waterrower.local
   ```

4. SSH in:

   ```bash
   ssh pi@waterrower.local
   # or: ssh pi@<IP address>
   ```

5. Accept the host key fingerprint and enter the password you set in Imager.
6. Update the OS before proceeding:

   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```

---

## 3 — Clone the repo and run the install script

```bash
# Clone BuoyCast
git clone https://github.com/your-org/BuoyCast.git
cd BuoyCast

# Run the install script as root
sudo bash install.sh
```

The script will:
- Install system packages (Python 3, Bluetooth, Avahi, Node.js 20, git)
- Set up a Python virtualenv in `/opt/buoycast/.venv`
- Build the React dashboard
- Copy `config.toml.example` → `/opt/buoycast/config.toml`
- Install and enable the `waterrower` systemd service
- Add `pi` to the `bluetooth` and `dialout` groups

---

## 4 — Edit config.toml

```bash
nano /opt/buoycast/config.toml
```

Minimum required fields:

```toml
[heart_rate]
device_mac = "A4:34:F1:XX:XX:XX"   # your TICKR MAC — see step 5 below

[strava]
client_id     = "12345"             # from your Strava API app
client_secret = "abc123..."
```

All other defaults are fine for a standard WaterRower S4 + Pi Zero 2W setup.
Save with `Ctrl+O`, exit with `Ctrl+X`.

---

## 5 — Find your TICKR MAC address

If you don't already know the MAC address of your Wahoo TICKR:

```bash
# Start an interactive BLE scan (wear the strap and breathe)
sudo bluetoothctl
[bluetooth]# scan on
```

Look for a line like:

```
[NEW] Device A4:34:F1:XX:XX:XX TICKR XXXX
```

Copy the MAC (`A4:34:F1:XX:XX:XX`), then:

```
[bluetooth]# scan off
[bluetooth]# exit
```

Paste it into `config.toml` under `[heart_rate] device_mac`.

---

## 6 — Strava OAuth (one-time, from a browser)

Strava requires an OAuth authorisation that must be done once from a browser.

### 6a — Create a Strava API app

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an app.
2. Set **Authorization Callback Domain** to `waterrower.local`.
3. Copy **Client ID** and **Client Secret** into `config.toml`.

### 6b — Start the service temporarily

```bash
sudo systemctl start waterrower
```

### 6c — Authorise from your phone or laptop browser

Open:

```
http://waterrower.local:8080/api/strava/auth
```

You will be redirected to Strava's consent page. Log in and click **Authorize**.
The Pi will receive the token and store it in `data/buoycast.db`.

### 6d — Verify the token was saved

```bash
curl -s http://waterrower.local:8080/api/strava/status | python3 -m json.tool
```

Expected response:

```json
{
  "connected": true,
  "athlete_name": "Your Name"
}
```

---

## 7 — Reboot and verify

```bash
sudo reboot
```

After ~60 seconds:

```bash
# Check service is running
sudo systemctl status waterrower

# Tail live logs
journalctl -u waterrower -f

# Check system status via API
curl -s http://waterrower.local:8080/api/status | python3 -m json.tool
```

Expected `/api/status` response when S4 is not yet connected:

```json
{
  "s4_connected": false,
  "tickr_connected": false,
  "workout_state": "IDLE",
  "uptime_seconds": 42,
  "last_metrics_ts": null
}
```

---

## 8 — Connect the WaterRower S4

1. Plug the USB OTG cable into the Pi's **OTG** micro-USB port (left port, closest to the board edge).
2. Plug the other end into the WaterRower S4 USB port on the back of the monitor.
3. Power on the S4 (or wake it if already on).
4. The Pi should detect `/dev/ttyACM0` automatically. Check:

   ```bash
   ls /dev/ttyACM*
   journalctl -u waterrower -f
   ```

   Look for `S4 connected` in the logs.

5. Re-check `/api/status`:

   ```bash
   curl -s http://waterrower.local:8080/api/status | python3 -m json.tool
   ```

   `s4_connected` should now be `true`.

---

## 9 — Open the dashboard

From your phone or laptop on the same Wi-Fi:

```
http://waterrower.local:8080
```

For best experience on iPhone/iPad:

1. Tap the **Share** icon → **Add to Home Screen**
2. Launch from the home screen icon (runs as a PWA, full-screen)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ping waterrower.local` fails | Check hostname in Imager settings; try IP address from router; ensure avahi-daemon is running: `sudo systemctl status avahi-daemon` |
| `ssh: connection refused` | SSH not enabled in Imager — re-flash with SSH enabled |
| S4 not detected (`/dev/ttyACM0` missing) | Try the other micro-USB port; check `dmesg \| grep tty` for CDC device |
| TICKR not connecting | Verify MAC in config.toml; ensure `pi` is in `bluetooth` group: `groups pi`; restart bluetooth: `sudo systemctl restart bluetooth` |
| `Permission denied` on serial port | Run `sudo usermod -aG dialout pi` then reboot |
| Service fails to start | Check full logs: `journalctl -u waterrower -n 50 --no-pager` |
| Strava auth page unreachable | Ensure service is running; check firewall (Pi OS Lite has no firewall by default) |
| Dashboard not loading | Try `http://<IP>:8080` instead of mDNS; check service logs |
