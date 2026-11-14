"""E2E tests for the full workout lifecycle.

Wires up EventBus → Merger → SmartDetection → StateMachine → StrokeRecorder → DB.
Simulates S4 + TICKR data by emitting METRICS_UPDATE events, then verifies
the entire chain: state transitions, stroke recording, FIT generation, DB persistence.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from garmin_fit_sdk import Decoder, Stream

from src.events import EventBus, EventType
from src.merger import DataMerger
from src.models import RowingMetrics, WorkoutState
from src.storage.db import Database
from src.storage.queries import get_strokes, get_workout, list_workouts
from src.workout.detection import SmartDetection
from src.workout.fit import generate_fit
from src.workout.recorder import StrokeRecorder
from src.workout.state import WorkoutStateMachine

# --- Fixtures ---


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sm(event_bus):
    return WorkoutStateMachine(event_bus)


@pytest.fixture
def merger(event_bus):
    return DataMerger(event_bus)


@pytest.fixture
def detection(event_bus, sm):
    return SmartDetection(
        event_bus=event_bus,
        state_machine=sm,
        auto_pause_idle_s=2.0,  # Fast for tests
        auto_end_idle_s=10.0,
    )


@pytest.fixture
def recorder(event_bus, sm, db):
    return StrokeRecorder(
        event_bus=event_bus,
        state_machine=sm,
        db=db,
        flush_interval_s=0.05,
    )


async def _start_all(merger, detection, recorder):
    """Start all async components."""
    await merger.start()
    await detection.start()
    await recorder.start()


async def _stop_all(merger, detection, recorder):
    """Stop all async components."""
    await recorder.stop()
    await detection.stop()
    await merger.stop()


def _s4_metrics(
    stroke_rate: float = 28.0,
    distance_m: float = 100.0,
    pace: float = 120.0,
    power: float = 150.0,
    calories: int = 50,
    stroke_count: int = 10,
) -> RowingMetrics:
    """Create S4-style metrics (no HR — merged by DataMerger)."""
    return RowingMetrics(
        timestamp=datetime.now(tz=UTC),
        stroke_rate=stroke_rate,
        stroke_count=stroke_count,
        distance_m=distance_m,
        pace_s_per_500m=pace,
        power_watts=power,
        calories=calories,
    )


def _hr_metrics(bpm: int = 140) -> RowingMetrics:
    """Create TICKR-style metrics (HR only)."""
    return RowingMetrics(
        timestamp=datetime.now(tz=UTC),
        heart_rate_bpm=bpm,
        rr_intervals_ms=[700],
    )


async def _emit_s4(bus: EventBus, metrics: RowingMetrics) -> None:
    """Emit S4 metrics and yield for merger processing."""
    await bus.emit(EventType.METRICS_UPDATE, data=metrics)
    await asyncio.sleep(0.01)


async def _emit_hr(bus: EventBus, metrics: RowingMetrics) -> None:
    """Emit TICKR HR metrics."""
    await bus.emit(EventType.METRICS_UPDATE, data=metrics)
    await asyncio.sleep(0.005)


# --- Full workout flow ---


async def test_full_workout_flow(event_bus, sm, merger, detection, recorder, db, tmp_path):
    """Full flow: start → mock rowing → end → FIT generated → SQLite record complete."""
    await _start_all(merger, detection, recorder)
    try:
        # Start workout
        await sm.start()
        await asyncio.sleep(0.02)

        workout_id = recorder.workout_id
        assert workout_id is not None
        assert sm.state == WorkoutState.ACTIVE

        # Simulate 10 seconds of rowing with HR
        for i in range(10):
            await _emit_hr(event_bus, _hr_metrics(bpm=135 + i))
            await _emit_s4(
                event_bus,
                _s4_metrics(
                    stroke_rate=28.0,
                    distance_m=float(i * 20),
                    stroke_count=i + 1,
                    power=150.0,
                    pace=120.0,
                ),
            )

        # Wait for periodic flush
        await asyncio.sleep(0.1)

        # End workout
        await sm.end()
        await asyncio.sleep(0.05)

        assert sm.state == WorkoutState.SUMMARY

        # Verify DB records
        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.ended_at is not None
        assert workout.total_strokes == 10
        assert workout.total_distance_m == 180.0  # max distance
        assert workout.avg_stroke_rate is not None
        assert workout.avg_heart_rate is not None
        assert workout.max_heart_rate is not None

        # Verify strokes in DB
        strokes = await get_strokes(db, workout_id)
        assert len(strokes) == 10

        # Generate FIT file
        fit_path = generate_fit(workout, strokes, output_dir=tmp_path)
        assert fit_path.exists()

        # Verify FIT file is valid
        stream = Stream.from_file(str(fit_path))
        decoder = Decoder(stream)
        messages, errors = decoder.read()
        assert len(errors) == 0
        assert len(messages.get("record_mesgs", [])) == 10
        assert len(messages.get("session_mesgs", [])) == 1

        session = messages["session_mesgs"][0]
        assert session.get("sport") == "rowing" or session.get("sport") == 15

    finally:
        await _stop_all(merger, detection, recorder)


# --- Auto-pause fires after idle ---


async def test_auto_pause_on_idle(event_bus, sm, merger, detection, recorder):
    """Workout auto-pauses after configured idle seconds."""
    await _start_all(merger, detection, recorder)
    try:
        await sm.start()
        await asyncio.sleep(0.02)
        assert sm.state == WorkoutState.ACTIVE

        with patch("src.workout.detection.time") as mock_time:
            # Row for a bit
            mock_time.monotonic.return_value = 0.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=28.0))
            assert sm.state == WorkoutState.ACTIVE

            # Stop rowing — idle for 2s (our test threshold)
            mock_time.monotonic.return_value = 2.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=0.0))
            await asyncio.sleep(0.01)

            assert sm.state == WorkoutState.PAUSED

    finally:
        await _stop_all(merger, detection, recorder)


# --- Auto-resume on stroke detection ---


async def test_auto_resume_on_strokes(event_bus, sm, merger, detection, recorder):
    """Paused workout auto-resumes when strokes are detected."""
    await _start_all(merger, detection, recorder)
    try:
        await sm.start()
        await asyncio.sleep(0.02)

        with patch("src.workout.detection.time") as mock_time:
            # Row, then idle to trigger pause
            mock_time.monotonic.return_value = 0.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=28.0))

            mock_time.monotonic.return_value = 2.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=0.0))
            await asyncio.sleep(0.01)
            assert sm.state == WorkoutState.PAUSED

            # Resume rowing
            mock_time.monotonic.return_value = 3.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=28.0))
            await asyncio.sleep(0.01)
            assert sm.state == WorkoutState.ACTIVE

    finally:
        await _stop_all(merger, detection, recorder)


# --- Workout survives S4 disconnect mid-row ---


async def test_s4_disconnect_pauses_workout(event_bus, sm, merger, detection, recorder, db):
    """S4 disconnect during active workout triggers pause via event bus."""
    await _start_all(merger, detection, recorder)
    try:
        await sm.start()
        await asyncio.sleep(0.02)

        workout_id = recorder.workout_id

        # Row for a bit
        for i in range(5):
            await _emit_s4(
                event_bus,
                _s4_metrics(
                    stroke_rate=28.0,
                    distance_m=float(i * 20),
                ),
            )

        assert sm.state == WorkoutState.ACTIVE
        assert recorder.total_recorded == 5

        # Simulate S4 disconnect — the real S4Reader publishes this event
        await event_bus.emit(EventType.S4_DISCONNECTED)
        # The state machine should be paused by external handling
        # (In production, the web server or main.py would call sm.pause())
        # For this test, simulate what main.py would do:
        await sm.pause()
        await asyncio.sleep(0.01)

        assert sm.state == WorkoutState.PAUSED

        # S4 reconnects — SmartDetection auto-resumes on stroke detection
        await _emit_s4(event_bus, _s4_metrics(stroke_rate=28.0, distance_m=120.0))
        await asyncio.sleep(0.01)
        assert sm.state == WorkoutState.ACTIVE

        # More rowing after reconnect
        for i in range(3):
            await _emit_s4(
                event_bus,
                _s4_metrics(
                    stroke_rate=28.0,
                    distance_m=float(140 + i * 20),
                ),
            )

        # End workout
        await sm.end()
        await asyncio.sleep(0.05)

        # Verify workout was saved
        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.ended_at is not None
        # Should have strokes from before and after disconnect
        assert workout.total_strokes >= 8  # 5 before + 3 after

    finally:
        await _stop_all(merger, detection, recorder)


# --- Multiple workouts in one session ---


async def test_multiple_workouts_in_session(event_bus, sm, merger, detection, recorder, db):
    """Can complete multiple workouts without restarting components."""
    await _start_all(merger, detection, recorder)
    try:
        # First workout
        await sm.start()
        await asyncio.sleep(0.02)
        first_id = recorder.workout_id

        for i in range(3):
            await _emit_s4(event_bus, _s4_metrics(distance_m=float(i * 10)))
        await sm.end()
        await asyncio.sleep(0.05)

        await sm.reset()

        # Second workout
        await sm.start()
        await asyncio.sleep(0.02)
        second_id = recorder.workout_id

        for i in range(5):
            await _emit_s4(event_bus, _s4_metrics(distance_m=float(i * 10)))
        await sm.end()
        await asyncio.sleep(0.05)

        # Verify both workouts in DB
        assert first_id != second_id
        workouts = await list_workouts(db)
        assert len(workouts) == 2

        w1 = await get_workout(db, first_id)
        w2 = await get_workout(db, second_id)
        assert w1 is not None and w1.total_strokes == 3
        assert w2 is not None and w2.total_strokes == 5

    finally:
        await _stop_all(merger, detection, recorder)


# --- Idle warning event fires ---


async def test_idle_warning_fires(event_bus, sm, merger, detection, recorder):
    """IDLE_WARNING event fires after extended idle period."""
    await _start_all(merger, detection, recorder)
    warning_q = event_bus.subscribe(EventType.IDLE_WARNING)

    try:
        await sm.start()
        await asyncio.sleep(0.02)

        with patch("src.workout.detection.time") as mock_time:
            # Row briefly
            mock_time.monotonic.return_value = 0.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=28.0))

            # Auto-pause at 2s
            mock_time.monotonic.return_value = 2.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=0.0))
            await asyncio.sleep(0.01)
            assert sm.state == WorkoutState.PAUSED

            # Idle warning at 10s
            mock_time.monotonic.return_value = 10.0
            await _emit_s4(event_bus, _s4_metrics(stroke_rate=0.0))
            await asyncio.sleep(0.01)

            assert not warning_q.empty()
            event = warning_q.get_nowait()
            assert event.type == EventType.IDLE_WARNING

    finally:
        await _stop_all(merger, detection, recorder)
