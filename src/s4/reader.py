"""S4 serial reader — async interface to the WaterRower S4 monitor.

Connects via USB CDC serial, performs handshake, polls memory addresses
at configured intervals, and publishes RowingMetrics via the event bus.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Protocol

from src.config import S4Settings
from src.events import EventBus, EventType
from src.models import RowingMetrics
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
    RESP_WR,
    ProtocolError,
    build_handshake,
    build_read_command,
    build_reset,
    elapsed_time_to_seconds,
    pace_raw_to_seconds_per_500m,
    parse_response,
    stroke_rate_raw_to_spm,
)

logger = logging.getLogger(__name__)


class AsyncSerial:
    """Wraps a synchronous pyserial Serial object to satisfy the SerialPort protocol."""

    def __init__(self, port: object) -> None:
        self._serial = port

    async def open(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._serial.open)

    async def close(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._serial.close)

    async def readline(self) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._serial.readline)

    async def write(self, data: bytes) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._serial.write, data)

    @property
    def is_open(self) -> bool:
        return self._serial.is_open  # type: ignore[no-any-return]


class SerialPort(Protocol):
    """Minimal serial port interface — allows injection of real or mock serial."""

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def readline(self) -> bytes: ...
    async def write(self, data: bytes) -> None: ...
    @property
    def is_open(self) -> bool: ...


class S4Reader:
    """Async reader for the WaterRower S4 monitor.

    Lifecycle:
        reader = S4Reader(serial_port, event_bus, settings)
        await reader.start()   # runs until stop() is called
        await reader.stop()
    """

    def __init__(
        self,
        serial: SerialPort,
        event_bus: EventBus,
        settings: S4Settings | None = None,
    ) -> None:
        self._serial = serial
        self._bus = event_bus
        self._settings = settings or S4Settings()
        self._running = False
        self._connected = False
        self._task: asyncio.Task[None] | None = None

        # Latest polled values (accumulated across poll cycles)
        self._values: dict[str, int] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the reader loop as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the reader and close the serial port."""
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
        """Main loop: connect → poll → reconnect on failure."""
        while self._running:
            try:
                await self._connect()
                await self._poll_loop()
            except (OSError, ProtocolError) as e:
                logger.warning("S4 connection error: %s", e)
                await self._disconnect()
                if self._running:
                    await asyncio.sleep(self._settings.reconnect_delay_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in S4 reader")
                await self._disconnect()
                if self._running:
                    await asyncio.sleep(self._settings.reconnect_delay_s)

    async def _connect(self) -> None:
        """Open serial port and perform S4 handshake."""
        await self._serial.open()

        # Send USB handshake
        await self._send(build_handshake())

        # Wait for _WR_ response (with timeout)
        response = await self._read_line(timeout=5.0)
        resp_type, _, _ = parse_response(response)
        if resp_type != RESP_WR:
            raise ProtocolError(f"Expected {RESP_WR}, got: {response}")

        # Clear memory
        await self._send(build_reset())

        self._connected = True
        self._values.clear()
        await self._bus.emit(EventType.S4_CONNECTED)
        logger.info("S4 connected")

    async def _disconnect(self) -> None:
        """Close serial port and fire disconnect event."""
        was_connected = self._connected
        self._connected = False
        try:
            if self._serial.is_open:
                await self._serial.close()
        except Exception:
            pass
        if was_connected:
            await self._bus.emit(EventType.S4_DISCONNECTED)
            logger.info("S4 disconnected")

    async def _poll_loop(self) -> None:
        """Poll S4 memory addresses and publish metrics."""
        interval = 1.0 / self._settings.poll_interval_hz

        while self._running and self._connected:
            # Send read commands for all addresses
            for addr in POLL_ADDRESSES:
                cmd = build_read_command(addr)
                await self._send(cmd)

            # Read responses (with timeout for the batch)
            responses_received = 0
            deadline = asyncio.get_event_loop().time() + interval
            while responses_received < len(POLL_ADDRESSES):
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    line = await self._read_line(timeout=remaining)
                except TimeoutError:
                    break

                try:
                    resp_type, addr_hex, value = parse_response(line)
                except ProtocolError as e:
                    logger.debug("Skipping malformed response: %s", e)
                    continue

                if addr_hex is not None and value is not None:
                    self._values[addr_hex] = value
                    responses_received += 1
                # Spontaneous messages (SS, SE, PING) are ignored here

            # Build and publish metrics
            metrics = self._build_metrics()
            await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)

            # Sleep until next poll interval
            sleep_time = deadline - asyncio.get_event_loop().time()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def _build_metrics(self) -> RowingMetrics:
        """Assemble latest polled values into a RowingMetrics model."""
        stroke_rate_raw = self._values.get(ADDR_STROKE_RATE.address)
        stroke_count = self._values.get(ADDR_STROKE_COUNT.address)
        distance_m = self._values.get(ADDR_DISTANCE_M.address)
        pace_raw = self._values.get(ADDR_PACE.address)
        power = self._values.get(ADDR_POWER.address)
        calories = self._values.get(ADDR_CALORIES.address)
        hours = self._values.get(ADDR_ELAPSED_HOURS.address, 0)
        minutes = self._values.get(ADDR_ELAPSED_MINS.address, 0)
        seconds = self._values.get(ADDR_ELAPSED_SECS.address, 0)

        return RowingMetrics(
            timestamp=datetime.now(tz=timezone.utc),
            stroke_rate=stroke_rate_raw_to_spm(stroke_rate_raw) if stroke_rate_raw is not None else None,
            stroke_count=stroke_count,
            distance_m=float(distance_m) if distance_m is not None else None,
            pace_s_per_500m=pace_raw_to_seconds_per_500m(pace_raw) if pace_raw is not None else None,
            power_watts=float(power) if power is not None else None,
            calories=calories,
            elapsed_seconds=elapsed_time_to_seconds(hours, minutes, seconds),
        )

    async def _send(self, command: str) -> None:
        """Send a command string to the S4 (appends line ending)."""
        await self._serial.write(command.encode() + LINE_ENDING)

    async def _read_line(self, timeout: float = 2.0) -> str:
        """Read one line from serial with timeout.

        Raises:
            TimeoutError: if no line received within timeout
            OSError: if serial port is closed/disconnected
        """
        try:
            raw = await asyncio.wait_for(self._serial.readline(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"No response from S4 within {timeout}s")
        return raw.decode("ascii", errors="replace").strip()
