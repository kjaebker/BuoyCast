"""Tests for the data merger."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.events import EventBus, EventType
from src.merger import STALE_THRESHOLD_S, DataMerger
from src.models import RowingMetrics


def _s4_metrics(**kwargs: object) -> RowingMetrics:
    """Create S4-style metrics (has rowing fields, no HR)."""
    defaults = {
        "timestamp": datetime.now(tz=UTC),
        "stroke_rate": 28.0,
        "stroke_count": 100,
        "distance_m": 500.0,
        "pace_s_per_500m": 120.0,
        "power_watts": 150.0,
        "calories": 50,
        "elapsed_seconds": 600,
    }
    defaults.update(kwargs)
    return RowingMetrics(**defaults)


def _hr_metrics(bpm: int = 140, rr: list[int] | None = None) -> RowingMetrics:
    """Create TICKR-style metrics (has HR, no rowing fields)."""
    return RowingMetrics(
        timestamp=datetime.now(tz=UTC),
        heart_rate_bpm=bpm,
        rr_intervals_ms=rr,
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


class TestMergerBasic:
    async def test_s4_plus_hr_merges(self, event_bus: EventBus):
        merger = DataMerger(event_bus)

        # We need a second subscriber to receive merged output.
        # The merger subscribes first, then we subscribe.
        await merger.start()
        q_out = event_bus.subscribe(EventType.MERGED_METRICS)

        # Send HR first
        await event_bus.emit(EventType.METRICS_UPDATE, data=_hr_metrics(bpm=145))
        await asyncio.sleep(0.05)

        # Send S4 metrics — triggers merge + re-publish
        await event_bus.emit(EventType.METRICS_UPDATE, data=_s4_metrics())
        await asyncio.sleep(0.05)

        # The merged output will be in our queue
        # Skip any HR-only events we might receive
        merged = None
        while not q_out.empty():
            event = q_out.get_nowait()
            m: RowingMetrics = event.data
            if isinstance(m, RowingMetrics) and m.stroke_rate is not None:
                merged = m

        assert merged is not None
        assert merged.stroke_rate == 28.0
        assert merged.heart_rate_bpm == 145

        await merger.stop()

    async def test_s4_without_hr(self, event_bus: EventBus):
        merger = DataMerger(event_bus)
        await merger.start()
        q_out = event_bus.subscribe(EventType.MERGED_METRICS)

        # Only S4, no HR ever sent
        await event_bus.emit(EventType.METRICS_UPDATE, data=_s4_metrics())
        await asyncio.sleep(0.05)

        merged = None
        while not q_out.empty():
            event = q_out.get_nowait()
            m = event.data
            if isinstance(m, RowingMetrics) and m.stroke_rate is not None:
                merged = m

        assert merged is not None
        assert merged.stroke_rate == 28.0
        assert merged.heart_rate_bpm is None

        await merger.stop()


class TestMergerStaleHR:
    async def test_stale_hr_set_to_none(self, event_bus: EventBus):
        merger = DataMerger(event_bus)
        await merger.start()
        q_out = event_bus.subscribe(EventType.MERGED_METRICS)

        # Send HR with a timestamp in the past
        old_hr = _hr_metrics(bpm=145)
        await event_bus.emit(EventType.METRICS_UPDATE, data=old_hr)
        await asyncio.sleep(0.05)

        # Simulate time passing beyond stale threshold
        old_time = datetime.now(tz=UTC) - timedelta(seconds=STALE_THRESHOLD_S + 1)
        merger._hr_timestamp = old_time

        # Send S4 metrics
        await event_bus.emit(EventType.METRICS_UPDATE, data=_s4_metrics())
        await asyncio.sleep(0.05)

        merged = None
        while not q_out.empty():
            event = q_out.get_nowait()
            m = event.data
            if isinstance(m, RowingMetrics) and m.stroke_rate is not None:
                merged = m

        assert merged is not None
        assert merged.heart_rate_bpm is None

        await merger.stop()


class TestMergerTickrDisconnected:
    async def test_s4_flows_without_tickr(self, event_bus: EventBus):
        merger = DataMerger(event_bus)
        await merger.start()
        q_out = event_bus.subscribe(EventType.MERGED_METRICS)

        # S4 metrics only, TICKR never connected
        await event_bus.emit(EventType.METRICS_UPDATE, data=_s4_metrics(distance_m=1000.0))
        await asyncio.sleep(0.05)

        merged = None
        while not q_out.empty():
            event = q_out.get_nowait()
            m = event.data
            if isinstance(m, RowingMetrics) and m.stroke_rate is not None:
                merged = m

        assert merged is not None
        assert merged.distance_m == 1000.0
        assert merged.heart_rate_bpm is None
        assert merged.rr_intervals_ms is None

        await merger.stop()


class TestMergerReset:
    async def test_reset_clears_stale_hr(self, event_bus: EventBus):
        merger = DataMerger(event_bus)
        await merger.start()
        q_out = event_bus.subscribe(EventType.MERGED_METRICS)

        # Send HR
        await event_bus.emit(EventType.METRICS_UPDATE, data=_hr_metrics(bpm=145))
        await asyncio.sleep(0.05)

        # Reset — simulating new workout
        merger.reset()

        # S4 metrics after reset should have no HR
        await event_bus.emit(EventType.METRICS_UPDATE, data=_s4_metrics())
        await asyncio.sleep(0.05)

        merged = None
        while not q_out.empty():
            event = q_out.get_nowait()
            m = event.data
            if isinstance(m, RowingMetrics) and m.stroke_rate is not None:
                merged = m

        assert merged is not None
        assert merged.heart_rate_bpm is None

        await merger.stop()
