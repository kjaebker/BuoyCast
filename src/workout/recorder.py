"""Stroke recorder — buffers metrics during ACTIVE state, flushes to SQLite.

Subscribes to MERGED_METRICS and WORKOUT_STARTED/ENDED events. Only records
strokes while the workout is ACTIVE. Flushes to SQLite every flush_interval_s
seconds, with a final flush + summary stats on workout end.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from datetime import UTC, datetime

from src.events import EventBus, EventType
from src.models import RowingMetrics, StrokeRecord, WorkoutRecord, WorkoutState
from src.storage.db import Database
from src.storage.queries import insert_strokes, insert_workout, update_workout
from src.workout.state import WorkoutStateMachine

logger = logging.getLogger(__name__)


class StrokeRecorder:
    """Records stroke data during active workouts.

    - Subscribes to MERGED_METRICS: appends StrokeRecord to buffer when ACTIVE
    - Periodic flush: writes buffered strokes to SQLite every flush_interval_s
    - On workout start: inserts placeholder WorkoutRecord (so FK works for strokes)
    - On workout end: final flush, compute summary stats, update WorkoutRecord
    """

    def __init__(
        self,
        event_bus: EventBus,
        state_machine: WorkoutStateMachine,
        db: Database,
        flush_interval_s: float = 10.0,
    ) -> None:
        self._bus = event_bus
        self._sm = state_machine
        self._db = db
        self._flush_interval_s = flush_interval_s

        self._running = False
        self._metrics_task: asyncio.Task[None] | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._start_task: asyncio.Task[None] | None = None
        self._end_task: asyncio.Task[None] | None = None

        self._workout_id: str | None = None
        self._buffer: deque[StrokeRecord] = deque()
        self._all_strokes: list[StrokeRecord] = []
        self._last_calories: int | None = None
        self._last_stroke_count: int | None = None
        # Captured at start: the state machine's started_at is cleared on reset,
        # which can land before this recorder handles WORKOUT_ENDED.
        self._started_at: datetime | None = None

    @property
    def workout_id(self) -> str | None:
        return self._workout_id

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def total_recorded(self) -> int:
        """Total strokes recorded (flushed + buffered)."""
        return len(self._all_strokes)

    async def start(self) -> None:
        """Start listening for events."""
        self._running = True
        self._metrics_queue = self._bus.subscribe(EventType.MERGED_METRICS)
        self._started_queue = self._bus.subscribe(EventType.WORKOUT_STARTED)
        self._ended_queue = self._bus.subscribe(EventType.WORKOUT_ENDED)

        self._metrics_task = asyncio.create_task(self._metrics_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._start_task = asyncio.create_task(self._start_loop())
        self._end_task = asyncio.create_task(self._end_loop())

    async def stop(self) -> None:
        """Stop the recorder."""
        self._running = False
        for task in (self._metrics_task, self._flush_task, self._start_task, self._end_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._metrics_task = None
        self._flush_task = None
        self._start_task = None
        self._end_task = None

        for et, attr in [
            (EventType.MERGED_METRICS, "_metrics_queue"),
            (EventType.WORKOUT_STARTED, "_started_queue"),
            (EventType.WORKOUT_ENDED, "_ended_queue"),
        ]:
            if hasattr(self, attr):
                self._bus.unsubscribe(et, getattr(self, attr))

    async def _metrics_loop(self) -> None:
        """Process incoming merged metrics."""
        while self._running:
            try:
                event = await self._metrics_queue.get()
            except asyncio.CancelledError:
                raise

            if self._sm.state != WorkoutState.ACTIVE:
                continue
            if self._workout_id is None:
                continue

            metrics = event.data
            if not isinstance(metrics, RowingMetrics):
                continue

            record = StrokeRecord(
                workout_id=self._workout_id,
                ts=metrics.timestamp,
                distance_m=metrics.distance_m or 0.0,
                stroke_rate=metrics.stroke_rate or 0.0,
                power_watts=metrics.power_watts,
                pace_s_per_500m=metrics.pace_s_per_500m,
                heart_rate_bpm=metrics.heart_rate_bpm,
                rr_intervals_ms=metrics.rr_intervals_ms,
            )
            self._buffer.append(record)
            self._all_strokes.append(record)

            # Track latest calories value for summary computation
            if metrics.calories is not None:
                self._last_calories = metrics.calories
            if metrics.stroke_count is not None:
                self._last_stroke_count = metrics.stroke_count

    async def _flush_loop(self) -> None:
        """Periodically flush buffer to SQLite."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval_s)
            except asyncio.CancelledError:
                raise
            await self._flush()

    async def _start_loop(self) -> None:
        """Listen for workout start events."""
        while self._running:
            try:
                await self._started_queue.get()
            except asyncio.CancelledError:
                raise
            await self._on_workout_started()

    async def _end_loop(self) -> None:
        """Listen for workout end events."""
        while self._running:
            try:
                await self._ended_queue.get()
            except asyncio.CancelledError:
                raise
            await self._on_workout_ended()

    async def _flush(self) -> None:
        """Write buffered strokes to SQLite."""
        if not self._buffer:
            return

        strokes = list(self._buffer)
        self._buffer.clear()

        try:
            await insert_strokes(self._db, strokes)
            logger.debug("Flushed %d strokes to SQLite", len(strokes))
        except Exception:
            logger.exception("Failed to flush strokes — re-buffering")
            self._buffer.extendleft(reversed(strokes))

    async def _on_workout_started(self) -> None:
        """Reset state and insert placeholder WorkoutRecord for FK integrity."""
        self._workout_id = uuid.uuid4().hex[:12]
        self._buffer.clear()
        self._all_strokes.clear()
        self._last_calories = None
        self._last_stroke_count = None

        # Insert placeholder so strokes can reference this workout_id
        started_at = self._sm.started_at or datetime.now(tz=UTC)
        self._started_at = started_at
        placeholder = WorkoutRecord(
            id=self._workout_id,
            started_at=started_at,
            ended_at=None,
            total_distance_m=0.0,
            total_strokes=0,
            elapsed_seconds=0,
        )
        try:
            await insert_workout(self._db, placeholder)
        except Exception:
            logger.exception("Failed to insert placeholder workout record")

    async def _on_workout_ended(self) -> None:
        """Final flush + compute summary stats + update WorkoutRecord."""
        if self._workout_id is None:
            return

        # Final flush
        await self._flush()

        # Compute summary and update the existing record
        update_fields = self._compute_summary_fields()
        if update_fields:
            try:
                await update_workout(self._db, self._workout_id, **update_fields)
                logger.info(
                    "Workout %s updated: %.0fm, %d strokes",
                    self._workout_id,
                    update_fields.get("total_distance_m", 0),
                    update_fields.get("total_strokes", 0),
                )
            except Exception:
                logger.exception("Failed to update workout record")

        self._workout_id = None
        self._all_strokes.clear()

    def _compute_summary_fields(self) -> dict:
        """Compute summary stats as a dict for update_workout."""
        started_at = self._started_at or self._sm.started_at
        if self._workout_id is None or started_at is None:
            return {}

        strokes = self._all_strokes
        # Metric samples arrive ~1 Hz, so they are not strokes: use the
        # monitor's (workout-relative) stroke count when it reports one.
        total_strokes = (
            self._last_stroke_count if self._last_stroke_count is not None else len(strokes)
        )

        total_distance = max((s.distance_m for s in strokes), default=0.0)

        ended_at = self._sm.ended_at or datetime.now(tz=UTC)
        elapsed = int((ended_at - started_at).total_seconds())

        rates = [s.stroke_rate for s in strokes if s.stroke_rate > 0]
        avg_stroke_rate = sum(rates) / len(rates) if rates else None

        paces = [
            s.pace_s_per_500m
            for s in strokes
            if s.pace_s_per_500m is not None and s.pace_s_per_500m > 0
        ]
        avg_pace = sum(paces) / len(paces) if paces else None

        powers = [s.power_watts for s in strokes if s.power_watts is not None and s.power_watts > 0]
        avg_power = sum(powers) / len(powers) if powers else None

        hr_values = [s.heart_rate_bpm for s in strokes if s.heart_rate_bpm is not None]
        avg_hr = int(sum(hr_values) / len(hr_values)) if hr_values else None
        max_hr = max(hr_values) if hr_values else None

        return {
            "ended_at": ended_at,
            "total_distance_m": total_distance,
            "total_strokes": total_strokes,
            "elapsed_seconds": elapsed,
            "avg_pace_s_per_500m": avg_pace,
            "avg_stroke_rate": avg_stroke_rate,
            "avg_power_watts": avg_power,
            "avg_heart_rate": avg_hr,
            "max_heart_rate": max_hr,
            "calories": self._last_calories or 0,
        }

    def handle_workout_started(self) -> str:
        """Synchronous init for direct invocation (without event bus).

        Returns the new workout_id. Note: does NOT insert into DB.
        Use the event-driven _on_workout_started for full DB integration.
        """
        self._workout_id = uuid.uuid4().hex[:12]
        self._buffer.clear()
        self._all_strokes.clear()
        return self._workout_id
