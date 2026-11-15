# Setting up BuoyCast

This guide takes a blank Raspberry Pi to a working BuoyCast in about 30
minutes, most of it waiting for downloads. You don't need a monitor or
keyboard for the Pi.

## What you need

| Item | Notes |
|---|---|
| Raspberry Pi Zero 2W | Any 64-bit Pi with Bluetooth works. The Zero 2W is what BuoyCast is tuned for. |
| microSD card, 16 GB or more | An "endurance" card (Samsung PRO Endurance, SanDisk MAX Endurance) lasts longer when always on |
| Micro-USB OTG cable (micro-USB → USB-A) | Connects the Pi to the WaterRower S4 monitor |
| 5 V / 2.5 A micro-USB power supply | Goes in the Pi's **PWR** port |
| 2.4 GHz Wi-Fi | The Zero 2W has no 5 GHz radio |
| WaterRower with the S4 monitor | |
| Bluetooth heart-rate strap (optional) | Tested with the Wahoo TICKR. Other standard heart-rate straps should work. |

## 1. Flash the SD card

1. Install **Raspberry Pi Imager** from
   [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Choose your Pi model, then **Raspberry Pi OS (other) → Raspberry Pi OS
   Lite (64-bit)**, then your SD card.
3. When Imager asks about **OS customisation**, choose **Edit settings**:
   - **Hostname:** `buoycast` (the dashboard will be at
     `http://buoycast.local:8080`)
   - **Username and password:** your choice
   - **Wireless LAN:** your Wi-Fi name, password and country
   - **Services → Enable SSH:** on
4. Write the card, put it in the Pi, and plug power into the **PWR** port
   (the one at the end of the board).

## 2. Connect to the Pi

Wait about a minute for the first boot, then from your computer:

```bash
ssh <your-username>@buoycast.local
```

If `buoycast.local` isn't found, look up the Pi's IP address in your
router's device list and use that instead.

## 3. Install BuoyCast

On the Pi:

```bash
curl -fsSL https://github.com/kjaebker/BuoyCast/releases/latest/download/install.sh | sudo bash
```

The installer:

- installs the system packages it needs (BlueZ, Avahi, polkit)
- creates a `buoycast` system user to run the service
- downloads the latest release into `/opt/buoycast` with its own Python
  environment. Nothing is compiled on the Pi.
- creates `/opt/buoycast/config.toml` from the template
- starts BuoyCast as a systemd service, and starts it on every boot

When it finishes it prints the dashboard address. Running it again is safe:
it keeps your config and workouts.

To install a specific version, run
`curl -fsSL https://github.com/kjaebker/BuoyCast/releases/latest/download/install.sh | sudo bash -s -- --version v0.3.0`.

## 4. Connect the rower

1. Plug the OTG cable into the Pi's **USB** port, the one in the middle of the
   board, not PWR.
2. Plug the other end into the USB port on the back of the S4 monitor.
3. Wake the monitor by pressing a button or taking a stroke.

Within a few seconds the dashboard's top bar shows **S4 live**. To
check from the Pi, run `journalctl -u buoycast -f` and look for `S4 connected`.

## 5. Open the dashboard

On your phone or tablet, on the same Wi-Fi, open
**http://buoycast.local:8080**.

On an iPhone or iPad, tap **Share → Add to Home Screen**. BuoyCast then opens
full screen, like an app, and keeps the screen awake during workouts.

Start rowing: BuoyCast notices and offers to start a workout. Or tap
**Start Workout**.

## Optional extras

All settings are in `/opt/buoycast/config.toml`. Edit it with
`sudo nano /opt/buoycast/config.toml`, then apply changes with
`sudo systemctl restart buoycast`. The template,
[`config.toml.example`](../config.toml.example), explains every setting.

### Heart-rate strap

Put the strap on (most only switch on when they touch skin), then on the Pi:

```bash
sudo systemctl stop buoycast          # frees the Bluetooth adapter for scanning
bluetoothctl --timeout 20 scan on     # look for your strap's name, e.g. "TICKR 1A2B"
```

Copy the address (like `A4:34:F1:12:34:56`) into the config:

```toml
[heart_rate]
enabled = true
device_mac = "A4:34:F1:12:34:56"
```

Then `sudo systemctl start buoycast`. Once the strap connects, the top bar shows your
heart rate instead of **HR waiting**. Workouts still record without a strap.

### Send workouts to your own server

BuoyCast can POST each finished workout to any HTTP endpoint you run, such as
a self-hosted training log or an automation tool. See [export.md](export.md).

### Strava

Strava uploads need your own Strava API application. Strava may require a
paid subscription for API access.

1. Create an application at
   [strava.com/settings/api](https://www.strava.com/settings/api). Set
   **Authorization Callback Domain** to `buoycast.local`. If you chose
   another hostname, use that hostname followed by `.local`.
2. Put the **Client ID** and **Client Secret** in the config:

   ```toml
   [server]
   mdns_name = "buoycast"     # must match the Pi's hostname

   [strava]
   client_id = "12345"
   client_secret = "..."
   ```

3. Restart BuoyCast. Then, in Settings → Strava, tap **Connect Strava** and
   approve access.

### Peloton

BuoyCast broadcasts your rowing data over Bluetooth as a standard FTMS
rower. Pairing with the Peloton app hasn't been confirmed to work yet. To
try it, and to help debug it, follow section 3 of the
[hardware checklist](hardware-checklist.md#3--ftms-ble-broadcast-to-peloton).

## Updating

New releases show up in **Settings → Software Update** on the dashboard. Tap
**Install Update** there. If the new version doesn't start, BuoyCast switches back
to the previous one automatically.

From the command line:

```bash
sudo buoycast-update                    # install the latest release
sudo buoycast-update --version v0.3.0   # install a specific release
sudo buoycast-update --rollback         # go back to the previous release
```

## Where things live

| Path | What |
|---|---|
| `/opt/buoycast/config.toml` | Your settings |
| `/opt/buoycast/data/` | Workout database and FIT files. Back this up. |
| `/opt/buoycast/logs/` | Log files (also in `journalctl -u buoycast`) |
| `/opt/buoycast/releases/<version>/` | Installed releases. `current` points at the active one. |

## Troubleshooting

| Problem | Try |
|---|---|
| `buoycast.local` doesn't resolve | Use the Pi's IP address instead. Android and older Windows don't always support `.local` names. |
| Dashboard doesn't load | `sudo systemctl status buoycast`, then `journalctl -u buoycast -n 50 --no-pager` |
| Dashboard says "host not allowed" | You opened it by a host name BuoyCast doesn't recognise. Add the name to `[server] allowed_hosts` (see [SECURITY.md](../SECURITY.md)). |
| S4 never connects | Make sure the cable is in the Pi's **USB** port, not PWR, and the monitor is awake. `ls /dev/ttyACM*` should list a device. If not, check `dmesg \| grep -i tty`. |
| Heart rate never connects | Check `device_mac`. Wear the strap so it's awake. Make sure your phone isn't already connected to it, since most straps allow only one connection. |
| The installer fails to download | `curl -I https://github.com` should work from the Pi. Check the Wi-Fi and the date/time (`timedatectl`). |
| Update fails | `journalctl -u buoycast-update -n 50 --no-pager` |

## Uninstall

```bash
sudo systemctl disable --now buoycast buoycast-update.service
sudo rm -f /etc/systemd/system/buoycast.service /etc/systemd/system/buoycast-update.service \
           /etc/polkit-1/rules.d/50-buoycast.rules /usr/local/sbin/buoycast-update
sudo systemctl daemon-reload
sudo rm -rf /opt/buoycast             # deletes your workouts too
sudo userdel buoycast
```
