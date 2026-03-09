"""Unit tests for WorkoutStateMachine — all valid/invalid transitions, timestamps, events."""

import pytest

from src.events import EventBus, EventType
from src.models import WorkoutState
from src.workout.state import InvalidTransitionError, WorkoutStateMachine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sm(event_bus):
    return WorkoutStateMachine(event_bus)


# --- Valid transitions ---


async def test_start_from_idle(sm):
    assert sm.state == WorkoutState.IDLE
    result = await sm.start()
    assert result == WorkoutState.ACTIVE
    assert sm.state == WorkoutState.ACTIVE


async def test_pause_from_active(sm):
    await sm.start()
    result = await sm.pause()
    assert result == WorkoutState.PAUSED
    assert sm.state == WorkoutState.PAUSED


async def test_resume_from_paused(sm):
    await sm.start()
    await sm.pause()
    result = await sm.resume()
    assert result == WorkoutState.ACTIVE
    assert sm.state == WorkoutState.ACTIVE


async def test_end_from_active(sm):
    await sm.start()
    result = await sm.end()
    assert result == WorkoutState.SUMMARY
    assert sm.state == WorkoutState.SUMMARY


async def test_end_from_paused(sm):
    await sm.start()
    await sm.pause()
    result = await sm.end()
    assert result == WorkoutState.SUMMARY
    assert sm.state == WorkoutState.SUMMARY


async def test_reset_from_summary(sm):
    await sm.start()
    await sm.end()
    result = await sm.reset()
    assert result == WorkoutState.IDLE
    assert sm.state == WorkoutState.IDLE


async def test_full_lifecycle(sm):
    """IDLE -> ACTIVE -> PAUSED -> ACTIVE -> SUMMARY -> IDLE."""
    assert sm.state == WorkoutState.IDLE
    await sm.start()
    assert sm.state == WorkoutState.ACTIVE
    await sm.pause()
    assert sm.state == WorkoutState.PAUSED
    await sm.resume()
    assert sm.state == WorkoutState.ACTIVE
    await sm.end()
    assert sm.state == WorkoutState.SUMMARY
    await sm.reset()
    assert sm.state == WorkoutState.IDLE


# --- Invalid transitions ---


@pytest.mark.parametrize(
    "action",
    ["pause", "resume", "end", "reset"],
)
async def test_invalid_from_idle(sm, action):
    with pytest.raises(InvalidTransitionError) as exc_info:
        await getattr(sm, action)()
    assert exc_info.value.current == WorkoutState.IDLE
    assert exc_info.value.action == action


@pytest.mark.parametrize("action", ["start", "resume", "reset"])
async def test_invalid_from_active(sm, action):
    await sm.start()
    with pytest.raises(InvalidTransitionError) as exc_info:
        await getattr(sm, action)()
    assert exc_info.value.current == WorkoutState.ACTIVE


@pytest.mark.parametrize("action", ["start", "pause", "reset"])
async def test_invalid_from_paused(sm, action):
    await sm.start()
    await sm.pause()
    with pytest.raises(InvalidTransitionError) as exc_info:
        await getattr(sm, action)()
    assert exc_info.value.current == WorkoutState.PAUSED


@pytest.mark.parametrize("action", ["start", "pause", "resume", "end"])
async def test_invalid_from_summary(sm, action):
    await sm.start()
    await sm.end()
    with pytest.raises(InvalidTransitionError) as exc_info:
        await getattr(sm, action)()
    assert exc_info.value.current == WorkoutState.SUMMARY


# --- Timestamps ---


async def test_started_at_set_on_start(sm):
    assert sm.started_at is None
    await sm.start()
    assert sm.started_at is not None


async def test_ended_at_set_on_end(sm):
    assert sm.ended_at is None
    await sm.start()
    assert sm.ended_at is None
    await sm.end()
    assert sm.ended_at is not None


async def test_ended_at_cleared_on_reset(sm):
    await sm.start()
    await sm.end()
    assert sm.ended_at is not None
    await sm.reset()
    assert sm.started_at is None
    assert sm.ended_at is None


async def test_started_at_cleared_on_reset(sm):
    await sm.start()
    await sm.end()
    await sm.reset()
    assert sm.started_at is None


