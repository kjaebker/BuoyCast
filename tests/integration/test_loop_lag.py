"""Event-loop lag test — verifies no blocking calls under concurrent load.

Methodology:
  A probe coroutine yields with asyncio.sleep(0) in a tight loop and records
  how long each yield actually takes.  A blocking call anywhere on the loop
  (file I/O, CPU spin, time.sleep, etc.) shows up as a latency spike.

Load scenario:
  - S4Reader publishing METRICS_UPDATE at 10 Hz via MockSerial
  - TickrReader publishing HR_RECEIVED at 10 Hz via MockBLEClient
  - Merger consuming both streams and re-publishing MERGED_METRICS
  - Two event-bus subscribers draining MERGED_METRICS (simulates web server
    and recorder both listening)

Thresholds:
  - p95 lag  < 20 ms   (well within a 1 Hz BLE update budget)
  - max lag  < 150 ms  (Windows timer resolution makes exact guarantees hard;
                        real blocking is typically > 500 ms)

The test runs for 2 seconds so it completes quickly on CI without needing
hardware.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, datetime

import pytest

from src.ble.tickr import TickrReader
from src.config import S4Settings
from src.events import EventBus, EventType
from src.merger import DataMerger
from src.models import RowingMetrics
from src.s4.reader import S4Reader
from tests.conftest import MockBLEClient, MockSerial

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _probe_loop(duration_s: float, samples: list[float]) -> None:
    """Yield continuously and record each yield latency in milliseconds."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + duration_s
    while loop.time() < deadline:
        t0 = loop.time()
        await asyncio.sleep(0)
        samples.append((loop.time() - t0) * 1000)


async def _drain(queue: asyncio.Queue, duration_s: float) -> int:
    """Drain a queue for `duration_s` seconds; return number of items consumed."""
    count = 0
    deadline = asyncio.get_event_loop().time() + duration_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            queue.get_nowait()
            count += 1
        except asyncio.QueueEmpty:
            await asyncio.sleep(0)
    return count


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fast_serial() -> MockSerial:
    ms = MockSerial()
    ms.set_steady_state(stroke_rate_spm=28, distance_m=500, power_watts=150)
    return ms


@pytest.fixture
def fast_ble() -> MockBLEClient:
    ble = MockBLEClient()
    ble.set_hr(145, [690])
    ble.set_notify_interval(0.05)  # 20 Hz
    return ble


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestEventLoopLag:
    async def test_no_blocking_calls_under_load(
        self, fast_serial: MockSerial, fast_ble: MockBLEClient
    ) -> None:
        """Loop lag stays within acceptable bounds while all components run."""
        DURATION = 2.0  # seconds

        bus = EventBus()
        merger = DataMerger(bus)

        # Two consumers simulate web server + recorder both draining events
        consumer_q1 = bus.subscribe(EventType.MERGED_METRICS)
        consumer_q2 = bus.subscribe(EventType.MERGED_METRICS)

        s4_settings = S4Settings(poll_interval_hz=10.0, reconnect_delay_s=1)
        s4_reader = S4Reader(fast_serial, bus, settings=s4_settings)

        tickr_reader = TickrReader(
            ble_client=fast_ble,
            event_bus=bus,
            backoff_base_s=0.01,
            backoff_max_s=0.05,
            poll_interval_s=0.05,
        )

        lag_samples: list[float] = []

        async def run_s4():
            task = asyncio.create_task(s4_reader.start())
            await asyncio.sleep(DURATION)
            await s4_reader.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        async def run_tickr():
            task = asyncio.create_task(tickr_reader.start())
            await asyncio.sleep(DURATION)
            await tickr_reader.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        async def run_merger():
            task = asyncio.create_task(merger.start())
            await asyncio.sleep(DURATION)
            await merger.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Run everything concurrently
        await asyncio.gather(
            run_s4(),
            run_tickr(),
            run_merger(),
            _drain(consumer_q1, DURATION),
            _drain(consumer_q2, DURATION),
            _probe_loop(DURATION, lag_samples),
        )

        assert len(lag_samples) > 100, (
            f"Too few samples ({len(lag_samples)}) — probe loop may be blocked"
        )

        p95 = statistics.quantiles(lag_samples, n=20)[18]  # 95th percentile
        max_lag = max(lag_samples)
        mean_lag = statistics.mean(lag_samples)

        print(
            f"\nLoop lag — mean: {mean_lag:.2f}ms  "
            f"p95: {p95:.2f}ms  max: {max_lag:.2f}ms  "
            f"n={len(lag_samples)}"
        )

        assert p95 < 20.0, (
            f"p95 loop lag {p95:.1f}ms exceeds 20ms threshold — "
            "likely a blocking call in a hot path"
        )
        assert max_lag < 150.0, (
            f"Max loop lag {max_lag:.1f}ms exceeds 150ms threshold — "
            "likely a blocking call (time.sleep / sync I/O)"
        )

    async def test_high_frequency_event_bus_no_lag(self) -> None:
        """Event bus alone at high throughput does not spike the loop."""
        DURATION = 1.0
        bus = EventBus()
        q = bus.subscribe(EventType.MERGED_METRICS)
        lag_samples: list[float] = []

        async def emit_metrics():
            deadline = asyncio.get_event_loop().time() + DURATION
            count = 0
            while asyncio.get_event_loop().time() < deadline:
                await bus.emit(
                    EventType.MERGED_METRICS,
                    data=RowingMetrics(
                        timestamp=datetime.now(tz=UTC),
                        stroke_rate=28.0,
                        distance_m=float(count),
                    ),
                )
                count += 1
                await asyncio.sleep(0)

        await asyncio.gather(
            emit_metrics(),
            _drain(q, DURATION),
            _probe_loop(DURATION, lag_samples),
        )

        assert len(lag_samples) > 50
        p95 = statistics.quantiles(lag_samples, n=20)[18]
        assert p95 < 10.0, f"Event bus p95 lag {p95:.1f}ms — event bus itself is causing contention"
