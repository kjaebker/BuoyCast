"""Shared test fixtures for BuoyCast."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import pytest

from src.s4.protocol import (
    ADDR_CALORIES,
    ADDR_DISTANCE_M,
    ADDR_ELAPSED_HOURS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_SECS,
    ADDR_PACE,
    ADDR_POWER,
    ADDR_STROKE_COUNT,
    ADDR_STROKE_RATE,
    LINE_ENDING,
    POLL_ADDRESSES,
    RESPONSE_PREFIX,
    RESP_WR,
    VALUE_HEX_DIGITS,
    MemoryLocation,
)


class MockSerial:
    """Mock serial port that replays pre-configured S4 responses.

    Supports:
    - Handshake simulation (_WR_ response to USB command)
    - Memory read responses (IDS/IDD/IDT) for polled addresses
    - Simulated disconnect mid-stream
    - Injection of malformed/corrupt data
    """

    def __init__(self) -> None:
        self._is_open = False
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._write_log: list[bytes] = []
        self._should_disconnect = False
        self._disconnect_after: int | None = None
        self._read_count = 0

        # Memory contents: address -> value (int)
        self._memory: dict[str, int] = {}
        self._handshake_done = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def write_log(self) -> list[bytes]:
        """All data written to the port."""
        return self._write_log

    async def open(self) -> None:
        if self._is_open:
            raise OSError("Port already open")
        self._is_open = True
        self._handshake_done = False

    async def close(self) -> None:
        self._is_open = False

    async def write(self, data: bytes) -> None:
        if not self._is_open:
            raise OSError("Port not open")
        self._write_log.append(data)
        text = data.decode("ascii").strip()

        # Handle USB handshake
        if text == "USB":
            await self._response_queue.put(RESP_WR.encode() + LINE_ENDING)
            self._handshake_done = True
            return

        # Handle RESET
        if text == "RESET":
            return

        # Handle IRD commands: IRD{size}{addr}
        if text.startswith("IRD") and len(text) >= 7:
            size_char = text[3]
            addr = text[4:7]
            await self._generate_read_response(size_char, addr)

    async def readline(self) -> bytes:
        if not self._is_open:
            raise OSError("Port not open")

        # Check for simulated disconnect
        self._read_count += 1
        if self._disconnect_after is not None and self._read_count > self._disconnect_after:
            self._is_open = False
            raise OSError("Simulated disconnect")

        return await self._response_queue.get()

    async def _generate_read_response(self, size_char: str, addr: str) -> None:
        """Generate a memory read response based on stored memory contents."""
        from src.s4.protocol import ReadSize

        size_map = {"S": ReadSize.SINGLE, "D": ReadSize.DOUBLE, "T": ReadSize.TRIPLE}
        size = size_map.get(size_char)
        if size is None:
            return

        value = self._memory.get(addr, 0)
        prefix = RESPONSE_PREFIX[size]
        hex_digits = VALUE_HEX_DIGITS[size]
        value_hex = f"{value:0{hex_digits}X}"
        response = f"{prefix}{addr}{value_hex}"
        await self._response_queue.put(response.encode() + LINE_ENDING)

    # --- Configuration helpers for tests ---

    def set_memory(self, location: MemoryLocation, value: int) -> None:
        """Set a memory value that will be returned on read."""
        self._memory[location.address] = value

    def set_disconnect_after(self, n_reads: int) -> None:
        """Simulate a disconnect after n readline() calls."""
        self._disconnect_after = n_reads
        self._read_count = 0

    def queue_raw_response(self, data: bytes) -> None:
        """Queue a raw response to be returned by readline()."""
        self._response_queue.put_nowait(data)

    def set_steady_state(
        self,
        stroke_rate_spm: float = 28.0,
        stroke_count: int = 100,
        distance_m: int = 500,
        pace_s_per_500m: float = 120.0,
        power_watts: int = 150,
        calories: int = 50,
        elapsed_hours: int = 0,
        elapsed_minutes: int = 10,
        elapsed_seconds: int = 0,
    ) -> None:
        """Configure memory for steady-state rowing data."""
        self.set_memory(ADDR_STROKE_RATE, int(stroke_rate_spm * 2))
        self.set_memory(ADDR_STROKE_COUNT, stroke_count)
        self.set_memory(ADDR_DISTANCE_M, distance_m)
        self.set_memory(ADDR_PACE, int(pace_s_per_500m * 10))
        self.set_memory(ADDR_POWER, power_watts)
        self.set_memory(ADDR_CALORIES, calories)
        self.set_memory(ADDR_ELAPSED_HOURS, elapsed_hours)
        self.set_memory(ADDR_ELAPSED_MINS, elapsed_minutes)
        self.set_memory(ADDR_ELAPSED_SECS, elapsed_seconds)

    def set_idle(self) -> None:
        """Configure memory for idle S4 (no strokes)."""
        self.set_steady_state(
            stroke_rate_spm=0,
            stroke_count=0,
            distance_m=0,
            pace_s_per_500m=0,
            power_watts=0,
            calories=0,
            elapsed_hours=0,
            elapsed_minutes=0,
            elapsed_seconds=0,
        )


@pytest.fixture
def mock_serial() -> MockSerial:
    """Provide a MockSerial instance."""
    return MockSerial()


@pytest.fixture
def mock_serial_steady() -> MockSerial:
    """Provide a MockSerial with steady-state rowing data."""
    ms = MockSerial()
    ms.set_steady_state()
    return ms


@pytest.fixture
def mock_serial_idle() -> MockSerial:
    """Provide a MockSerial with idle (no strokes) data."""
    ms = MockSerial()
    ms.set_idle()
    return ms
