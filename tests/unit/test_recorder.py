"""Unit tests for StrokeRecorder — ACTIVE-only recording, flush, summary stats."""

import asyncio
from datetime import UTC, datetime

import pytest

from src.events import EventBus, EventType
from src.models import RowingMetrics
from src.storage.db import Database
from src.storage.queries import get_strokes, get_workout
from src.workout.recorder import StrokeRecorder
from src.workout.state import WorkoutStateMachine


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
def recorder(event_bus, sm, db):
    return StrokeRecorder(
        event_bus=event_bus,
        state_machine=sm,
        db=db,
        flush_interval_s=0.05,  # Fast flush for tests
    )


def _metrics(
    stroke_rate: float = 28.0,
    distance_m: float = 100.0,
    pace: float = 120.0,
    power: float = 150.0,
    hr: int | None = None,
) -> RowingMetrics:
    return RowingMetrics(
        timestamp=datetime.now(tz=UTC),
        stroke_rate=stroke_rate,
        distance_m=distance_m,
        pace_s_per_500m=pace,
        power_watts=power,
        heart_rate_bpm=hr,
    )


async def _emit_and_yield(bus: EventBus, metrics: RowingMetrics) -> None:
    """Emit MERGED_METRICS and yield for processing."""
    await bus.emit(EventType.MERGED_METRICS, data=metrics)
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def _start_workout(sm, recorder):
    """Start a workout and let the recorder process the event."""
    await sm.start()
    # Give start_loop time to process the WORKOUT_STARTED event + DB insert
    await asyncio.sleep(0.02)


async def _end_workout(sm):
    """End a workout and yield for processing."""
    await sm.end()
    # Give end_loop time to process: flush + compute summary + DB update
    await asyncio.sleep(0.02)


# --- Records only during ACTIVE ---


async def test_records_only_when_active(event_bus, sm, recorder):
    """Recorder should only buffer strokes when workout is ACTIVE."""
    await recorder.start()
    try:
        # IDLE — should not record
        await _emit_and_yield(event_bus, _metrics())
        assert recorder.total_recorded == 0

        # Start workout
        await _start_workout(sm, recorder)

        # ACTIVE — should record
        await _emit_and_yield(event_bus, _metrics())
        assert recorder.total_recorded == 1

        # Pause — should not record
        await sm.pause()
        await _emit_and_yield(event_bus, _metrics())
        assert recorder.total_recorded == 1

        # Resume — should record again
        await sm.resume()
        await _emit_and_yield(event_bus, _metrics())
        assert recorder.total_recorded == 2
    finally:
        await recorder.stop()


# --- Buffer flush ---


async def test_buffer_flushes_periodically(event_bus, sm, recorder, db):
    """Buffer should flush to SQLite on the configured interval."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)

        # Record some strokes
        for _ in range(5):
            await _emit_and_yield(event_bus, _metrics())

        assert recorder.buffer_size == 5

        # Wait for flush
        await asyncio.sleep(0.1)

        assert recorder.buffer_size == 0

        # Verify in DB
        strokes = await get_strokes(db, recorder.workout_id)
        assert len(strokes) == 5
    finally:
        await recorder.stop()


# --- Final flush on workout end ---


async def test_final_flush_on_end(event_bus, sm, recorder, db):
    """All buffered strokes should flush when workout ends."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        workout_id = recorder.workout_id
        assert workout_id is not None

        # Record strokes
        for i in range(3):
            await _emit_and_yield(event_bus, _metrics(distance_m=float(i * 10)))

        assert recorder.buffer_size == 3

        # End workout — triggers final flush + summary
        await _end_workout(sm)

        # Strokes should be in DB
        strokes = await get_strokes(db, workout_id)
        assert len(strokes) == 3

        # WorkoutRecord should be updated with summary
        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.total_strokes == 3
        assert workout.ended_at is not None
    finally:
        await recorder.stop()


