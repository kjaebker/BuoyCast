"""Raw S4 serial dump — sends USB handshake then prints every line received.

Run on the Pi:
    python tools/s4_raw_dump.py [port]

Default port: /dev/ttyACM0
Rows for ~60 seconds, printing every byte as received with timestamps.
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

def send(cmd):
    line = (cmd + "\r\n").encode("ascii")
    print(f"  >> {cmd!r}")
    ser.write(line)

print("Sending USB handshake...")
send("USB")

start = time.time()
while time.time() - start < 60:
    raw = ser.readline()
    ts = time.time() - start
    if raw:
        try:
            decoded = raw.decode("ascii", errors="replace").strip()
        except Exception as e:
            decoded = repr(raw)
        print(f"[{ts:6.2f}] << {decoded!r}  (raw: {raw.hex()})")
    else:
        print(f"[{ts:6.2f}] (timeout / no data)")

ser.close()
print("Done.")
