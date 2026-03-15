"""TICKR BLE heart rate reader — connects to Wahoo TICKR and reads HR data.

Uses a protocol-based BLE interface so the actual BLE library (bleak)
can be swapped for a mock in tests.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Protocol

from src.config import HeartRateSettings
from src.events import EventBus, EventType
from src.models import RowingMetrics

logger = logging.getLogger(__name__)

# BLE Heart Rate Service UUIDs
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# Exponential backoff constants
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0


class BLEClient(Protocol):
    """Minimal BLE client interface — allows injection of real (bleak) or mock."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def start_notify(self, char_uuid: str, callback: NotifyCallback) -> None: ...
    async def stop_notify(self, char_uuid: str) -> None: ...
    @property
    def is_connected(self) -> bool: ...


# Type alias for BLE notification callbacks
NotifyCallback = object  # Callable[[bytearray], None] — kept loose for Protocol compat


def parse_hr_measurement(data: bytes | bytearray) -> tuple[int, list[int]]:
    """Parse a BLE Heart Rate Measurement characteristic value.

    Per Bluetooth HRS spec (0x2A37):
    - Byte 0: flags
        - Bit 0: 0 = uint8 BPM, 1 = uint16 BPM
        - Bit 4: 1 = RR intervals present
    - Byte 1 (or 1–2): BPM value
    - Remaining bytes: RR intervals as uint16 LE (units of 1/1024 seconds)

    Args:
        data: raw characteristic bytes

    Returns:
        (heart_rate_bpm, rr_intervals_ms)

    Raises:
        ValueError: if data is too short or BPM is out of range
    """
    if len(data) < 2:
        raise ValueError(f"HR measurement too short: {len(data)} bytes")

    flags = data[0]
    hr_format_16bit = bool(flags & 0x01)
    rr_present = bool(flags & 0x10)

    # Parse BPM
    if hr_format_16bit:
        if len(data) < 3:
            raise ValueError("HR uint16 format but data too short")
        bpm = int.from_bytes(data[1:3], byteorder="little")
        offset = 3
    else:
        bpm = data[1]
        offset = 2

    if bpm < 20 or bpm > 250:
        raise ValueError(f"Heart rate out of range: {bpm} BPM")

    # Parse RR intervals
    rr_intervals_ms: list[int] = []
    if rr_present:
        while offset + 1 < len(data):
            rr_raw = int.from_bytes(data[offset : offset + 2], byteorder="little")
            # Convert from 1/1024 seconds to milliseconds
            rr_ms = int(round(rr_raw * 1000 / 1024))
            if rr_ms < 200 or rr_ms > 2000:
                raise ValueError(f"RR interval out of range: {rr_ms} ms")
            rr_intervals_ms.append(rr_ms)
            offset += 2

    return bpm, rr_intervals_ms