async def test_workout_saved_emitted_after_summary(event_bus, sm, recorder, db):
    """WORKOUT_SAVED fires once the summary is in SQLite, carrying the workout ID."""
    saved = event_bus.subscribe(EventType.WORKOUT_SAVED)
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        workout_id = recorder.workout_id
        await _emit_and_yield(event_bus, _metrics(distance_m=50.0))
        await _end_workout(sm)

        event = saved.get_nowait()
        assert event.data == workout_id
        workout = await get_workout(db, workout_id)
        assert workout.ended_at is not None
    finally:
        await recorder.stop()


# --- Summary stats computed correctly ---


async def test_summary_stats(event_bus, sm, recorder, db):
    """Summary stats should be computed from recorded strokes."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        workout_id = recorder.workout_id

        # Record strokes with known values
        await _emit_and_yield(
            event_bus,
            _metrics(
                stroke_rate=26.0,
                distance_m=50.0,
                pace=130.0,
                power=140.0,
                hr=140,
            ),
        )
        await _emit_and_yield(
            event_bus,
            _metrics(
                stroke_rate=30.0,
                distance_m=100.0,
                pace=110.0,
                power=160.0,
                hr=160,
            ),
        )

        await _end_workout(sm)

        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.total_strokes == 2
        assert workout.total_distance_m == 100.0  # Max distance
        assert workout.avg_stroke_rate == pytest.approx(28.0)
        assert workout.avg_pace_s_per_500m == pytest.approx(120.0)
        assert workout.avg_power_watts == pytest.approx(150.0)
        assert workout.avg_heart_rate == 150  # (140+160)/2
        assert workout.max_heart_rate == 160
    finally:
        await recorder.stop()


# --- Handles no HR data gracefully ---


async def test_summary_without_hr(event_bus, sm, recorder, db):
    """Summary should handle workouts with no HR data."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        workout_id = recorder.workout_id

        await _emit_and_yield(event_bus, _metrics(hr=None))
        await _emit_and_yield(event_bus, _metrics(hr=None))

        await _end_workout(sm)

        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.avg_heart_rate is None
        assert workout.max_heart_rate is None
    finally:
        await recorder.stop()


# --- Workout ID reset between workouts ---


async def test_workout_id_changes_between_workouts(event_bus, sm, recorder):
    """Each workout should get a new unique ID."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        first_id = recorder.workout_id

        await _end_workout(sm)
        await sm.reset()

        await _start_workout(sm, recorder)
        second_id = recorder.workout_id

        assert first_id is not None
        assert second_id is not None
        assert first_id != second_id
    finally:
        await recorder.stop()


# --- Placeholder workout inserted on start ---


async def test_placeholder_workout_on_start(event_bus, sm, recorder, db):
    """A placeholder WorkoutRecord should be inserted on workout start."""
    await recorder.start()
    try:
        await _start_workout(sm, recorder)
        workout_id = recorder.workout_id

        workout = await get_workout(db, workout_id)
        assert workout is not None
        assert workout.ended_at is None
        assert workout.total_strokes == 0
    finally:
        await recorder.stop()


# --- Direct handle_workout_started ---


async def test_handle_workout_started_directly(recorder):
    """handle_workout_started sets up workout_id and clears state."""
    assert recorder.workout_id is None
    wid = recorder.handle_workout_started()
    assert recorder.workout_id is not None
    assert wid == recorder.workout_id
    assert recorder.buffer_size == 0
    assert recorder.total_recorded == 0


async def test_summary_survives_reset_before_end_is_handled(sm, recorder, db):
    """A fast end->reset must still finalise the workout (no orphaned row)."""
    await recorder.start()
    try:
        await sm.start()
        await asyncio.sleep(0.02)
        workout_id = recorder.workout_id
        await sm.end()
        await sm.reset()  # clears sm.started_at before the recorder runs
        await asyncio.sleep(0.05)
        workout = await get_workout(db, workout_id)
        assert workout is not None and workout.ended_at is not None
    finally:
        await recorder.stop()
