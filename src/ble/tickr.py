"""TICKR BLE heart rate reader — connects to Wahoo TICKR and reads HR data.

Uses a protocol-based BLE interface so the actual BLE library (bleak)
can be swapped for a mock in tests.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Protocol

from pydantic import ValidationError

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
        (heart_rate_bpm, rr_intervals_ms) — out-of-range RR intervals are
        silently skipped rather than rejecting the entire notification.

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

    # Parse RR intervals — skip out-of-range values instead of failing the
    # entire notification.  A single bad RR interval shouldn't discard a
    # valid BPM reading.
    rr_intervals_ms: list[int] = []
    if rr_present:
        while offset + 1 < len(data):
            rr_raw = int.from_bytes(data[offset : offset + 2], byteorder="little")
            # Convert from 1/1024 seconds to milliseconds
            rr_ms = int(round(rr_raw * 1000 / 1024))
            if 200 <= rr_ms <= 2000:
                rr_intervals_ms.append(rr_ms)
            else:
                logger.debug("Skipping out-of-range RR interval: %dms (raw=%d)", rr_ms, rr_raw)
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
        self._rr_buffer: deque[int] = deque(maxlen=10)
        # Cross-check: track consecutive readings where RR-derived BPM diverges
        # from the BPM field. If divergence persists, the RR buffer is corrupt.
        self._consecutive_divergence = 0
        # Rate-of-change limiting: prevent implausible BPM jumps.
        self._last_emitted_bpm: int | None = None
        # Debug capture: write raw BLE data + processing decisions to JSONL file.
        self._debug_file: IO[str] | None = None

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
        if self._settings.debug_capture:
            self._open_debug_file()
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
        self._close_debug_file()

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
        self._consecutive_divergence = 0
        self._last_emitted_bpm = None
        if was_connected:
            await self._bus.emit(EventType.TICKR_DISCONNECTED)
            logger.info("TICKR disconnected")

    def _open_debug_file(self) -> None:
        """Open a timestamped JSONL file for raw HR data capture."""
        capture_dir = Path(self._settings.debug_capture_dir)
        capture_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = capture_dir / f"hr_capture_{ts}.jsonl"
        self._debug_file = open(path, "a")  # noqa: SIM115
        logger.info("HR debug capture → %s", path)

    def _close_debug_file(self) -> None:
        """Close the debug capture file if open."""
        if self._debug_file is not None:
            self._debug_file.close()
            self._debug_file = None

    def _write_debug(self, record: dict) -> None:
        """Append a JSON record to the debug capture file."""
        if self._debug_file is None:
            return
        try:
            self._debug_file.write(json.dumps(record) + "\n")
            self._debug_file.flush()
        except Exception:
            pass  # never let debug I/O crash the reader

    def _add_rr_intervals(self, rr_intervals: list[int]) -> list[str]:
        """Add RR intervals to the buffer, rejecting physiological outliers.

        Returns a list of debug notes describing what was accepted/rejected.
        """
        notes: list[str] = []
        if not self._rr_buffer:
            accepted = [rr for rr in rr_intervals if rr >= 300]
            rejected = [rr for rr in rr_intervals if rr < 300]
            self._rr_buffer.extend(accepted)
            if rejected:
                notes.append(f"seed_rejected={rejected}")
            return notes

        sorted_buf = sorted(self._rr_buffer)
        mid = len(sorted_buf) // 2
        median = (
            sorted_buf[mid] if len(sorted_buf) % 2 else (sorted_buf[mid - 1] + sorted_buf[mid]) // 2
        )
        for rr in rr_intervals:
            if abs(rr - median) / median <= 0.30:
                self._rr_buffer.append(rr)
            else:
                logger.debug("Rejected RR outlier %dms (median %dms)", rr, median)
                notes.append(f"outlier_rejected={rr}ms(median={median})")
        return notes

    async def _on_hr_notification(self, characteristic: object, data: bytearray) -> None:
        """Handle incoming HR measurement notification."""
        now = datetime.now(tz=UTC)
        debug: dict = {"ts": now.isoformat(), "raw_hex": data.hex()}

        try:
            raw_bpm, rr_intervals = parse_hr_measurement(data)
        except ValueError as e:
            logger.debug("Skipping invalid HR data: %s", e)
            debug["error"] = str(e)
            self._write_debug(debug)
            return

        debug["raw_bpm"] = raw_bpm
        debug["rr_intervals_ms"] = rr_intervals
        debug["bpm_field_doubled"] = self._settings.bpm_field_doubled

        # Determine the "field BPM" — the BPM value reported directly by the
        # TICKR hardware, corrected for the known doubling firmware bug.
        field_bpm = raw_bpm // 2 if self._settings.bpm_field_doubled else raw_bpm
        debug["field_bpm"] = field_bpm

        # Add RR intervals to the buffer (outlier-filtered).
        rr_notes = self._add_rr_intervals(rr_intervals)
        debug["rr_buffer"] = list(self._rr_buffer)
        debug["rr_notes"] = rr_notes

        bpm = field_bpm  # default: use field BPM
        debug["bpm_source"] = "field"

        # Prefer RR-derived BPM when the buffer has data.
        #
        # Cross-check: compare RR-derived BPM against the RAW BPM (not the
        # halved field_bpm).  When bpm_field_doubled is True, the raw BPM is
        # ~2x the real HR, so comparing against it avoids false positives where
        # the correct RR-derived value looks "too high" vs the halved field.
        if self._rr_buffer:
            rr_bpm = round(60000 / (sum(self._rr_buffer) / len(self._rr_buffer)))
            debug["rr_derived_bpm"] = rr_bpm

            if raw_bpm > 0 and rr_bpm > raw_bpm * 1.40:
                self._consecutive_divergence += 1
                debug["divergence_count"] = self._consecutive_divergence
                if self._consecutive_divergence >= 3:
                    logger.warning(
                        "RR buffer appears corrupted (RR-derived %d >> raw %d) "
                        "after %d divergences, resetting",
                        rr_bpm,
                        raw_bpm,
                        self._consecutive_divergence,
                    )
                    self._rr_buffer.clear()
                    self._consecutive_divergence = 0
                    debug["action"] = "rr_buffer_reset"
                bpm = field_bpm
                debug["bpm_source"] = "field(divergence)"
            else:
                self._consecutive_divergence = 0
                bpm = rr_bpm
                debug["bpm_source"] = "rr_derived"

        # Rate-of-change limiting: physiologically, HR cannot jump more than
        # ~15 BPM between consecutive 1-second notifications.
        pre_limit_bpm = bpm
        if self._last_emitted_bpm is not None:
            max_delta = 15
            delta = bpm - self._last_emitted_bpm
            if abs(delta) > max_delta:
                bpm = self._last_emitted_bpm + (max_delta if delta > 0 else -max_delta)
                logger.debug(
                    "Rate-limited HR change: %d -> %d (clamped delta %d)",
                    self._last_emitted_bpm,
                    bpm,
                    delta,
                )
        if bpm != pre_limit_bpm:
            debug["rate_limited_from"] = pre_limit_bpm
        debug["emitted_bpm"] = bpm
        self._last_emitted_bpm = bpm

        self._write_debug(debug)

        try:
            metrics = RowingMetrics(
                timestamp=now,
                heart_rate_bpm=bpm,
                rr_intervals_ms=rr_intervals if rr_intervals else None,
            )
        except ValidationError as e:
            logger.debug("Skipping HR with invalid derived BPM %d: %s", bpm, e)
            return
        await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)
