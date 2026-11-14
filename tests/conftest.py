"""Shared test fixtures for BuoyCast."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.s4.protocol import (
    ADDR_AVG_SPEED,
    ADDR_CALORIES,
    ADDR_DISTANCE_M,
    ADDR_ELAPSED_HOURS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_SECS,
    ADDR_POWER,
    ADDR_STROKE_COUNT,
    ADDR_STROKE_RATE,
    LINE_ENDING,
    RESP_WR,
    RESPONSE_PREFIX,
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

    async def flush_input(self) -> None:
        """Discard any queued responses (simulates flushing serial input buffer)."""
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

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

        # Handle IV? firmware query
        if text == "IV?":
            await self._response_queue.put(b"IV40210" + LINE_ENDING)
            return

        # Handle RESET and EXIT — no response needed
        if text in ("RESET", "EXIT"):
            return

        # Handle IR read commands: IR{size}{addr3hex} (e.g. IRS1A9, IRD055, IRT08A)
        if text.startswith("IR") and len(text) >= 6:
            size_char = text[2]
            addr = text[3:6]
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
        # S4 address 1A9 stores SPM directly (confirmed with hardware)
        self.set_memory(ADDR_STROKE_RATE, int(stroke_rate_spm))
        self.set_memory(ADDR_STROKE_COUNT, stroke_count)
        self.set_memory(ADDR_DISTANCE_M, distance_m)
        # Address 14A stores avg speed in cm/s; convert from pace (s/500m)
        avg_speed_cmps = int(50000 / pace_s_per_500m) if pace_s_per_500m > 0 else 0
        self.set_memory(ADDR_AVG_SPEED, avg_speed_cmps)
        self.set_memory(ADDR_POWER, power_watts)
        self.set_memory(ADDR_CALORIES, calories * 1000)  # stored as millikcal
        # Elapsed time is BCD-encoded on the real S4 — store BCD values so
        # bcd_decode() in the reader produces the right decimal result.
        self.set_memory(ADDR_ELAPSED_HOURS, int(f"{elapsed_hours:02d}", 16))
        self.set_memory(ADDR_ELAPSED_MINS, int(f"{elapsed_minutes:02d}", 16))
        self.set_memory(ADDR_ELAPSED_SECS, int(f"{elapsed_seconds:02d}", 16))

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


class MockBLEClient:
    """Mock BLE client that simulates TICKR HR notifications.

    Supports:
    - Simulated connection and HR notifications on a timer
    - Configurable BPM and RR intervals
    - Simulated disconnect mid-session
    - Unavailable at startup
    """

    def __init__(self) -> None:
        self._is_connected = False
        self._notify_callback: Any = None
        self._notify_task: asyncio.Task[None] | None = None
        self._bpm: int = 140
        self._rr_intervals: list[int] = [700]
        self._notify_interval_s: float = 1.0
        self._disconnect_after_notifications: int | None = None
        self._notification_count = 0
        self._should_fail_connect = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self) -> None:
        if self._should_fail_connect:
            raise OSError("Simulated: TICKR unavailable")
        self._is_connected = True

    async def disconnect(self) -> None:
        self._is_connected = False
        if self._notify_task and not self._notify_task.done():
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None

    async def start_notify(self, char_uuid: str, callback: Any) -> None:
        self._notify_callback = callback
        self._notification_count = 0
        self._notify_task = asyncio.create_task(self._notification_loop())

    async def stop_notify(self, char_uuid: str) -> None:
        if self._notify_task and not self._notify_task.done():
            self._notify_task.cancel()
            try:
                await self._notify_task
            except asyncio.CancelledError:
                pass
            self._notify_task = None
        self._notify_callback = None

    async def _notification_loop(self) -> None:
        """Fire HR notifications at configured interval."""
        while self._is_connected:
            if self._disconnect_after_notifications is not None:
                if self._notification_count >= self._disconnect_after_notifications:
                    self._is_connected = False
                    return

            data = self._build_hr_data()
            if self._notify_callback is not None:
                await self._notify_callback(None, data)
            self._notification_count += 1
            await asyncio.sleep(self._notify_interval_s)

    def _build_hr_data(self) -> bytearray:
        """Build BLE HR Measurement characteristic value."""
        flags = 0x00  # uint8 BPM format
        if self._rr_intervals:
            flags |= 0x10  # RR interval present
        data = bytearray([flags, self._bpm])
        for rr in self._rr_intervals:
            # Convert ms to 1/1024 seconds
            rr_raw = int(round(rr * 1024 / 1000))
            data.extend(rr_raw.to_bytes(2, byteorder="little"))
        return data

    # --- Configuration helpers ---

    def set_hr(self, bpm: int, rr_intervals: list[int] | None = None) -> None:
        """Set the HR values that will be notified."""
        self._bpm = bpm
        self._rr_intervals = rr_intervals or []

    def set_disconnect_after(self, n_notifications: int) -> None:
        """Simulate disconnect after n notifications."""
        self._disconnect_after_notifications = n_notifications
        self._notification_count = 0

    def set_unavailable(self) -> None:
        """Simulate TICKR not found / unavailable."""
        self._should_fail_connect = True

    def set_available(self) -> None:
        """Make TICKR available again after set_unavailable()."""
        self._should_fail_connect = False

    def set_notify_interval(self, seconds: float) -> None:
        """Set interval between HR notifications."""
        self._notify_interval_s = seconds


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


@pytest.fixture
def mock_ble() -> MockBLEClient:
    """Provide a MockBLEClient instance."""
    return MockBLEClient()


@pytest.fixture
def mock_ble_stable() -> MockBLEClient:
    """Provide a MockBLEClient with stable HR data."""
    ble = MockBLEClient()
    ble.set_hr(140, [700])
    ble.set_notify_interval(0.1)  # Fast for tests
    return ble
