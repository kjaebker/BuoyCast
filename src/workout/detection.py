"""Smart workout detection — auto-pause on idle, auto-resume on rowing.

Subscribes to MERGED_METRICS events, tracks time since last non-zero stroke
rate, and fires state machine transitions accordingly.
"""

from __future__ import annotations

import asyncio
import logging
import time

from src.events import EventBus, EventType
from src.models import RowingMetrics, WorkoutState
from src.workout.state import WorkoutStateMachine

logger = logging.getLogger(__name__)


class SmartDetection:
    """Monitors merged metrics for idle/rowing detection.

    - When ACTIVE and no strokes for `auto_pause_idle_s` → calls on_idle_detected()
    - When PAUSED and strokes detected → calls on_rowing_detected()
    - When idle for `auto_end_idle_s` → publishes IDLE_WARNING (does not auto-end)
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_machine: WorkoutStateMachine,
        auto_pause_idle_s: float = 30.0,
        auto_end_idle_s: float = 300.0,
    ) -> None:
        self._bus = event_bus
        self._sm = state_machine
        self._auto_pause_idle_s = auto_pause_idle_s
        self._auto_end_idle_s = auto_end_idle_s

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_stroke_time: float | None = None
        self._idle_warning_sent = False

    @property
    def last_stroke_time(self) -> float | None:
        """Monotonic timestamp of last detected stroke activity."""
        return self._last_stroke_time

    @property
    def idle_warning_sent(self) -> bool:
        return self._idle_warning_sent

    async def start(self) -> None:
        """Start listening for merged metrics."""
        self._running = True
        self._queue = self._bus.subscribe(EventType.MERGED_METRICS)
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop detection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if hasattr(self, "_queue"):
            self._bus.unsubscribe(EventType.MERGED_METRICS, self._queue)

    def reset(self) -> None:
        """Reset detection state — call on workout start/end."""
        self._last_stroke_time = None
        self._idle_warning_sent = False

    async def _run_loop(self) -> None:
        """Process merged metrics and detect idle/rowing."""
        while self._running:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                raise

            metrics = event.data
            if not isinstance(metrics, RowingMetrics):
                continue

            await self._process(metrics)

    async def _process(self, metrics: RowingMetrics) -> None:
        """Evaluate a single metrics update for idle/rowing transitions."""
        now = time.monotonic()
        has_strokes = metrics.stroke_rate is not None and metrics.stroke_rate > 0

        if has_strokes:
            self._last_stroke_time = now
            self._idle_warning_sent = False

            # Auto-resume if paused
            if self._sm.state == WorkoutState.PAUSED:
                logger.info("Rowing detected — auto-resuming workout")
                await self._sm.on_rowing_detected()
            return

        # No strokes — check for idle conditions
        if self._last_stroke_time is None:
            # No strokes seen yet in this workout
            return

        idle_seconds = now - self._last_stroke_time

        # Auto-pause after auto_pause_idle_s
        if self._sm.state == WorkoutState.ACTIVE and idle_seconds >= self._auto_pause_idle_s:
            logger.info(
                "No strokes for %.0fs — auto-pausing workout",
                idle_seconds,
            )
            await self._sm.on_idle_detected()

        # Idle warning after auto_end_idle_s (does not auto-end)
        if not self._idle_warning_sent and idle_seconds >= self._auto_end_idle_s:
            self._idle_warning_sent = True
            logger.warning(
                "No strokes for %.0fs — sending idle warning",
                idle_seconds,
            )
            await self._bus.emit(
                EventType.IDLE_WARNING,
                data={"idle_seconds": idle_seconds},
            )