class TickrReader:
    """Async BLE reader for Wahoo TICKR heart rate monitor.

    Lifecycle:
        reader = TickrReader(ble_client, event_bus, settings)
        await reader.start()   # runs until stop() is called
        await reader.stop()
    """

    def __init__(
        self,
        ble_client: BLEClient | Callable[[], BLEClient],
        event_bus: EventBus,
        settings: HeartRateSettings | None = None,
        *,
        backoff_base_s: float = BACKOFF_BASE_S,
        backoff_max_s: float = BACKOFF_MAX_S,
        poll_interval_s: float = 0.5,
    ) -> None:
        if callable(ble_client) and not hasattr(ble_client, "connect"):
            self._ble_factory: Callable[[], BLEClient] | None = ble_client
            # Don't eagerly call async factories — the coroutine would never be awaited.
            # _run_loop creates the client on each connect attempt.
            self._ble: BLEClient | None = (  # type: ignore[assignment]
                None if inspect.iscoroutinefunction(ble_client) else ble_client()
            )
        else:
            self._ble_factory = None
            self._ble = ble_client  # type: ignore[assignment]
        self._bus = event_bus
        self._settings = settings or HeartRateSettings()
        self._running = False
        self._connected = False
        self._paused = False
        self._task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._poll_interval_s = poll_interval_s
        # Rolling buffer of recent RR intervals (ms). BPM is derived from their
        # average rather than from a single beat, which eliminates HRV noise and
        # prevents the TICKR's double-counting firmware bug from reaching the UI.
        self._rr_buffer: deque[int] = deque(maxlen=6)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    async def pause_reading(self) -> None:
        """Stop reading (disconnect, no auto-reconnect)."""
        self._paused = True
        await self._disconnect()
        logger.info("TICKR reading paused")

    async def resume_reading(self) -> None:
        """Resume reading (allow reconnection)."""
        self._paused = False
        logger.info("TICKR reading resumed")

    async def start(self) -> None:
        """Start the reader loop as a background task."""
        if not self._settings.enabled:
            logger.info("TICKR disabled in config, skipping")
            return
        if not self._settings.device_mac:
            logger.warning("No TICKR MAC address configured")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the reader and disconnect."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._disconnect()

    async def _run_loop(self) -> None:
        """Main loop: connect → listen → reconnect with exponential backoff."""
        backoff = self._backoff_base_s

        while self._running:
            # Skip connection attempts if paused
            if self._paused:
                await asyncio.sleep(self._poll_interval_s)
                continue

            try:
                # Recreate the BLE client each attempt — on Linux/BlueZ a failed
                # connection leaves the client in a broken state that can't be reused.
                if self._ble_factory is not None:
                    client = self._ble_factory()
                    if asyncio.iscoroutine(client):
                        client = await client
                    self._ble = client
                await self._connect()
                backoff = self._backoff_base_s  # Reset on successful connection
                self._consecutive_failures = 0

                # Stay connected until disconnect or stop
                while self._running and not self._paused and self._ble.is_connected:
                    await asyncio.sleep(self._poll_interval_s)

                # If we get here, BLE disconnected
                await self._disconnect()

            except (OSError, Exception) as e:
                self._consecutive_failures += 1
                msg = str(e) or type(e).__name__
                if self._consecutive_failures == 1:
                    logger.warning("TICKR connection error: %s", msg)
                else:
                    logger.debug("TICKR reconnect attempt %d: %s", self._consecutive_failures, msg)
                logger.debug("TICKR connection error details:", exc_info=True)
                await self._disconnect()

            if self._running:
                logger.debug("TICKR reconnecting in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._backoff_max_s)

    async def _connect(self) -> None:
        """Connect to TICKR and subscribe to HR notifications."""
        logger.debug("TICKR: calling connect()...")
        await asyncio.wait_for(self._ble.connect(), timeout=10.0)
        logger.debug("TICKR: connect() succeeded, subscribing to notifications...")
        await asyncio.wait_for(
            self._ble.start_notify(HR_MEASUREMENT_UUID, self._on_hr_notification),
            timeout=10.0,
        )
        self._connected = True
        await self._bus.emit(EventType.TICKR_CONNECTED)
        logger.info("TICKR connected: %s", self._settings.device_mac)

    async def _disconnect(self) -> None:
        """Disconnect from TICKR and fire event."""
        was_connected = self._connected
        self._connected = False
        if self._ble is not None:
            try:
                if self._ble.is_connected:
                    await self._ble.stop_notify(HR_MEASUREMENT_UUID)
            except Exception:
                pass
            try:
                # Always call disconnect — even if connect() timed out, BlueZ may
                # still have a pending connection attempt that must be cancelled.
                # Skipping this leaves BlueZ stuck and causes the next connect to
                # also time out.
                await self._ble.disconnect()
            except Exception:
                pass
        self._rr_buffer.clear()
        if was_connected:
            await self._bus.emit(EventType.TICKR_DISCONNECTED)
            logger.info("TICKR disconnected")

    def _add_rr_intervals(self, rr_intervals: list[int]) -> None:
        """Add RR intervals to the buffer, rejecting physiological outliers.

        Spurious R-wave detections from poor skin contact produce short RR
        intervals (e.g. 200-300ms) that would wildly distort a mean. We reject
        any incoming interval that deviates more than 30% from the current
        buffer median. On an empty buffer every value is accepted so the reader
        locks on quickly after connect.
        """
        if not self._rr_buffer:
            # Seed with physiologically plausible intervals only (≤ 200 BPM).
            # Short intervals from double-counted beats (poor initial contact,
            # TICKR firmware quirk) would corrupt the median baseline and then
            # cause all subsequent valid intervals to be rejected as outliers.
            self._rr_buffer.extend(rr for rr in rr_intervals if rr >= 300)
            return

        sorted_buf = sorted(self._rr_buffer)
        mid = len(sorted_buf) // 2
        median = (
            sorted_buf[mid]
            if len(sorted_buf) % 2
            else (sorted_buf[mid - 1] + sorted_buf[mid]) // 2
        )
        for rr in rr_intervals:
            if abs(rr - median) / median <= 0.30:
                self._rr_buffer.append(rr)
            else:
                logger.debug("Rejected RR outlier %dms (median %dms)", rr, median)

    async def _on_hr_notification(self, characteristic: object, data: bytearray) -> None:
        """Handle incoming HR measurement notification."""
        try:
            bpm, rr_intervals = parse_hr_measurement(data)
        except ValueError as e:
            logger.debug("Skipping invalid HR data: %s", e)
            return

        # Prefer RR-derived BPM — it reflects actual beat-to-beat timing and is
        # immune to the TICKR BPM-doubling firmware bug.  Outliers are filtered
        # first so that a single spurious detection doesn't corrupt the average.
        #
        # Fallback chain when no clean RR data is available:
        #   1. bpm_field_doubled=True in config → BPM field / 2
        #   2. Otherwise → BPM field as-is
        self._add_rr_intervals(rr_intervals)
        if self._rr_buffer:
            bpm = round(60000 / (sum(self._rr_buffer) / len(self._rr_buffer)))
        elif self._settings.bpm_field_doubled:
            bpm = bpm // 2

        metrics = RowingMetrics(
            timestamp=datetime.now(tz=timezone.utc),
            heart_rate_bpm=bpm,
            rr_intervals_ms=rr_intervals if rr_intervals else None,
        )
        await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)
