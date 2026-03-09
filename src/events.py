"""Event bus for inter-component communication via asyncio.Queue."""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """All event types flowing through the bus."""

    METRICS_UPDATE = "metrics_update"
    WORKOUT_STARTED = "workout_started"
    WORKOUT_PAUSED = "workout_paused"
    WORKOUT_RESUMED = "workout_resumed"
    WORKOUT_ENDED = "workout_ended"
    TICKR_CONNECTED = "tickr_connected"
    TICKR_DISCONNECTED = "tickr_disconnected"
    S4_CONNECTED = "s4_connected"
    S4_DISCONNECTED = "s4_disconnected"
    MERGED_METRICS = "merged_metrics"
    STRAVA_UPLOAD_STATUS = "strava_upload_status"


class Event(BaseModel):
    """Typed event envelope carried on the bus."""

    type: EventType
    data: Any = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EventBus:
    """Pub/sub event bus backed by asyncio.Queue instances.

    Each subscriber gets its own queue, so multiple consumers receive
    every event independently.
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[asyncio.Queue[Event]]] = {}

    def subscribe(self, event_type: EventType) -> asyncio.Queue[Event]:
        """Subscribe to an event type. Returns a queue that will receive matching events."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.setdefault(event_type, []).append(queue)
        return queue

    def unsubscribe(self, event_type: EventType, queue: asyncio.Queue[Event]) -> None:
        """Remove a subscription."""
        queues = self._subscribers.get(event_type, [])
        try:
            queues.remove(queue)
        except ValueError:
            pass

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type."""
        for queue in self._subscribers.get(event.type, []):
            await queue.put(event)

    async def emit(self, event_type: EventType, data: Any = None) -> None:
        """Convenience: create and publish an event in one call."""
        await self.publish(Event(type=event_type, data=data))

    def subscriber_count(self, event_type: EventType) -> int:
        """Number of active subscribers for an event type."""
        return len(self._subscribers.get(event_type, []))
