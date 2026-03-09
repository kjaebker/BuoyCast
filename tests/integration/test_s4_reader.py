"""Integration tests for S4Reader against MockSerial."""

import asyncio

import pytest

from src.config import S4Settings
from src.events import EventBus, EventType
from src.models import RowingMetrics
from src.s4.protocol import (
    ADDR_CALORIES,
    ADDR_DISTANCE_M,
    ADDR_STROKE_RATE,
    LINE_ENDING,
    RESP_WR,
)
from src.s4.reader import S4Reader
from tests.conftest import MockSerial


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def fast_settings() -> S4Settings:
    """S4 settings with fast poll rate for testing."""
    return S4Settings(poll_interval_hz=10.0, reconnect_delay_s=0)


class TestS4ReaderHandshake:
    async def test_connects_and_performs_handshake(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        q = event_bus.subscribe(EventType.S4_CONNECTED)
        await reader.start()

        # Wait for connection event
        event = await asyncio.wait_for(q.get(), timeout=2.0)
        assert event.type == EventType.S4_CONNECTED

        await reader.stop()

    async def test_handshake_sends_usb_then_reset(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        await reader.start()
        # Give it time to connect
        await asyncio.sleep(0.2)
        await reader.stop()

        # First write should be USB, second should be RESET
        writes = [w.decode("ascii").strip() for w in mock_serial.write_log]
        assert writes[0] == "USB"
        assert writes[1] == "RESET"


class TestS4ReaderMetrics:
    async def test_emits_metrics_update_events(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        q = event_bus.subscribe(EventType.METRICS_UPDATE)
        await reader.start()

        # Wait for at least one metrics event
        event = await asyncio.wait_for(q.get(), timeout=2.0)
        assert event.type == EventType.METRICS_UPDATE
        assert isinstance(event.data, RowingMetrics)

        await reader.stop()

    async def test_metrics_fields_populated(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state(
            stroke_rate_spm=28.0,
            stroke_count=100,
            distance_m=500,
            pace_s_per_500m=120.0,
            power_watts=150,
            calories=50,
            elapsed_minutes=10,
        )
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        q = event_bus.subscribe(EventType.METRICS_UPDATE)
        await reader.start()

        event = await asyncio.wait_for(q.get(), timeout=2.0)
        metrics: RowingMetrics = event.data

        assert metrics.stroke_rate == 28.0
        assert metrics.stroke_count == 100
        assert metrics.distance_m == 500.0
        assert metrics.pace_s_per_500m == 120.0
        assert metrics.power_watts == 150.0
        assert metrics.calories == 50
        assert metrics.elapsed_seconds == 600  # 10 minutes

        await reader.stop()

    async def test_idle_metrics(
        self, mock_serial_idle: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        reader = S4Reader(mock_serial_idle, event_bus, fast_settings)

        q = event_bus.subscribe(EventType.METRICS_UPDATE)
        await reader.start()

        event = await asyncio.wait_for(q.get(), timeout=2.0)
        metrics: RowingMetrics = event.data

        assert metrics.stroke_rate == 0.0
        assert metrics.distance_m == 0.0
        assert metrics.power_watts == 0.0

        await reader.stop()


class TestS4ReaderDisconnect:
    async def test_fires_disconnect_event(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        # Disconnect after a few reads (handshake + some poll responses)
        mock_serial.set_disconnect_after(5)

        reader = S4Reader(mock_serial, event_bus, fast_settings)

        q_connected = event_bus.subscribe(EventType.S4_CONNECTED)
        q_disconnected = event_bus.subscribe(EventType.S4_DISCONNECTED)

        await reader.start()

        # Should connect first
        await asyncio.wait_for(q_connected.get(), timeout=2.0)

        # Then disconnect
        event = await asyncio.wait_for(q_disconnected.get(), timeout=2.0)
        assert event.type == EventType.S4_DISCONNECTED

        await reader.stop()

    async def test_auto_reconnects_after_disconnect(
        self, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock = MockSerial()
        mock.set_steady_state()
        mock.set_disconnect_after(5)

        reader = S4Reader(mock, event_bus, fast_settings)

        q_connected = event_bus.subscribe(EventType.S4_CONNECTED)

        await reader.start()

        # First connection
        await asyncio.wait_for(q_connected.get(), timeout=2.0)

        # After disconnect, the mock resets disconnect_after — set fresh state
        # The reader should reconnect since reconnect_delay_s=0
        # MockSerial.open() will succeed again after close()
        # We need to re-arm the mock for the second connection
        mock._disconnect_after = None  # Allow second connection to persist

        # Wait for second connection
        event = await asyncio.wait_for(q_connected.get(), timeout=3.0)
        assert event.type == EventType.S4_CONNECTED

        await reader.stop()


class TestS4ReaderMalformedData:
    async def test_handles_corrupt_response_gracefully(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        q = event_bus.subscribe(EventType.METRICS_UPDATE)
        await reader.start()

        # Inject some corrupt data — reader should skip and continue
        mock_serial.queue_raw_response(b"GARBAGE_DATA\r\n")
        mock_serial.queue_raw_response(b"IDS1E1ZZ\r\n")  # Invalid hex

        # Should still get metrics events (from the valid polled data)
        event = await asyncio.wait_for(q.get(), timeout=2.0)
        assert event.type == EventType.METRICS_UPDATE

        await reader.stop()


class TestS4ReaderLifecycle:
    async def test_stop_is_idempotent(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)
        await reader.start()
        await asyncio.sleep(0.1)
        await reader.stop()
        await reader.stop()  # Should not raise

    async def test_connected_property(
        self, mock_serial: MockSerial, event_bus: EventBus, fast_settings: S4Settings
    ):
        mock_serial.set_steady_state()
        reader = S4Reader(mock_serial, event_bus, fast_settings)

        assert not reader.connected

        q = event_bus.subscribe(EventType.S4_CONNECTED)
        await reader.start()
        await asyncio.wait_for(q.get(), timeout=2.0)

        assert reader.connected

        await reader.stop()
        assert not reader.connected
