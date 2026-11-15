# WaterRower S4 USB Protocol Reference

Documented from working implementation and verified against the following
open-source references:
- [pirowflo](https://github.com/inonoob/pirowflo) — `src/adapters/s4/waterrowerinterface.py`
- [waterrower-core](https://github.com/tbressler/waterrower-core) — Java implementation
- [WaterRowerLinkPlus](https://github.com/nickbits1024/WaterRowerLinkPlus) — ESP32/C

Tested hardware: WaterRower S4 monitor, firmware `IV40210` (hardware type 4, firmware 2.10).

---

## Serial Connection

| Parameter | Value |
|-----------|-------|
| Baud rate | 19200 |
| Data bits | 8 |
| Parity    | None |
| Stop bits | 1 |
| Line ending | `\r\n` (CR+LF) |
| Encoding  | ASCII |

All commands and responses are plain ASCII text terminated with `\r\n`.

---

## Startup Sequence

The correct startup sequence is strictly ordered. Skipping steps causes `ERROR` on all IRD reads.

```
Host → S4:  USB\r\n
S4 → Host:  _WR_\r\n          ← S4 acknowledged, now in PC mode (display shows "PC")
Host → S4:  IV?\r\n            ← request firmware/model info (required before IRD polling)
S4 → Host:  IV40210\r\n        ← IV + model (4=S4) + firmware_hi (02) + firmware_lo (10)
Host → S4:  IR[S|D|T]{addr}\r\n  ← start polling
```

**Critical notes:**
- `IV?` **must** be sent and acknowledged before IRD memory reads will work. Without it, all `IRD` commands return `ERROR`.
- `RESET` is **not** required during startup and should not be sent — it clears all workout data and may interfere with the PC mode state.
- `RESET` is only useful when the user explicitly wants to zero out workout data mid-session.
- Clean disconnect: send `EXIT\r\n` before closing the serial port to release PC mode and allow the S4 to sleep.

---

## Command Format

### Memory Read Request

```
IR{size}{addr3hex}\r\n
```

| size char | Meaning | Response bytes |
|-----------|---------|----------------|
| `S` | Single byte | 1 byte (2 hex chars) |
| `D` | Double byte | 2 bytes (4 hex chars) |
| `T` | Triple byte | 3 bytes (6 hex chars) |

Examples:
- `IRS1A9\r\n` — read single byte at address 0x1A9 (stroke rate)
- `IRD055\r\n` — read double byte at address 0x055 (distance meters)
- `IRT08A\r\n` — read triple byte at address 0x08A (total calories)

> ⚠️ **Common mistake:** The format is `IR{S|D|T}{addr}` — NOT `IRD{S|D|T}{addr}`. The `D` in `IRD` is the size specifier for Double, not a generic prefix. Sending `IRDS1A9` (7 chars) instead of `IRS1A9` (6 chars) causes `ERROR`.

### Other Commands

| Command | Direction | Description |
|---------|-----------|-------------|
| `USB`   | Host→S4   | Initiate USB communication |
| `IV?`   | Host→S4   | Request model/firmware info |
| `EXIT`  | Host→S4   | Release USB mode, allow S4 to sleep |
| `RESET` | Host→S4   | Zero all workout data (use carefully) |

---

## Response Format

### Memory Read Response

```
ID{size}{addr3hex}{valueNhex}\r\n
```

| Response | Format | Length |
|----------|--------|--------|
| `IDS{addr}{val2hex}` | Single byte result | 8 chars |
| `IDD{addr}{val4hex}` | Double byte result | 10 chars |
| `IDT{addr}{val6hex}` | Triple byte result | 12 chars |

Examples:
- `IDS1A91C\r\n` — address 0x1A9, value 0x1C = 28 → stroke rate 28 SPM
- `IDD0550075\r\n` — address 0x055, value 0x0075 = 117 meters
- `IDT08A0012C1\r\n` — address 0x08A, value 0x0012C1 = 4801 millikcal

**Byte order:** Multi-byte values have the high byte first in the hex string (big-endian representation). Direct `int(value_hex, 16)` parsing is correct.

### Spontaneous Messages (S4 → Host, no request needed)

| Message | Meaning |
|---------|---------|
| `_WR_`  | S4 acknowledged USB command |
| `PING`  | Keepalive, sent every ~1 second when idle |
| `P{XX}` | Pulse count — 2 hex digits = pulses in last 25ms window (sent continuously while rowing at ~40 Hz) |
| `SS`    | Stroke Start — drive phase began |
| `SE`    | Stroke End — recovery phase began |
| `OK`    | General acknowledgement (e.g. after RESET) |
| `ERROR` | Unknown or rejected command |
| `IV{model}{hi}{lo}` | Firmware version response |

**Pulse count (`P{XX}`):** Sent at 25ms intervals while the flywheel is moving. Value is the number of encoder pulses in that 25ms window. Can be used to derive instantaneous flywheel velocity (pulse_count × k = speed). At typical rowing pace these arrive at ~40 Hz — they will flood the serial buffer and must be discarded during IRD polling.

**How BuoyCast reads the line:** while connected, one task in `S4Reader` reads every line continuously. Memory-read responses (`IDS`/`IDD`/`IDT`) resolve the poll request waiting for that address; `SS`/`SE` are published immediately as `STROKE` events (forwarded to the dashboard as `{"type": "stroke"}` WebSocket messages) so the animated rower can phase-lock to real strokes; `PING` and pulse counts are ignored. The input buffer is not flushed between polls, since that would drop stroke events.

---

## Memory Map

All addresses use 3 uppercase hex digits. Verified against pirowflo and waterrower-core.

| Address | Size | Label | Unit / Notes |
|---------|------|-------|--------------|
| `055`   | Double | Total distance | meters, `int(val, 16)` |
| `088`   | Double | Instantaneous power | watts, `int(val, 16)`. Zero during recovery phase — use rolling average |
| `08A`   | Triple | Total calories | millikcal, divide by 1000 for kcal |
| `140`   | Double | Total stroke count | strokes, `int(val, 16)` |
| `14A`   | Double | Average speed | cm/s, `int(val, 16)`. Convert to 500m pace: `50000 / cmps` |
| `1A9`   | Single | Stroke rate | SPM directly, `int(val, 16)` (NOT divided by 2) |
| `1E1`   | Single | Elapsed seconds | **BCD encoded** — parse as `int(val, 10)` not `int(val, 16)` |
| `1E2`   | Single | Elapsed minutes | **BCD encoded** — parse as `int(val, 10)` |
| `1E3`   | Single | Elapsed hours   | **BCD encoded** — parse as `int(val, 10)` |
| `1A0`   | Double | Heart rate (onboard) | BPM, only used if no external HR monitor |

**BCD decoding:** Elapsed time addresses store values in BCD (Binary Coded Decimal). The S4 sends `30` for 30 seconds, not `0x30` (=48). After parsing as hex, convert back: `int(format(hex_value, '02X'), 10)`.

### Additional addresses (not currently polled)

| Address | Size | Label |
|---------|------|-------|
| `142`   | Single | Average stroke time (25ms units, derive SPM: `60000 / (val × 25)`) |
| `143`   | Single | Average pull (drive) time in 25ms units |
| `148`   | Double | Total speed (instantaneous, cm/s) |
| `1A6`   | Double | 500m pace (alternate address) |
| `1E0`   | Single | Elapsed sub-second decimal |
| `0A9`   | Single | Tank volume (liters, read once, not in poll loop) |

---

## Polling Strategy

pirowflo polls all addresses in a round-robin loop with 25ms between each request using separate send and receive threads (fire-and-forget). Our implementation uses a sequential send-then-read approach.

**Recommended polling rate:** 4 Hz (250ms per full cycle of 9 addresses).

**Key challenge:** While rowing, the S4 sends `P{XX}` pulse messages at ~40 Hz. These accumulate in the serial buffer and must be discarded while waiting for IRD responses. Mitigations:
1. Flush the serial input buffer before each poll cycle
2. Allow enough read retries per address to drain spurious messages (15+ recommended)
3. Keep serial readline timeout short (100ms) since responses arrive in ~6ms

---

## Known Issues / Gotchas

1. **`IV?` is required before IRD polling.** Without it, all memory reads return `ERROR`. This is not documented in the WaterRower spec but is required in practice.

2. **`IRDS`/`IRDD`/`IRDT` are wrong.** The correct format is `IRS`/`IRD`/`IRT`. Many third-party docs incorrectly show the 4-character prefix variant.

3. **Elapsed time uses BCD encoding.** Addresses `1E1`, `1E2`, `1E3` encode decimal values in hex (30 seconds → byte `0x30`, not `0x1E`). Parse with base 10, not base 16.

4. **Instantaneous power (`088`) is zero during recovery.** The S4 only reports non-zero power during the drive phase. Use a rolling average (e.g. 5-second window) for display.

5. **`RESET` during startup is harmful.** It clears all workout data and may block IRD reads until the user interacts with the monitor. Only send `RESET` if the user explicitly wants to zero the session.

6. **Pulse messages flood during rowing.** `P{XX}` messages arrive every 25ms while the flywheel spins, even if you're not actively pulling. Always flush the buffer before polling and use generous read retries.

7. **`P00` appears immediately after `_WR_`.** The S4 sends one pulse count of 0 right after the USB handshake. This is a firmware quirk — ignore it.
