"""BuoyCast hardware simulators — emit realistic rowing metrics without physical hardware.

Used for local development and testing via the --simulate CLI flag.

Generates a workout with three phases:
  - Warmup  (0–1 min):  stroke rate 18–20 SPM, HR 95→120 BPM
  - Effort  (1–10 min): stroke rate 20–24 SPM, HR 120→155 BPM with undulation
  - Cooldown (10–12 min): stroke rate dropping, HR recovering
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from datetime import UTC, datetime

from src.events import EventBus, EventType
from src.models import RowingMetrics, StrokeEvent, StrokePhase

logger = logging.getLogger(__name__)


class SimulatedS4Reader:
    """Simulates a WaterRower S4 monitor by emitting synthetic RowingMetrics.

    Implements the same public interface as S4Reader so it can be dropped in as
    a replacement — resume_polling(), disconnect_and_pause(), send_reset(), and
    the connected/paused properties are all honoured.
    """

    def __init__(self, event_bus: EventBus, poll_interval_s: float = 1.0) -> None:
        self._bus = event_bus
        self._poll_interval_s = poll_interval_s
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._connected = False
        self._paused = False
        self._elapsed_s: float = 0.0
        self._distance_m: float = 0.0
        self._stroke_count: int = 0
        self._partial_stroke: float = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    def resume_polling(self) -> None:
        self._paused = False

    async def send_reset(self) -> None:
        self._elapsed_s = 0.0
        self._distance_m = 0.0
        self._stroke_count = 0
        self._partial_stroke = 0.0
        logger.info("SimulatedS4: counters reset")

    async def disconnect_and_pause(self) -> None:
        self._paused = True
        await self._do_disconnect()

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self._stroke_task = asyncio.create_task(self._stroke_loop())
        logger.info("SimulatedS4: started")

    async def stop(self) -> None:
        self._running = False
        stroke_task = getattr(self, "_stroke_task", None)
        if stroke_task:
            stroke_task.cancel()
            try:
                await stroke_task
            except asyncio.CancelledError:
                pass
            self._stroke_task = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._do_disconnect()

    async def _do_disconnect(self) -> None:
        if self._connected:
            self._connected = False
            await self._bus.emit(EventType.S4_DISCONNECTED)
            logger.info("SimulatedS4: disconnected")

    async def _run_loop(self) -> None:
        # Simulate brief USB handshake delay
        await asyncio.sleep(0.5)
        self._connected = True
        await self._bus.emit(EventType.S4_CONNECTED)
        logger.info("SimulatedS4: connected (simulation mode)")

        while self._running:
            if self._paused:
                await asyncio.sleep(0.5)
                continue

            metrics = self._build_metrics()
            await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)

            await asyncio.sleep(self._poll_interval_s)
            self._elapsed_s += self._poll_interval_s

        await self._do_disconnect()

    async def _stroke_loop(self) -> None:
        """Emit SS/SE stroke events like the real S4, at the simulated rate."""
        while self._running:
            if self._paused or not self._connected:
                await asyncio.sleep(0.2)
                continue
            rate, _ = self._phase_metrics(self._elapsed_s)
            period = 60.0 / max(rate, 10.0)
            drive = max(0.6, min(period * 0.45, random.gauss(1.0, 0.05)))
            await self._bus.emit(
                EventType.STROKE,
                data=StrokeEvent(phase=StrokePhase.DRIVE, timestamp=datetime.now(tz=UTC)),
            )
            await asyncio.sleep(drive)
            await self._bus.emit(
                EventType.STROKE,
                data=StrokeEvent(phase=StrokePhase.RECOVERY, timestamp=datetime.now(tz=UTC)),
            )
            await asyncio.sleep(max(0.2, period - drive + random.gauss(0, 0.04)))

    def _build_metrics(self) -> RowingMetrics:
        t = self._elapsed_s
        stroke_rate, pace_s_per_500m = self._phase_metrics(t)

        # Add natural noise
        stroke_rate = max(14.0, stroke_rate + random.gauss(0, 0.4))
        pace_s_per_500m = max(90.0, pace_s_per_500m + random.gauss(0, 1.5))

        speed_mps = 500.0 / pace_s_per_500m

        # Accumulate distance
        self._distance_m += speed_mps * self._poll_interval_s

        # Accumulate stroke count (fractional strokes)
        self._partial_stroke += stroke_rate / 60.0 * self._poll_interval_s
        new_strokes = int(self._partial_stroke)
        self._stroke_count += new_strokes
        self._partial_stroke -= new_strokes

        # Power via simplified drag equation (P ∝ v³)
        # At 2:00/500m (4.167 m/s) → ~200 W
        ref_speed = 500.0 / 120.0
        power_watts = max(0.0, 200.0 * (speed_mps / ref_speed) ** 3 + random.gauss(0, 4.0))

        # Calories: rough estimate (≈4 kcal/min at moderate effort)
        calories = int(t * 0.067)

        return RowingMetrics(
            timestamp=datetime.now(tz=UTC),
            stroke_rate=round(stroke_rate, 1),
            stroke_count=self._stroke_count,
            distance_m=round(self._distance_m, 1),
            pace_s_per_500m=round(pace_s_per_500m, 1),
            power_watts=round(power_watts, 1),
            calories=calories,
            elapsed_seconds=int(self._elapsed_s),
        )

    def _phase_metrics(self, t: float) -> tuple[float, float]:
        """Return (stroke_rate_spm, pace_s_per_500m) for the current phase."""
        if t < 60:
            # Warmup: ramp from 18 → 20 SPM, pace 2:20 → 2:05
            p = t / 60.0
            sr = 18.0 + p * 2.0
            pace = 140.0 - p * 15.0
        elif t < 600:
            # Main effort: 22 SPM with sinusoidal undulation, pace ~1:58–2:05
            p = (t - 60) / 540.0
            sr = 22.0 + math.sin(p * math.pi * 5) * 1.5
            pace = 118.0 + math.sin(p * math.pi * 3) * 5.0
        elif t < 720:
            # Cooldown: ramp down from 20 → 16 SPM, pace slowing
            p = (t - 600) / 120.0
            sr = 20.0 - p * 4.0
            pace = 125.0 + p * 25.0
        else:
            # Light ongoing rowing
            sr = 16.0 + math.sin(t * 0.08) * 0.8
            pace = 150.0 + math.sin(t * 0.05) * 5.0
        return sr, pace


class SimulatedHRReader:
    """Simulates a Wahoo TICKR by emitting synthetic heart rate metrics.

    Implements the same public interface as TickrReader — pause_reading(),
    resume_reading(), connected/paused properties.
    """

    def __init__(self, event_bus: EventBus, poll_interval_s: float = 1.0) -> None:
        self._bus = event_bus
        self._poll_interval_s = poll_interval_s
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._connected = False
        self._paused = False
        self._elapsed_s: float = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    async def pause_reading(self) -> None:
        self._paused = True
        await self._do_disconnect()
        logger.info("SimulatedHR: paused")

    async def resume_reading(self) -> None:
        self._paused = False
        logger.info("SimulatedHR: resumed")

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("SimulatedHR: started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._do_disconnect()

    async def _do_disconnect(self) -> None:
        if self._connected:
            self._connected = False
            await self._bus.emit(EventType.TICKR_DISCONNECTED)
            logger.info("SimulatedHR: disconnected")

    async def _run_loop(self) -> None:
        # Slight delay so HR connects after S4
        await asyncio.sleep(0.8)
        self._connected = True
        await self._bus.emit(EventType.TICKR_CONNECTED)
        logger.info("SimulatedHR: connected (simulation mode)")

        while self._running:
            if self._paused:
                await asyncio.sleep(0.5)
                continue

            metrics = self._build_metrics()
            await self._bus.emit(EventType.METRICS_UPDATE, data=metrics)

            await asyncio.sleep(self._poll_interval_s)
            self._elapsed_s += self._poll_interval_s

        await self._do_disconnect()

    def _build_metrics(self) -> RowingMetrics:
        t = self._elapsed_s

        # HR curve: warmup → build → steady state → cooldown
        if t < 60:
            hr = 95.0 + (t / 60.0) * 25.0  # 95 → 120 BPM
        elif t < 300:
            hr = 120.0 + ((t - 60) / 240.0) * 35.0  # 120 → 155 BPM
        elif t < 600:
            hr = 152.0 + math.sin((t - 300) * 0.04) * 5.0  # steady ~147–157 BPM
        elif t < 720:
            hr = 155.0 - ((t - 600) / 120.0) * 25.0  # 155 → 130 BPM
        else:
            hr = max(80.0, 130.0 - ((t - 720) / 300.0) * 30.0)  # gradual recovery

        # Natural HRV noise
        hr = max(60.0, min(200.0, hr + random.gauss(0, 1.2)))
        bpm = round(hr)

        # Generate physiologically plausible RR intervals
        rr_base_ms = round(60000 / bpm)
        rr_intervals = [max(300, min(1500, rr_base_ms + random.randint(-25, 25))) for _ in range(2)]

        return RowingMetrics(
            timestamp=datetime.now(tz=UTC),
            heart_rate_bpm=bpm,
            rr_intervals_ms=rr_intervals,
        )
