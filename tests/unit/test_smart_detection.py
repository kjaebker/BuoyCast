"""Unit tests for SmartDetection — idle auto-pause, rowing auto-resume, idle warning."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.events import EventBus, EventType
from src.models import RowingMetrics, WorkoutState
from src.workout.detection import SmartDetection
from src.workout.state import WorkoutStateMachine


def _metrics(stroke_rate: float | None = None) -> RowingMetrics:
    """Create a minimal RowingMetrics for testing."""
    return RowingMetrics(
        timestamp=datetime.now(tz=UTC),
        stroke_rate=stroke_rate,
    )


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sm(event_bus):
    return WorkoutStateMachine(event_bus)


@pytest.fixture
def detection(event_bus, sm):
    return SmartDetection(
        event_bus=event_bus,
        state_machine=sm,
        auto_pause_idle_s=5.0,
        auto_end_idle_s=30.0,
    )


# --- Helper to drive detection without the async loop ---


async def _emit_merged(event_bus: EventBus, metrics: RowingMetrics) -> None:
    """Publish a MERGED_METRICS event."""
    await event_bus.emit(EventType.MERGED_METRICS, data=metrics)


async def _process_directly(detection: SmartDetection, metrics: RowingMetrics) -> None:
    """Call _process directly to avoid async loop complexity in tests."""
    await detection._process(metrics)


# --- Auto-pause on idle ---


async def test_auto_pause_after_idle_seconds(sm, detection):
    """ACTIVE workout auto-pauses after configured idle seconds."""
    await sm.start()

    with patch("src.workout.detection.time") as mock_time:
        # First update: rowing at t=0
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert sm.state == WorkoutState.ACTIVE

        # Update at t=4: still idle but under threshold
        mock_time.monotonic.return_value = 4.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert sm.state == WorkoutState.ACTIVE

        # Update at t=5: idle threshold reached
        mock_time.monotonic.return_value = 5.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert sm.state == WorkoutState.PAUSED


async def test_no_auto_pause_when_not_active(sm, detection):
    """Auto-pause only fires when ACTIVE."""
    # Stay IDLE — should not crash or transition
    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))

        mock_time.monotonic.return_value = 10.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert sm.state == WorkoutState.IDLE


async def test_no_auto_pause_without_prior_strokes(sm, detection):
    """If no strokes have been seen yet, don't auto-pause."""
    await sm.start()

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 100.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert sm.state == WorkoutState.ACTIVE  # No prior stroke → no pause


async def test_null_stroke_rate_treated_as_no_strokes(sm, detection):
    """stroke_rate=None should be treated as no strokes."""
    await sm.start()

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))

        mock_time.monotonic.return_value = 5.0
        await _process_directly(detection, _metrics(stroke_rate=None))
        assert sm.state == WorkoutState.PAUSED


# --- Auto-resume on rowing ---


async def test_auto_resume_when_paused_and_strokes_detected(sm, detection):
    """PAUSED workout auto-resumes when strokes are detected."""
    await sm.start()
    await sm.pause()
    assert sm.state == WorkoutState.PAUSED

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert sm.state == WorkoutState.ACTIVE


async def test_no_auto_resume_when_active(sm, detection):
    """Already ACTIVE — strokes should not cause any transition."""
    await sm.start()

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert sm.state == WorkoutState.ACTIVE


async def test_no_auto_resume_when_idle(sm, detection):
    """IDLE state — strokes should not cause resume."""
    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert sm.state == WorkoutState.IDLE


# --- Idle warning ---


async def test_idle_warning_after_auto_end_idle_s(event_bus, sm, detection):
    """Idle warning fires after auto_end_idle_s of no strokes."""
    await sm.start()
    q = event_bus.subscribe(EventType.IDLE_WARNING)

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))

        # At 29s — no warning yet
        mock_time.monotonic.return_value = 29.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert q.empty()

        # At 30s — warning fires
        mock_time.monotonic.return_value = 30.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert not q.empty()
        event = q.get_nowait()
        assert event.type == EventType.IDLE_WARNING
        assert event.data["idle_seconds"] >= 30.0


async def test_idle_warning_only_sent_once(event_bus, sm, detection):
    """Idle warning should not repeat until strokes resume."""
    await sm.start()
    q = event_bus.subscribe(EventType.IDLE_WARNING)

    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))

        # Trigger warning
        mock_time.monotonic.return_value = 30.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert q.qsize() == 1

        # More idle time — no second warning
        mock_time.monotonic.return_value = 60.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert q.qsize() == 1  # Still just one


async def test_idle_warning_resets_on_rowing(event_bus, sm, detection):
    """After strokes resume, idle warning can fire again."""
    await sm.start()
    q = event_bus.subscribe(EventType.IDLE_WARNING)

    with patch("src.workout.detection.time") as mock_time:
        # Row, then idle to trigger warning
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        mock_time.monotonic.return_value = 30.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert q.qsize() == 1

        # Resume rowing — resets warning flag
        mock_time.monotonic.return_value = 31.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert not detection.idle_warning_sent

        # Idle again — warning can fire again
        mock_time.monotonic.return_value = 61.0
        await _process_directly(detection, _metrics(stroke_rate=0.0))
        assert q.qsize() == 2


# --- Reset ---


async def test_reset_clears_state(detection):
    """reset() clears last_stroke_time and idle_warning_sent."""
    with patch("src.workout.detection.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await _process_directly(detection, _metrics(stroke_rate=28.0))
        assert detection.last_stroke_time is not None

    detection.reset()
    assert detection.last_stroke_time is None
    assert not detection.idle_warning_sent


# --- Integration with event bus loop ---


async def test_detection_via_event_bus(event_bus, sm, detection):
    """Test that SmartDetection processes events from the bus correctly."""
    await sm.start()
    await detection.start()

    try:
        with patch("src.workout.detection.time") as mock_time:
            # Emit rowing metrics
            mock_time.monotonic.return_value = 0.0
            await _emit_merged(event_bus, _metrics(stroke_rate=28.0))
            # Give the loop a chance to process
            await _yield_loop()

            # Emit idle metrics past threshold
            mock_time.monotonic.return_value = 5.0
            await _emit_merged(event_bus, _metrics(stroke_rate=0.0))
            await _yield_loop()

            assert sm.state == WorkoutState.PAUSED
    finally:
        await detection.stop()


async def _yield_loop() -> None:
    """Yield control to let async tasks process."""
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