# --- Event publishing ---


async def test_start_publishes_workout_started(event_bus, sm):
    q = event_bus.subscribe(EventType.WORKOUT_STARTED)
    await sm.start()
    event = q.get_nowait()
    assert event.type == EventType.WORKOUT_STARTED
    assert event.data["new_state"] == "ACTIVE"
    assert event.data["old_state"] == "IDLE"


async def test_pause_publishes_workout_paused(event_bus, sm):
    await sm.start()
    q = event_bus.subscribe(EventType.WORKOUT_PAUSED)
    await sm.pause()
    event = q.get_nowait()
    assert event.type == EventType.WORKOUT_PAUSED
    assert event.data["new_state"] == "PAUSED"


async def test_resume_publishes_workout_resumed(event_bus, sm):
    await sm.start()
    await sm.pause()
    q = event_bus.subscribe(EventType.WORKOUT_RESUMED)
    await sm.resume()
    event = q.get_nowait()
    assert event.type == EventType.WORKOUT_RESUMED
    assert event.data["new_state"] == "ACTIVE"


async def test_end_publishes_workout_ended(event_bus, sm):
    await sm.start()
    q = event_bus.subscribe(EventType.WORKOUT_ENDED)
    await sm.end()
    event = q.get_nowait()
    assert event.type == EventType.WORKOUT_ENDED
    assert event.data["new_state"] == "SUMMARY"
    assert event.data["ended_at"] is not None


async def test_all_events_published_in_full_lifecycle(event_bus, sm):
    """Subscribe to all workout events and verify the full sequence."""
    started_q = event_bus.subscribe(EventType.WORKOUT_STARTED)
    paused_q = event_bus.subscribe(EventType.WORKOUT_PAUSED)
    resumed_q = event_bus.subscribe(EventType.WORKOUT_RESUMED)
    ended_q = event_bus.subscribe(EventType.WORKOUT_ENDED)

    await sm.start()
    await sm.pause()
    await sm.resume()
    await sm.end()

    assert started_q.get_nowait().type == EventType.WORKOUT_STARTED
    assert paused_q.get_nowait().type == EventType.WORKOUT_PAUSED
    assert resumed_q.get_nowait().type == EventType.WORKOUT_RESUMED
    assert ended_q.get_nowait().type == EventType.WORKOUT_ENDED


# --- Smart detection ---


async def test_on_idle_detected_pauses_when_active(sm):
    await sm.start()
    result = await sm.on_idle_detected()
    assert result == WorkoutState.PAUSED
    assert sm.state == WorkoutState.PAUSED


async def test_on_idle_detected_noop_when_not_active(sm):
    result = await sm.on_idle_detected()
    assert result is None
    assert sm.state == WorkoutState.IDLE


async def test_on_idle_detected_noop_when_paused(sm):
    await sm.start()
    await sm.pause()
    result = await sm.on_idle_detected()
    assert result is None
    assert sm.state == WorkoutState.PAUSED


async def test_on_rowing_detected_resumes_when_paused(sm):
    await sm.start()
    await sm.pause()
    result = await sm.on_rowing_detected()
    assert result == WorkoutState.ACTIVE
    assert sm.state == WorkoutState.ACTIVE


async def test_on_rowing_detected_noop_when_active(sm):
    await sm.start()
    result = await sm.on_rowing_detected()
    assert result is None
    assert sm.state == WorkoutState.ACTIVE


async def test_on_rowing_detected_noop_when_idle(sm):
    result = await sm.on_rowing_detected()
    assert result is None
    assert sm.state == WorkoutState.IDLE


async def test_smart_detection_publishes_events(event_bus, sm):
    """Smart detection triggers should publish the same events as manual actions."""
    paused_q = event_bus.subscribe(EventType.WORKOUT_PAUSED)
    resumed_q = event_bus.subscribe(EventType.WORKOUT_RESUMED)

    await sm.start()
    await sm.on_idle_detected()
    assert paused_q.get_nowait().type == EventType.WORKOUT_PAUSED

    await sm.on_rowing_detected()
    assert resumed_q.get_nowait().type == EventType.WORKOUT_RESUMED
