"""Data merger — combines S4 rowing metrics with TICKR heart rate data.

Subscribes to METRICS_UPDATE events from both sources, maintains latest
values independently, and publishes a unified RowingMetrics on each S4 tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.events import EventBus, EventType
from src.models import RowingMetrics

logger = logging.getLogger(__name__)

# If TICKR data is older than this, treat HR as unavailable.
# 5 seconds gives ample margin for BLE notification jitter (~1Hz)
# while still clearing stale data after a genuine disconnect.
STALE_THRESHOLD_S = 5.0


class DataMerger:
    """Merges S4 and TICKR metrics streams into a unified output.

    The merger distinguishes S4 vs TICKR metrics by checking which fields
    are populated: S4 metrics have stroke_rate/distance/etc., TICKR metrics
    have heart_rate_bpm/rr_intervals.

    On each S4 update, a merged RowingMetrics is published with the latest
    HR data overlaid — unless the HR data is stale (> 3s old).
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Latest data from each source
        self._latest_s4: RowingMetrics | None = None
        self._latest_hr: RowingMetrics | None = None
        self._hr_timestamp: datetime | None = None

    async def start(self) -> None:
        """Start listening for metrics events."""
        self._running = True
        self._queue = self._bus.subscribe(EventType.METRICS_UPDATE)
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the merger."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if hasattr(self, "_queue"):
            self._bus.unsubscribe(EventType.METRICS_UPDATE, self._queue)

    async def _run_loop(self) -> None:
        """Process incoming metrics events."""
        while self._running:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                raise

            metrics: RowingMetrics = event.data
            if not isinstance(metrics, RowingMetrics):
                continue

            if self._is_hr_source(metrics):
                self._latest_hr = metrics
                self._hr_timestamp = metrics.timestamp
            else:
                # S4 source — merge and publish
                self._latest_s4 = metrics
                merged = self._merge()
                await self._bus.emit(EventType.MERGED_METRICS, data=merged)

    def _is_hr_source(self, metrics: RowingMetrics) -> bool:
        """Determine if metrics came from TICKR (HR only) vs S4."""
        # TICKR metrics have HR but no rowing data
        return metrics.heart_rate_bpm is not None and metrics.stroke_rate is None

    def _merge(self) -> RowingMetrics:
        """Merge latest S4 data with latest HR data."""
        s4 = self._latest_s4
        if s4 is None:
            return RowingMetrics(timestamp=datetime.now(tz=timezone.utc))

        # Start with S4 data
        hr_bpm: int | None = None
        rr_intervals: list[int] | None = None

        # Overlay HR if fresh
        if self._latest_hr is not None and self._hr_timestamp is not None:
            age = (datetime.now(tz=timezone.utc) - self._hr_timestamp).total_seconds()
            if age <= STALE_THRESHOLD_S:
                hr_bpm = self._latest_hr.heart_rate_bpm
                rr_intervals = self._latest_hr.rr_intervals_ms

        return RowingMetrics(
            timestamp=datetime.now(tz=timezone.utc),
            stroke_rate=s4.stroke_rate,
            stroke_count=s4.stroke_count,
            distance_m=s4.distance_m,
            pace_s_per_500m=s4.pace_s_per_500m,
            power_watts=s4.power_watts,
            calories=s4.calories,
            elapsed_seconds=s4.elapsed_seconds,
            drive_length_cm=s4.drive_length_cm,
            heart_rate_bpm=hr_bpm,
            rr_intervals_ms=rr_intervals,
        )

    def reset(self) -> None:
        """Clear cached data — call between workouts to prevent stale HR bleed."""
        self._latest_s4 = None
        self._latest_hr = None
        self._hr_timestamp = None
