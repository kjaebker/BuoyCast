"""Integration tests for TickrReader against MockBLEClient."""

import asyncio

import pytest

from src.ble.tickr import TickrReader
from src.config import HeartRateSettings
from src.events import EventBus, EventType
from src.models import RowingMetrics
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
        # mock_ble_stable sends BPM field=140, RR=700ms.
        # RR-derived BPM = round(60000/700) = 86; reader emits that value.
        reader = TickrReader(mock_ble_stable, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.METRICS_UPDATE)

        await reader.start()
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        assert event.type == EventType.METRICS_UPDATE

        metrics: RowingMetrics = event.data
        assert metrics.heart_rate_bpm == round(60000 / 700)

        await reader.stop()

    async def test_rr_smoothing_corrects_doubled_bpm(
        self, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        # Simulate the TICKR double-counting bug: BPM field=107, RR=1260ms (~49 BPM).
        # After the buffer fills, emitted BPM must be derived from RR, not the field.
        mock = MockBLEClient()
        rr_ms = round(0x04EC * 1000 / 1024)  # 1260 raw → ~1230ms
        mock.set_hr(107, [rr_ms])
        mock.set_notify_interval(0.02)

        reader = TickrReader(mock, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.METRICS_UPDATE)

        await reader.start()
        # Drain enough notifications to fill the buffer (maxlen=10)
        last_bpm = None
        for _ in range(12):
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            last_bpm = event.data.heart_rate_bpm

        expected = round(60000 / rr_ms)
        assert last_bpm == expected, f"Expected {expected} BPM from RR, got {last_bpm}"
        assert last_bpm != 107

        await reader.stop()

    async def test_disabled_skips_start(self, mock_ble: MockBLEClient, event_bus: EventBus):
        settings = HeartRateSettings(enabled=False, device_mac="AA:BB:CC:DD:EE:FF")
        reader = TickrReader(mock_ble, event_bus, settings, **FAST_TIMING)

        q = event_bus.subscribe(EventType.TICKR_CONNECTED)
        await reader.start()
        await asyncio.sleep(0.1)

        assert q.empty()
        assert not reader.connected

        await reader.stop()

    async def test_no_mac_skips_start(self, mock_ble: MockBLEClient, event_bus: EventBus):
        settings = HeartRateSettings(enabled=True, device_mac="")
        reader = TickrReader(mock_ble, event_bus, settings, **FAST_TIMING)

        await reader.start()
        await asyncio.sleep(0.1)
        assert not reader.connected
        await reader.stop()


class TestTickrReaderRRRecovery:
    async def test_rr_buffer_corruption_recovery(
        self, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        """When RR buffer gets corrupted (short intervals), the reader should
        detect the divergence from the BPM field and reset the buffer, returning
        to plausible values instead of staying stuck at 200+ BPM."""
        mock = MockBLEClient()
        # Start with normal HR: BPM=80, RR=750ms (~80 BPM)
        mock.set_hr(80, [750])
        mock.set_notify_interval(0.02)

        reader = TickrReader(mock, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.METRICS_UPDATE)

        await reader.start()
        # Let a few normal readings come through
        for _ in range(5):
            await asyncio.wait_for(q.get(), timeout=1.0)

        # Simulate corruption: TICKR starts sending short RR intervals (300ms = 200 BPM)
        # but BPM field stays at 80 (real HR)
        mock.set_hr(80, [300])

        # Collect readings — after divergence detection (3+ readings), should recover
        bpm_values = []
        for _ in range(10):
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            bpm_values.append(event.data.heart_rate_bpm)

        # After recovery, BPM should return to near the field BPM (80), not stay at 200.
        # Rate limiting may cause gradual descent, so just check the last value
        # is much closer to 80 than to 200.
        assert bpm_values[-1] < 130, (
            f"BPM should recover toward field value ~80, got {bpm_values[-1]}"
        )

        await reader.stop()

    async def test_rate_of_change_limiting(
        self, event_bus: EventBus, hr_settings: HeartRateSettings
    ):
        """HR should not jump more than 15 BPM between consecutive readings."""
        mock = MockBLEClient()
        mock.set_hr(80, [750])
        mock.set_notify_interval(0.02)

        reader = TickrReader(mock, event_bus, hr_settings, **FAST_TIMING)
        q = event_bus.subscribe(EventType.METRICS_UPDATE)

        await reader.start()
        # Let initial readings stabilize
        last_bpm = None
        for _ in range(5):
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            last_bpm = event.data.heart_rate_bpm

        # Sudden jump: change to BPM=200 with matching RR intervals
        mock.set_hr(200, [300])

        # The first reading after the jump should be rate-limited
        bpm_values = []
        for _ in range(3):
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            bpm_values.append(event.data.heart_rate_bpm)

        # First value after jump should be at most 15 BPM above previous
        assert bpm_values[0] <= last_bpm + 15, (
            f"Expected rate-limited BPM ≤ {last_bpm + 15}, got {bpm_values[0]}"
        )

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
