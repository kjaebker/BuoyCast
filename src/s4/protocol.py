"""WaterRower S4/S5 USB serial protocol — constants, commands, and parsers.

The S4 monitor communicates via ASCII text over USB CDC serial at 19200 baud.
Each command/response is a string terminated by \\r\\n.

Reference: WaterRower S4/S5 USB Protocol Specification.
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
CMD_USB = "USB"  # Initiate USB communication; S4 responds with _WR_
CMD_RESET = "RESET"  # Clear distance/time/stroke counters

# Memory read commands — format: "IRD{size}{addr3hex}"
# size: S = single byte, D = double byte, T = triple byte
CMD_IRD_PREFIX = "IRD"

# Memory write commands — format: "IRS{size}{addr3hex}{value}"
CMD_IRS_PREFIX = "IRS"

# Exit USB mode
CMD_EXIT = "EXIT"

# Request firmware version
CMD_IV = "IV?"

# ---------------------------------------------------------------------------
# S4 → Host responses / spontaneous messages
# ---------------------------------------------------------------------------
RESP_WR = "_WR_"  # S4 acknowledge of USB command
RESP_IV = "IV"  # Firmware version prefix
RESP_SS = "SS"  # Stroke Start — pushed when a new stroke begins
RESP_SE = "SE"  # Stroke End — pushed at the end of a stroke
RESP_PING = "PING"  # Keepalive, sent periodically by S4
RESP_OK = "OK"  # General acknowledgement
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
# S4 memory map — key addresses (3-hex-digit format)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MemoryLocation:
    """A named location in the S4 memory map."""

    address: str  # 3 hex chars, e.g. "140"
    size: ReadSize
    label: str


# Stroke / speed
ADDR_STROKE_RATE = MemoryLocation("140", ReadSize.DOUBLE, "stroke_rate")
ADDR_STROKE_COUNT = MemoryLocation("142", ReadSize.DOUBLE, "stroke_count")

# Distance
ADDR_DISTANCE_M = MemoryLocation("057", ReadSize.DOUBLE, "distance_meters")
ADDR_DISTANCE_CM = MemoryLocation("054", ReadSize.DOUBLE, "distance_cm")

# Pace
ADDR_PACE = MemoryLocation("1A5", ReadSize.DOUBLE, "pace_seconds_per_500m")

# Power
ADDR_POWER = MemoryLocation("148", ReadSize.DOUBLE, "power_watts")

# Calories
ADDR_CALORIES = MemoryLocation("088", ReadSize.TRIPLE, "calories")

# Elapsed time
ADDR_ELAPSED_HOURS = MemoryLocation("1E1", ReadSize.SINGLE, "elapsed_hours")
ADDR_ELAPSED_MINS = MemoryLocation("1E2", ReadSize.SINGLE, "elapsed_minutes")
ADDR_ELAPSED_SECS = MemoryLocation("1E3", ReadSize.SINGLE, "elapsed_seconds")

# Heart rate (from S4 onboard — not used when TICKR is connected)
ADDR_HEART_RATE = MemoryLocation("1A0", ReadSize.DOUBLE, "heart_rate_bpm")

# Drive length
ADDR_DRIVE_LENGTH = MemoryLocation("142", ReadSize.DOUBLE, "drive_length")

# All addresses to poll during normal operation
POLL_ADDRESSES: list[MemoryLocation] = [
    ADDR_STROKE_RATE,
    ADDR_STROKE_COUNT,
    ADDR_DISTANCE_M,
    ADDR_PACE,
    ADDR_POWER,
    ADDR_CALORIES,
    ADDR_ELAPSED_HOURS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_SECS,
]


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------
def build_read_command(location: MemoryLocation) -> str:
    """Build an IRD command string for a memory location (without line ending)."""
    return f"{CMD_IRD_PREFIX}{location.size.value}{location.address}"


def build_handshake() -> str:
    """Build the USB handshake command."""
    return CMD_USB


def build_reset() -> str:
    """Build the reset/clear-memory command."""
    return CMD_RESET


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
            payload = line[len(prefix) :]
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

    # Unknown response — don't crash, return as-is
    return line, None, None


# ---------------------------------------------------------------------------
# Value conversion utilities
# ---------------------------------------------------------------------------
def parse_single_byte(value: int) -> int:
    """Parse a single-byte (0–255) integer value."""
    if not 0 <= value <= 0xFF:
        raise ProtocolError(f"Single byte value out of range: {value}")
    return value


def parse_double_byte(value: int) -> int:
    """Parse a double-byte (0–65535) integer value."""
    if not 0 <= value <= 0xFFFF:
        raise ProtocolError(f"Double byte value out of range: {value}")
    return value


def parse_triple_byte(value: int) -> int:
    """Parse a triple-byte (0–16777215) integer value."""
    if not 0 <= value <= 0xFFFFFF:
        raise ProtocolError(f"Triple byte value out of range: {value}")
    return value


def stroke_rate_raw_to_spm(raw: int) -> float:
    """Convert raw stroke rate value to strokes per minute.

    The S4 reports stroke rate as SPM × 2 (resolution 0.5 SPM).
    """
    return raw / 2.0


def pace_raw_to_seconds_per_500m(raw: int) -> float:
    """Convert raw pace value to seconds per 500m.

    The S4 reports pace in units of seconds/500m × 10 (0.1s resolution).
    A raw value of 0 means no pace data (not rowing).
    """
    if raw == 0:
        return 0.0
    return raw / 10.0


def assemble_distance(meters: int, cm: int = 0) -> float:
    """Assemble total distance from meter and centimeter readings.

    Args:
        meters: distance in whole meters from ADDR_DISTANCE_M
        cm: optional centimeters from ADDR_DISTANCE_CM

    Returns:
        Total distance in meters as a float.
    """
    return meters + (cm / 100.0)


def elapsed_time_to_seconds(hours: int, minutes: int, seconds: int) -> int:
    """Convert split elapsed time fields to total seconds."""
    return hours * 3600 + minutes * 60 + seconds
