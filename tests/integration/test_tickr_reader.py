"""Integration tests for TickrReader against MockBLEClient."""

import asyncio

import pytest

from src.config import HeartRateSettings
from src.events import EventBus, EventType
from src.models import RowingMetrics
from src.ble.tickr import TickrReader
from tests.conftest import MockBLEClient

# Fast timing kwargs for all test readers
FAST_TIMING = {"backoff_base_s": 0.05, "backoff_max_s": 0.2, "poll_interval_s": 0.02}


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def hr_settings() -> HeartRateSettings:
    return HeartRateSettings(enabled=True, device_mac="AA:BB:CC:DD:EE:FF")


class TestTickrReaderConnection:
    async def test_connects_and_fires_event(
        self, mock_ble_stable: MockBLEClient, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.TICKR_CONNECTED)

        await reader.start()
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event.type == EventType.TICKR_CONNECTED

        await reader.stop()

    async def test_receives_hr_notifications(
        self, mock_ble_stable: MockBLEClient, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.METRICS_UPDATE)

        await reader.start()
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event.type == EventType.METRICS_UPDATE

        metrics: RowingMetrics = event.data
        assert metrics.heart_rate_bpm == 140

        await reader.stop()

    async def test_disabled_skips_start(
        self, mock_ble: MockBLEClient, event_bus: EventBus
    ):
        settings = HeartRateSettings(enabled=False, device_mac="AA:BB:CC:DD:EE:FF")
        reader = TickrReader(mock_ble, event_bus, settings, **FAST_TIMING)

        q = event_bus.subscribe(EventType.TICKR_CONNECTED)
        await reader.start()
        await asyncio.sleep(0.1)

        assert q.empty()
        assert not reader.connected

        await reader.stop()

    async def test_no_mac_skips_start(
        self, mock_ble: MockBLEClient, event_bus: EventBus
    ):
        settings = HeartRateSettings(enabled=True, device_mac="")
        reader = TickrReader(mock_ble, event_bus, settings, **FAST_TIMING)

        await reader.start()
        await asyncio.sleep(0.1)
        assert not reader.connected
        await reader.stop()


class TestTickrReaderDisconnect:
    async def test_fires_disconnect_event(
        self, mock_ble_stable: MockBLEClient, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        mock_ble_stable.set_disconnect_after(2)
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)

        q_connected = event_bus.subscribe(EventType.TICKR_CONNECTED)
        q_disconnected = event_bus.subscribe(EventType.TICKR_DISCONNECTED)

        await reader.start()
        await asyncio.wait_for(q_connected.get(), timeout=1.0)

        event = await asyncio.wait_for(q_disconnected.get(), timeout=1.0)
        assert event.type == EventType.TICKR_DISCONNECTED

        await reader.stop()

    async def test_reconnects_after_disconnect(
        self, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        mock = MockBLEClient()
        mock.set_hr(140, [700])
        mock.set_notify_interval(0.02)
        mock.set_disconnect_after(2)

        reader = TickrReader(mock, event_bus, hr_settings, **FAST_TIMING)
        q_conn = event_bus.subscribe(EventType.TICKR_CONNECTED)
        q_disc = event_bus.subscribe(EventType.TICKR_DISCONNECTED)

        await reader.start()

        # First connection
        await asyncio.wait_for(q_conn.get(), timeout=1.0)

        # Wait for disconnect to actually happen before re-arming
        await asyncio.wait_for(q_disc.get(), timeout=1.0)
        mock._disconnect_after_notifications = None

        # Second connection (after backoff)
        event = await asyncio.wait_for(q_conn.get(), timeout=1.0)
        assert event.type == EventType.TICKR_CONNECTED

        await reader.stop()


class TestTickrReaderUnavailable:
    async def test_unavailable_at_startup_retries(
        self, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        mock = MockBLEClient()
        mock.set_unavailable()
        mock.set_hr(140)
        mock.set_notify_interval(0.02)

        reader = TickrReader(mock, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.TICKR_CONNECTED)

        await reader.start()
        await asyncio.sleep(0.15)

        # Should not be connected
        assert not reader.connected
        assert q.empty()

        # Make available — should reconnect
        mock.set_available()
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event.type == EventType.TICKR_CONNECTED

        await reader.stop()


class TestTickrReaderLifecycle:
    async def test_stop_is_idempotent(
        self, mock_ble_stable: MockBLEClient, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)
        await reader.start()
        await asyncio.sleep(0.05)
        await reader.stop()
        await reader.stop()  # Should not raise

    async def test_connected_property(
        self, mock_ble_stable: MockBLEClient, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)
        assert not reader.connected

        q = event_bus.subscribe(EventType.TICKR_CONNECTED)
        await reader.start()
        await asyncio.wait_for(q.get(), timeout=1.0)
        assert reader.connected

        await reader.stop()
        assert not reader.connected
