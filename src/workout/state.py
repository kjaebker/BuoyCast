"""Workout state machine with explicit transition guards and event publishing."""

from datetime import datetime, timezone

from src.events import EventBus, EventType
from src.models import WorkoutState


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current: WorkoutState, action: str) -> None:
        self.current = current
        self.action = action
        super().__init__(f"Cannot {action} from {current.value} state")


# Valid transitions: (current_state, action) -> new_state
_TRANSITIONS: dict[tuple[WorkoutState, str], WorkoutState] = {
    (WorkoutState.IDLE, "start"): WorkoutState.ACTIVE,
    (WorkoutState.ACTIVE, "pause"): WorkoutState.PAUSED,
    (WorkoutState.ACTIVE, "end"): WorkoutState.SUMMARY,
    (WorkoutState.PAUSED, "resume"): WorkoutState.ACTIVE,
    (WorkoutState.PAUSED, "end"): WorkoutState.SUMMARY,
    (WorkoutState.SUMMARY, "reset"): WorkoutState.IDLE,
}

# Map actions to the event they emit
_ACTION_EVENTS: dict[str, EventType] = {
    "start": EventType.WORKOUT_STARTED,
    "pause": EventType.WORKOUT_PAUSED,
    "resume": EventType.WORKOUT_RESUMED,
    "end": EventType.WORKOUT_ENDED,
}


class WorkoutStateMachine:
    """Manages workout lifecycle state transitions.

    Transition table:
        IDLE    -> start()  -> ACTIVE
        ACTIVE  -> pause()  -> PAUSED
        ACTIVE  -> end()    -> SUMMARY
        PAUSED  -> resume() -> ACTIVE
        PAUSED  -> end()    -> SUMMARY
        SUMMARY -> reset()  -> IDLE

    Smart detection inputs:
        on_idle_detected()   — triggers pause() when ACTIVE
        on_rowing_detected() — triggers resume() when PAUSED
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._state = WorkoutState.IDLE
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None

    @property
    def state(self) -> WorkoutState:
        return self._state

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def ended_at(self) -> datetime | None:
        return self._ended_at

    async def _transition(self, action: str) -> WorkoutState:
        """Execute a state transition, publish event, return new state."""
        key = (self._state, action)
        new_state = _TRANSITIONS.get(key)
        if new_state is None:
            raise InvalidTransitionError(self._state, action)

        old_state = self._state
        self._state = new_state

        # Record timestamps
        if action == "start":
            self._started_at = datetime.now(tz=timezone.utc)
            self._ended_at = None
        elif action == "end":
            self._ended_at = datetime.now(tz=timezone.utc)
        elif action == "reset":
            self._started_at = None
            self._ended_at = None

        # Publish event (reset has no event)
        event_type = _ACTION_EVENTS.get(action)
        if event_type is not None:
            await self._event_bus.emit(
                event_type,
                data={
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                    "started_at": self._started_at.isoformat() if self._started_at else None,
                    "ended_at": self._ended_at.isoformat() if self._ended_at else None,
                },
            )

        return new_state

    async def start(self) -> WorkoutState:
        """IDLE -> ACTIVE. Begin a new workout."""
        return await self._transition("start")

    async def pause(self) -> WorkoutState:
        """ACTIVE -> PAUSED. Pause the current workout."""
        return await self._transition("pause")

    async def resume(self) -> WorkoutState:
        """PAUSED -> ACTIVE. Resume the paused workout."""
        return await self._transition("resume")

    async def end(self) -> WorkoutState:
        """ACTIVE|PAUSED -> SUMMARY. End the workout."""
        return await self._transition("end")

    async def reset(self) -> WorkoutState:
        """SUMMARY -> IDLE. Clear state for next workout."""
        return await self._transition("reset")

    async def on_idle_detected(self) -> WorkoutState | None:
        """Smart detection: auto-pause when no strokes detected.

        Only fires when ACTIVE. Returns new state or None if no transition.
        """
        if self._state == WorkoutState.ACTIVE:
            return await self.pause()
        return None

    async def on_rowing_detected(self) -> WorkoutState | None:
        """Smart detection: auto-resume when strokes detected.

        Only fires when PAUSED. Returns new state or None if no transition.
        """
        if self._state == WorkoutState.PAUSED:
            return await self.resume()
        return None

    async def force_reset(self) -> WorkoutState:
        """Force transition to IDLE from any state.

        If currently ACTIVE or PAUSED, emits WORKOUT_ENDED first so the
        recorder flushes data, then resets to IDLE.  Safe to call when
        already IDLE (no-op).
        """
        if self._state == WorkoutState.IDLE:
            return self._state

        if self._state in (WorkoutState.ACTIVE, WorkoutState.PAUSED):
            await self._transition("end")

        if self._state == WorkoutState.SUMMARY:
            await self._transition("reset")

        return self._state
