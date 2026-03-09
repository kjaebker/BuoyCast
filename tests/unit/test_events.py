"""Tests for event bus."""

import asyncio
from datetime import datetime, timezone

import pytest

from src.events import Event, EventBus, EventType


class TestEventType:
    def test_all_values_exist(self):
        expected = {
            "metrics_update",
            "merged_metrics",
            "workout_started",
            "workout_paused",
            "workout_resumed",
            "workout_ended",
            "tickr_connected",
            "tickr_disconnected",
            "s4_connected",
            "s4_disconnected",
            "idle_warning",
            "strava_upload_status",
        }
        assert {e.value for e in EventType} == expected

    def test_is_str_enum(self):
        assert isinstance(EventType.METRICS_UPDATE, str)


class TestEvent:
    def test_minimal(self):
        e = Event(type=EventType.S4_CONNECTED)
        assert e.type == EventType.S4_CONNECTED
        assert e.data is None
        assert isinstance(e.timestamp, datetime)

    def test_with_data(self):
        e = Event(type=EventType.METRICS_UPDATE, data={"stroke_rate": 28.0})
        assert e.data["stroke_rate"] == 28.0

    def test_timestamp_auto_set(self):
        before = datetime.now(tz=timezone.utc)
        e = Event(type=EventType.S4_CONNECTED)
        after = datetime.now(tz=timezone.utc)
        assert before <= e.timestamp <= after


class TestEventBus:
    async def test_single_subscriber(self):
        bus = EventBus()
        q = bus.subscribe(EventType.S4_CONNECTED)
        await bus.emit(EventType.S4_CONNECTED)
        event = q.get_nowait()
        assert event.type == EventType.S4_CONNECTED

    async def test_multiple_subscribers_same_event(self):
        bus = EventBus()
        q1 = bus.subscribe(EventType.METRICS_UPDATE)
        q2 = bus.subscribe(EventType.METRICS_UPDATE)
        await bus.emit(EventType.METRICS_UPDATE, data={"hr": 140})
        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        assert e1.type == EventType.METRICS_UPDATE
        assert e2.type == EventType.METRICS_UPDATE
        assert e1.data == e2.data

    async def test_subscriber_only_gets_subscribed_events(self):
        bus = EventBus()
        q = bus.subscribe(EventType.S4_CONNECTED)
        await bus.emit(EventType.TICKR_CONNECTED)
        assert q.empty()

    async def test_publish_with_no_subscribers(self):
        bus = EventBus()
        # Should not raise
        await bus.emit(EventType.WORKOUT_STARTED)

    async def test_unsubscribe(self):
        bus = EventBus()
        q = bus.subscribe(EventType.S4_CONNECTED)
        assert bus.subscriber_count(EventType.S4_CONNECTED) == 1
        bus.unsubscribe(EventType.S4_CONNECTED, q)
        assert bus.subscriber_count(EventType.S4_CONNECTED) == 0
        await bus.emit(EventType.S4_CONNECTED)
        assert q.empty()

    async def test_unsubscribe_nonexistent_queue(self):
        bus = EventBus()
        q: asyncio.Queue[Event] = asyncio.Queue()
        # Should not raise
        bus.unsubscribe(EventType.S4_CONNECTED, q)

    async def test_subscriber_count(self):
        bus = EventBus()
        assert bus.subscriber_count(EventType.WORKOUT_ENDED) == 0
        q1 = bus.subscribe(EventType.WORKOUT_ENDED)
        assert bus.subscriber_count(EventType.WORKOUT_ENDED) == 1
        q2 = bus.subscribe(EventType.WORKOUT_ENDED)
        assert bus.subscriber_count(EventType.WORKOUT_ENDED) == 2
        bus.unsubscribe(EventType.WORKOUT_ENDED, q1)
        assert bus.subscriber_count(EventType.WORKOUT_ENDED) == 1

    async def test_publish_event_directly(self):
        bus = EventBus()
        q = bus.subscribe(EventType.WORKOUT_ENDED)
        event = Event(type=EventType.WORKOUT_ENDED, data={"id": "wk-1"})
        await bus.publish(event)
        received = q.get_nowait()
        assert received is event

    async def test_multiple_events_ordered(self):
        bus = EventBus()
        q = bus.subscribe(EventType.METRICS_UPDATE)
        for i in range(5):
            await bus.emit(EventType.METRICS_UPDATE, data={"seq": i})
        for i in range(5):
            e = q.get_nowait()
            assert e.data["seq"] == i

    async def test_independent_event_types(self):
        bus = EventBus()
        q_s4 = bus.subscribe(EventType.S4_CONNECTED)
        q_tickr = bus.subscribe(EventType.TICKR_CONNECTED)
        await bus.emit(EventType.S4_CONNECTED, data="s4")
        await bus.emit(EventType.TICKR_CONNECTED, data="tickr")
        assert q_s4.get_nowait().data == "s4"
        assert q_tickr.get_nowait().data == "tickr"
        assert q_s4.qsize() == 0
        assert q_tickr.qsize() == 0
