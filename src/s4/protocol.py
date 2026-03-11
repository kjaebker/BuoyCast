"""WaterRower S4/S5 USB serial protocol — constants, commands, and parsers.

The S4 monitor communicates via ASCII text over USB CDC serial at 19200 baud.
Each command/response is a string terminated by \\r\\n.

Reference: WaterRower S4/S5 USB Protocol Specification.
Verified against: pirowflo (inonoob), waterrower-core (tbressler), WaterRowerLinkPlus.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProtocolError(Exception):
    """Raised when a protocol violation or malformed data is encountered."""


# ---------------------------------------------------------------------------
# Serial settings
# ---------------------------------------------------------------------------
BAUD_RATE = 19200
LINE_ENDING = b"\r\n"

# ---------------------------------------------------------------------------
# Host → S4 commands (ASCII strings, sent with LINE_ENDING appended)
# ---------------------------------------------------------------------------
CMD_USB = "USB"    # Initiate USB communication; S4 responds with _WR_
CMD_RESET = "RESET"  # Clear distance/time/stroke counters
CMD_IV = "IV?"     # Request firmware/model version; S4 responds with IV{model}{ver}
CMD_EXIT = "EXIT"  # Release USB mode so S4 can enter sleep

# Memory read commands — format: "IR{size}{addr3hex}"
# IRS = read single byte, IRD = read double byte, IRT = read triple byte
CMD_IR_PREFIX = "IR"

# ---------------------------------------------------------------------------
# S4 → Host responses / spontaneous messages
# ---------------------------------------------------------------------------
RESP_WR = "_WR_"    # S4 acknowledge of USB command
RESP_IV = "IV"      # Firmware version prefix
RESP_SS = "SS"      # Stroke Start — pushed when a new stroke begins
RESP_SE = "SE"      # Stroke End — pushed at the end of a stroke
RESP_PING = "PING"  # Keepalive, sent ~1/s when idle
RESP_OK = "OK"      # General acknowledgement
RESP_ERROR = "ERROR"  # Error response

# Individual Data response prefixes
RESP_IDS = "IDS"  # Single-byte read response: IDS{addr3hex}{val2hex}
RESP_IDD = "IDD"  # Double-byte read response: IDD{addr3hex}{val4hex}
RESP_IDT = "IDT"  # Triple-byte read response: IDT{addr3hex}{val6hex}


# ---------------------------------------------------------------------------
# Read size specifiers
# ---------------------------------------------------------------------------
class ReadSize(str, Enum):
    """Size specifier for IRD/IRS memory read commands."""

    SINGLE = "S"  # 1 byte  (2 hex chars in response)
    DOUBLE = "D"  # 2 bytes (4 hex chars in response)
    TRIPLE = "T"  # 3 bytes (6 hex chars in response)


# Number of hex digits in the response value for each read size
VALUE_HEX_DIGITS: dict[ReadSize, int] = {
    ReadSize.SINGLE: 2,
    ReadSize.DOUBLE: 4,
    ReadSize.TRIPLE: 6,
}

# Response prefix for each read size
RESPONSE_PREFIX: dict[ReadSize, str] = {
    ReadSize.SINGLE: RESP_IDS,
    ReadSize.DOUBLE: RESP_IDD,
    ReadSize.TRIPLE: RESP_IDT,
}


# ---------------------------------------------------------------------------
# S4 memory map — verified addresses (3-hex-digit format)
# Sources: pirowflo waterrowerinterface.py, waterrower-core MemoryLocation.java
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MemoryLocation:
    """A named location in the S4 memory map."""

    address: str  # 3 hex chars, e.g. "140"
    size: ReadSize
    label: str


# Stroke rate: raw value, SPM = raw × 2
ADDR_STROKE_RATE = MemoryLocation("1A9", ReadSize.SINGLE, "stroke_rate")

# Total stroke count
ADDR_STROKE_COUNT = MemoryLocation("140", ReadSize.DOUBLE, "stroke_count")

# Distance in whole meters
ADDR_DISTANCE_M = MemoryLocation("055", ReadSize.DOUBLE, "distance_meters")

# Average speed in cm/s — used to derive 500m pace
ADDR_AVG_SPEED = MemoryLocation("14A", ReadSize.DOUBLE, "avg_speed_cmps")

# Instantaneous power in watts
ADDR_POWER = MemoryLocation("088", ReadSize.DOUBLE, "power_watts")

# Total calories (kcal)
ADDR_CALORIES = MemoryLocation("08A", ReadSize.TRIPLE, "calories")

# Elapsed time — each is a single byte (0–59 for s/m, 0–99 for h)
ADDR_ELAPSED_SECS = MemoryLocation("1E1", ReadSize.SINGLE, "elapsed_seconds")
ADDR_ELAPSED_MINS = MemoryLocation("1E2", ReadSize.SINGLE, "elapsed_minutes")
ADDR_ELAPSED_HOURS = MemoryLocation("1E3", ReadSize.SINGLE, "elapsed_hours")

# Heart rate from S4 onboard sensor (not used when TICKR is connected)
ADDR_HEART_RATE = MemoryLocation("1A0", ReadSize.DOUBLE, "heart_rate_bpm")

# All addresses to poll during normal operation
POLL_ADDRESSES: list[MemoryLocation] = [
    ADDR_STROKE_RATE,
    ADDR_STROKE_COUNT,
    ADDR_DISTANCE_M,
    ADDR_AVG_SPEED,
    ADDR_POWER,
    ADDR_CALORIES,
    ADDR_ELAPSED_SECS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_HOURS,
]


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------
def build_read_command(location: MemoryLocation) -> str:
    """Build an IR read command for a memory location (without line ending).

    Format: IR{S|D|T}{addr3hex}
      IRS = single byte read, IRD = double byte read, IRT = triple byte read
    """
    return f"{CMD_IR_PREFIX}{location.size.value}{location.address}"


def build_handshake() -> str:
    """Build the USB handshake command."""
    return CMD_USB


def build_iv_query() -> str:
    """Build the firmware version query command."""
    return CMD_IV


def build_exit() -> str:
    """Build the EXIT command — releases USB mode so the S4 can enter sleep."""
    return CMD_EXIT


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------
def parse_response(line: str) -> tuple[str, str | None, int | None]:
    """Parse a raw response line from S4.

    Returns:
        (response_type, address_or_none, value_or_none)

    For data responses (IDS/IDD/IDT):
        response_type = "IDS"/"IDD"/"IDT"
        address = 3-hex-char string
        value = parsed integer

    For other responses:
        response_type = the full line (e.g. "_WR_", "SS", "PING")
        address = None
        value = None

    Raises:
        ProtocolError: if response is malformed
    """
    line = line.strip()
    if not line:
        raise ProtocolError("Empty response line")

    # Check for data responses
    for size, prefix in RESPONSE_PREFIX.items():
        if line.startswith(prefix):
            expected_hex = VALUE_HEX_DIGITS[size]
            payload = line[len(prefix):]
            # Payload format: {addr3hex}{valueNhex}
            expected_len = 3 + expected_hex
            if len(payload) != expected_len:
                raise ProtocolError(
                    f"Malformed {prefix} response: expected {expected_len} hex chars "
                    f"after prefix, got {len(payload)}: '{line}'"
                )
            addr = payload[:3]
            value_hex = payload[3:]
            try:
                value = int(value_hex, 16)
            except ValueError:
                raise ProtocolError(
                    f"Invalid hex value in {prefix} response: '{value_hex}' in '{line}'"
                )
            return prefix, addr, value

    # Non-data responses
    if line in (RESP_WR, RESP_SS, RESP_SE, RESP_PING, RESP_OK, RESP_ERROR):
        return line, None, None

    # Firmware version
    if line.startswith(RESP_IV):
        return RESP_IV, None, None

    # Unknown response (e.g. pulse count "P02", undocumented stroke messages) — discard
    return line, None, None


# ---------------------------------------------------------------------------
# Value conversion utilities
# ---------------------------------------------------------------------------
def stroke_rate_raw_to_spm(raw: int) -> float:
    """Convert raw stroke rate (address 1A9) to strokes per minute.

    Address 1A9 stores SPM directly (confirmed: S4 display matches raw value).
    """
    return float(raw)


def avg_speed_to_pace(cmps: int) -> float:
    """Convert average speed (cm/s, address 14A) to seconds per 500m.

    pace = 500m / speed(m/s) = 50000cm / speed(cm/s)
    Returns 0.0 when speed is zero (not rowing).
    """
    if cmps == 0:
        return 0.0
    return 50000.0 / cmps


def bcd_decode(hex_value: int) -> int:
    """Decode a BCD-encoded value that was parsed as hex.

    Elapsed time fields (1E1, 1E2, 1E3) use decimal (BCD) encoding:
    the S4 sends "30" for 30 seconds, not 0x30 (=48). After int("30", 16)=48,
    this converts back: 48 → "30" → int("30", 10) = 30.
    """
    return int(f"{hex_value:02X}", 10)


def elapsed_time_to_seconds(hours: int, minutes: int, seconds: int) -> int:
    """Convert split elapsed time fields to total seconds."""
    return hours * 3600 + minutes * 60 + seconds
