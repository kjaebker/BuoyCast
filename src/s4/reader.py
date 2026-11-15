"""S4 serial reader — async interface to the WaterRower S4 monitor.

Connects via USB CDC serial, performs handshake, polls memory addresses
at configured intervals, and publishes RowingMetrics via the event bus.

While connected, a single line-reader task owns the serial input: it hands
memory-read responses to the poll request waiting for that address, and
publishes the S4's spontaneous SS/SE (stroke start/end) messages as STROKE
events the moment they arrive, so the dashboard can sync to real strokes.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Protocol

from src.config import S4Settings
from src.events import EventBus, EventType
from src.models import RowingMetrics, StrokeEvent, StrokePhase
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
    POLL_ADDRESSES,
    RESP_IV,
    RESP_SE,
    RESP_SS,
    RESP_WR,
    ProtocolError,
    avg_speed_to_pace,
    bcd_decode,
    build_exit,
    build_handshake,
    build_iv_query,
    build_read_command,
    build_reset,
    elapsed_time_to_seconds,
    parse_response,
    stroke_rate_raw_to_spm,
)

logger = logging.getLogger(__name__)

# How long a poll waits for its memory-read response (the S4 answers in ~6 ms).
RESPONSE_TIMEOUT_S = 0.5


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
        self._consecutive_failures = 0

        # Latest polled values (accumulated across poll cycles)
        self._values: dict[str, int] = {}

        # Rolling power buffer — 20 samples at 4 Hz ≈ 5 seconds
        self._power_buffer: deque[float] = deque(maxlen=20)

        # Poll requests awaiting a response, keyed by 3-hex-char address.
        self._pending: dict[str, asyncio.Future[int]] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    def resume_polling(self) -> None:
        """Allow the run loop to (re)connect after a disconnect_and_pause()."""
        self._paused = False

    async def send_reset(self) -> None:
        """Send RESET to clear all workout counters on the S4.

        Only sends if currently connected. Safe to call even if S4 doesn't respond.
        """
        if self._connected:
            try:
                await self._send(build_reset())
                logger.info("S4 RESET sent — counters cleared")
            except Exception as e:
                logger.warning("Failed to send S4 RESET: %s", e)

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
                self._consecutive_failures += 1
                if self._consecutive_failures == 1:
                    logger.warning("S4 connection error: %s", e)
                else:
                    logger.debug("S4 reconnect attempt %d: %s", self._consecutive_failures, e)
                await self._disconnect()
                if self._running and not self._paused:
                    await asyncio.sleep(self._settings.reconnect_delay_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._consecutive_failures += 1
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

        # Send IV? to confirm S4 identity — required by protocol before IRD polling
        logger.debug("S4 handshake: sending IV?")
        await self._send(build_iv_query())
        for _ in range(5):
            try:
                response = await self._read_line()
                logger.debug("S4 handshake: << %r", response)
                resp_type, _, _ = parse_response(response)
                if resp_type == RESP_IV:
                    logger.info("S4 firmware version: %s", response)
                    break
            except TimeoutError:
                logger.debug("S4 handshake: timeout waiting for IV response")
                break

        self._connected = True
        self._consecutive_failures = 0
        self._values.clear()
        self._power_buffer.clear()
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
        """Poll S4 memory addresses and publish metrics, while a line reader
        task consumes everything the S4 sends (responses and stroke events)."""
        interval = 1.0 / self._settings.poll_interval_hz
        loop = asyncio.get_running_loop()
        first_cycle = True
        line_reader = asyncio.create_task(self._line_reader())

        try:
            while self._running and self._connected and not self._paused:
                cycle_start = loop.time()
                hits = 0

                for addr in POLL_ADDRESSES:
                    if not self._running or not self._connected or self._paused:
                        break
                    if line_reader.done():
                        line_reader.result()  # re-raise the serial error

                    future: asyncio.Future[int] = loop.create_future()
                    self._pending[addr.address] = future
                    cmd = build_read_command(addr)
                    logger.debug("S4 >> %s", cmd)
                    try:
                        await self._send(cmd)
                        self._values[addr.address] = await asyncio.wait_for(
                            future, timeout=RESPONSE_TIMEOUT_S
                        )
                        hits += 1
                    except TimeoutError:
                        logger.debug("S4 timeout waiting for response to %s", cmd)
                    finally:
                        self._pending.pop(addr.address, None)

                if first_cycle:
                    logger.info(
                        "S4 first poll cycle complete: %d/%d responses",
                        hits,
                        len(POLL_ADDRESSES),
                    )
                    first_cycle = False

                metrics = self._build_metrics()
                await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)

                sleep_time = interval - (loop.time() - cycle_start)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        finally:
            line_reader.cancel()
            try:
                await line_reader
            except (asyncio.CancelledError, Exception):
                pass

    async def _line_reader(self) -> None:
        """Read every line from the S4 for the life of the connection.

        Memory-read responses resolve the matching pending poll; SS/SE become
        STROKE events immediately; PING and pulse counts (P02/P03 at ~40 Hz
        while rowing) are ignored. A serial error fails all pending polls so
        the poll loop raises and the run loop reconnects.
        """
        try:
            while True:
                try:
                    line = await self._read_line()
                except TimeoutError:
                    continue  # serial read timeout with nothing to read

                try:
                    resp_type, addr_hex, value = parse_response(line)
                except ProtocolError as e:
                    logger.debug("Skipping malformed response: %s", e)
                    continue

                if resp_type == RESP_SS:
                    await self._emit_stroke(StrokePhase.DRIVE)
                elif resp_type == RESP_SE:
                    await self._emit_stroke(StrokePhase.RECOVERY)
                elif addr_hex is not None and value is not None:
                    future = self._pending.get(addr_hex)
                    if future is not None and not future.done():
                        future.set_result(value)
                    else:
                        logger.debug("S4 unsolicited/stale response: %r", line)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(e)
            raise

    async def _emit_stroke(self, phase: StrokePhase) -> None:
        await self._bus.emit(
            EventType.STROKE,
            data=StrokeEvent(phase=phase, timestamp=datetime.now(tz=UTC)),
        )

    def _build_metrics(self) -> RowingMetrics:
        """Assemble latest polled values into a RowingMetrics model."""
        stroke_rate_raw = self._values.get(ADDR_STROKE_RATE.address)
        stroke_count = self._values.get(ADDR_STROKE_COUNT.address)
        distance_m = self._values.get(ADDR_DISTANCE_M.address)
        avg_speed_cmps = self._values.get(ADDR_AVG_SPEED.address)
        power_raw = self._values.get(ADDR_POWER.address)
        if power_raw is not None and power_raw > 0:
            self._power_buffer.append(float(power_raw))
        power = sum(self._power_buffer) / len(self._power_buffer) if self._power_buffer else None
        calories = self._values.get(ADDR_CALORIES.address)
        # Elapsed time fields use BCD encoding — decode before using
        seconds = bcd_decode(self._values.get(ADDR_ELAPSED_SECS.address, 0))
        minutes = bcd_decode(self._values.get(ADDR_ELAPSED_MINS.address, 0))
        hours = bcd_decode(self._values.get(ADDR_ELAPSED_HOURS.address, 0))

        return RowingMetrics(
            timestamp=datetime.now(tz=UTC),
            stroke_rate=stroke_rate_raw_to_spm(stroke_rate_raw)
            if stroke_rate_raw is not None
            else None,
            stroke_count=stroke_count,
            distance_m=float(distance_m) if distance_m is not None else None,
            pace_s_per_500m=avg_speed_to_pace(avg_speed_cmps)
            if avg_speed_cmps is not None
            else None,
            power_watts=power,
            calories=int(calories / 1000) if calories is not None else None,
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
