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
    build_exit,
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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.open)

    async def close(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.close)

    async def readline(self) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._serial.readline)

    async def write(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.write, data)

    async def flush_input(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.reset_input_buffer)

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
        self._paused = False
        self._task: asyncio.Task[None] | None = None

        # Latest polled values (accumulated across poll cycles)
        self._values: dict[str, int] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    def resume_polling(self) -> None:
        """Allow the run loop to (re)connect after a disconnect_and_pause()."""
        self._paused = False

    async def disconnect_and_pause(self) -> None:
        """Send EXIT to release USB mode, disconnect, and stop auto-reconnecting."""
        self._paused = True
        if self._connected:
            try:
                await self._send(build_exit())
            except Exception:
                pass
        await self._disconnect()

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
            if self._paused:
                await asyncio.sleep(0.5)
                continue
            try:
                await self._connect()
                await self._poll_loop()
            except (OSError, ProtocolError) as e:
                logger.warning("S4 connection error: %s", e)
                await self._disconnect()
                if self._running and not self._paused:
                    await asyncio.sleep(self._settings.reconnect_delay_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in S4 reader")
                await self._disconnect()
                if self._running and not self._paused:
                    await asyncio.sleep(self._settings.reconnect_delay_s)

    async def _connect(self) -> None:
        """Open serial port and perform S4 handshake."""
        await self._serial.open()

        # Flush any stale bytes left in the OS buffer from a previous session
        await self._serial.flush_input()

        # Send USB handshake
        logger.debug("S4 handshake: sending USB")
        await self._send(build_handshake())

        # Wait for _WR_ response — retry for up to ~5s (10 × serial timeout)
        resp_type = None
        for _ in range(10):
            try:
                response = await self._read_line()
            except TimeoutError:
                logger.debug("S4 handshake: timeout waiting for _WR_")
                continue
            logger.debug("S4 handshake: << %r", response)
            resp_type, _, _ = parse_response(response)
            if resp_type == RESP_WR:
                break
        if resp_type != RESP_WR:
            raise ProtocolError("No _WR_ handshake response from S4")

        # RESET primes the S4 memory for IRD polling — required before reads work
        # Brief pause to let the S4 fully enter USB mode before sending RESET
        await asyncio.sleep(0.5)

        logger.debug("S4 handshake: sending RESET")
        await self._send(build_reset())

        # Wait for the S4 to finish processing RESET before IRD polling starts
        await asyncio.sleep(1.0)

        # Drain any messages the S4 sends after RESET before we start polling
        for _ in range(6):
            try:
                line = await self._read_line()
                logger.debug("S4 post-reset: << %r", line)
            except TimeoutError:
                break

        # Probe a range of IRD commands to find what firmware 2.10 accepts
        probe_commands = [
            "IRDS000",   # single byte, very low address
            "IRDS001",
            "IRDS1E3",   # elapsed seconds
            "IRDD1E3",   # same address, double size
            "IRDD057",   # distance meters
            "IRDS140",   # stroke rate area, single
            "IRDD140",   # stroke rate area, double
        ]
        for cmd in probe_commands:
            logger.debug("S4 probe: >> %s", cmd)
            await self._send(cmd)
            for _ in range(3):
                try:
                    line = await self._read_line()
                    logger.debug("S4 probe: << %r (for %s)", line, cmd)
                    if line not in ("ERROR", "PING", "SS", "SE"):
                        break  # got a real response
                except TimeoutError:
                    logger.debug("S4 probe: timeout for %s", cmd)
                    break

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
        """Poll S4 memory addresses and publish metrics.

        Sequential: send one IRD command then read until we get the matching
        IDD response (discarding spontaneous PINGs/SS/SE in between).
        """
        interval = 1.0 / self._settings.poll_interval_hz
        first_cycle = True

        while self._running and self._connected and not self._paused:
            cycle_start = asyncio.get_running_loop().time()
            hits = 0

            for addr in POLL_ADDRESSES:
                if not self._running or not self._connected or self._paused:
                    break

                cmd = build_read_command(addr)
                logger.debug("S4 >> %s", cmd)
                await self._send(cmd)

                # Read until we get the matching IDD response or time out.
                # Up to 5 reads to absorb interleaved PING/SS/SE messages.
                for _ in range(5):
                    try:
                        line = await self._read_line()
                    except TimeoutError:
                        logger.debug("S4 timeout waiting for response to %s", cmd)
                        break
                    except OSError:
                        raise

                    logger.debug("S4 << %r", line)

                    try:
                        _, addr_hex, value = parse_response(line)
                    except ProtocolError as e:
                        logger.debug("Skipping malformed response: %s", e)
                        continue

                    if addr_hex == addr.address and value is not None:
                        self._values[addr_hex] = value
                        hits += 1
                        break
                    elif addr_hex is None:
                        # Spontaneous message (PING, SS, SE) — discard and keep reading
                        continue
                    else:
                        # Stale response for a different address — discard
                        logger.debug("S4 stale response: expected %s got %s", addr.address, addr_hex)

            if first_cycle:
                logger.info("S4 first poll cycle complete: %d/%d responses", hits, len(POLL_ADDRESSES))
                first_cycle = False

            metrics = self._build_metrics()
            await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)

            elapsed = asyncio.get_running_loop().time() - cycle_start
            sleep_time = interval - elapsed
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

    async def _read_line(self) -> str:
        """Read one line from serial.

        Relies on the serial port's own read timeout (set on the Serial object)
        to bound the blocking call — no asyncio.wait_for needed, which avoids
        leaving orphaned executor threads that consume bytes from the buffer.

        Raises:
            TimeoutError: if no line received within the serial port timeout
            OSError: if serial port is closed/disconnected
        """
        try:
            raw = await self._serial.readline()
        except TypeError as e:
            # Port was closed mid-read (fd becomes None); treat as disconnect
            raise OSError(f"Serial port closed during read: {e}") from e
        if not raw:
            raise TimeoutError("No response from S4 (serial timeout)")
        return raw.decode("ascii", errors="replace").strip()
