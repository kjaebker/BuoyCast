"""Raw S4 serial dump — sends USB handshake, listens, then probes IRD commands.

Run on the Pi:
    python tools/s4_raw_dump.py [port]

Default port: /dev/ttyACM0
"""

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUD = 19200
TIMEOUT = 0.5

print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, baudrate=BAUD, timeout=TIMEOUT)
ser.reset_input_buffer()
t0 = time.time()

def ts():
    return time.time() - t0

def send(cmd):
    line = (cmd + "\r\n").encode("ascii")
    print(f"[{ts():6.2f}] >> {cmd!r}")
    ser.write(line)

def read_all(duration):
    end = time.time() + duration
    while time.time() < end:
        raw = ser.readline()
        if raw:
            try:
                decoded = raw.decode("ascii", errors="replace").strip()
            except Exception:
                decoded = repr(raw)
            print(f"[{ts():6.2f}] << {decoded!r}  (hex: {raw.hex()})")
        else:
            print(f"[{ts():6.2f}] (no data)")

# Step 1: handshake
send("USB")
print("--- listening 5s after USB ---")
read_all(5)

# Step 2: probe IRD commands
print("--- probing IRD commands ---")
for cmd in ["IRDS000", "IRDS001", "IRDS1E3", "IRDD1E3", "IRDD140", "IRDD057"]:
    send(cmd)
    read_all(1.5)

# Step 3: listen to spontaneous traffic
print("--- listening 30s (row now!) ---")
read_all(30)

ser.close()
print("Done.")
