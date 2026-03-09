"""BLE FTMS Rower broadcaster — advertises as peripheral for Peloton/WaterRower.

Two parts:
1. Byte packing functions (pack_rower_data) — platform-independent, fully testable
2. FTMSBroadcaster class — BlueZ D-Bus GATT server (Linux/Pi only)

The FTMS Rower Data characteristic (0x2AD1) format follows the Bluetooth FTMS spec.
"""

from __future__ import annotations

import asyncio
import logging
import struct

from src.events import EventBus, EventType
from src.models import RowingMetrics

logger = logging.getLogger(__name__)

# --- FTMS UUIDs ---
FTMS_SERVICE_UUID = "00001826-0000-1000-8000-00805f9b34fb"
ROWER_DATA_CHAR_UUID = "00002ad1-0000-1000-8000-00805f9b34fb"

# --- Rower Data flags (uint16, little-endian) ---
# Bit 0: More Data (0 = present fields follow, 1 = some omitted) — always 0
# Bit 1: Average Stroke Rate present
# Bit 2: Total Distance present
# Bit 3: Instantaneous Pace present
# Bit 4: Average Pace present
# Bit 5: Instantaneous Power present
# Bit 6: Average Power present
# Bit 7: Resistance Level present
# Bit 8: Expended Energy present
# Bit 9: Heart Rate present
# Bit 10: Metabolic Equivalent present
# Bit 11: Elapsed Time present
# Bit 12: Remaining Time present
FLAG_AVG_STROKE_RATE = 1 << 1
FLAG_TOTAL_DISTANCE = 1 << 2
FLAG_INSTANTANEOUS_PACE = 1 << 3
FLAG_INSTANTANEOUS_POWER = 1 << 5
FLAG_HEART_RATE = 1 << 9


def pack_rower_data(metrics: RowingMetrics) -> bytes:
    """Pack RowingMetrics into FTMS Rower Data characteristic bytes.

    Field layout (after flags uint16):
    - Stroke Rate: uint8, resolution 0.5 SPM (value × 2)
    - Stroke Count: uint16
    - Total Distance: uint24 (3 bytes LE), meters
    - Instantaneous Pace: uint16, seconds/500m
    - Instantaneous Power: int16, watts (clamped to >= 0)
    - Heart Rate: uint8, BPM (conditional — omitted if None)

    Returns:
        bytes for the Rower Data characteristic value.
    """
    flags = 0
    data = bytearray()

    # Stroke Rate (uint8 × 2 resolution) + Stroke Count (uint16)
    # These are always present (part of the base fields when flag bit 1 is set)
    stroke_rate_raw = 0
    stroke_count = 0
    if metrics.stroke_rate is not None and metrics.stroke_rate > 0:
        stroke_rate_raw = min(int(round(metrics.stroke_rate * 2)), 255)
    if metrics.stroke_count is not None:
        stroke_count = min(metrics.stroke_count, 0xFFFF)
    flags |= FLAG_AVG_STROKE_RATE
    data.extend(struct.pack("<B", stroke_rate_raw))
    data.extend(struct.pack("<H", stroke_count))

    # Total Distance (uint24 LE)
    if metrics.distance_m is not None:
        flags |= FLAG_TOTAL_DISTANCE
        distance = min(int(round(metrics.distance_m)), 0xFFFFFF)
        data.extend(distance.to_bytes(3, byteorder="little"))

    # Instantaneous Pace (uint16, seconds/500m)
    if metrics.pace_s_per_500m is not None and metrics.pace_s_per_500m > 0:
        flags |= FLAG_INSTANTANEOUS_PACE
        pace = min(int(round(metrics.pace_s_per_500m)), 0xFFFF)
        data.extend(struct.pack("<H", pace))

    # Instantaneous Power (int16, watts — clamp negative to 0)
    if metrics.power_watts is not None:
        flags |= FLAG_INSTANTANEOUS_POWER
        power = max(0, min(int(round(metrics.power_watts)), 32767))
        data.extend(struct.pack("<h", power))

    # Heart Rate (uint8, BPM — conditional)
    if metrics.heart_rate_bpm is not None:
        flags |= FLAG_HEART_RATE
        hr = min(max(metrics.heart_rate_bpm, 0), 255)
        data.extend(struct.pack("<B", hr))

    # Prepend flags
    result = struct.pack("<H", flags) + bytes(data)
    return result


class FTMSBroadcaster:
    """BLE FTMS Rower peripheral broadcaster.

    Uses BlueZ D-Bus GATT server to advertise as 'BuoyCast' and serve
    the Rower Data characteristic. Subscribes to MERGED_METRICS events
    and updates the characteristic at ~1Hz.

    This class requires Linux with BlueZ — it will log a warning and
    no-op on other platforms.
    """

    def __init__(self, event_bus: EventBus, device_name: str = "BuoyCast") -> None:
        self._bus = event_bus
        self._device_name = device_name
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._latest_data: bytes = pack_rower_data(
            RowingMetrics(
                timestamp=__import__("datetime").datetime.now(
                    tz=__import__("datetime").timezone.utc
                )
            )
        )

    @property
    def latest_data(self) -> bytes:
        """Most recently packed Rower Data characteristic value."""
        return self._latest_data

    async def start(self) -> None:
        """Start the FTMS broadcaster.

        Subscribes to MERGED_METRICS and starts updating the characteristic.
        On non-Linux platforms, logs a warning and runs in data-only mode
        (still packs data, but doesn't advertise over BLE).
        """
        self._running = True
        self._queue = self._bus.subscribe(EventType.MERGED_METRICS)
        self._task = asyncio.create_task(self._run_loop())

        # Attempt to set up BlueZ advertising (Linux only)
        try:
            await self._setup_ble()
        except Exception:
            logger.warning(
                "BlueZ GATT setup failed — running in data-only mode "
                "(BLE advertising not available on this platform)"
            )

    async def stop(self) -> None:
        """Stop the broadcaster."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if hasattr(self, "_queue"):
            self._bus.unsubscribe(EventType.MERGED_METRICS, self._queue)

        try:
            await self._teardown_ble()
        except Exception:
            pass

    async def _run_loop(self) -> None:
        """Process merged metrics and update characteristic."""
        while self._running:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                raise

            metrics = event.data
            if not isinstance(metrics, RowingMetrics):
                continue

            self._latest_data = pack_rower_data(metrics)
            await self._update_characteristic(self._latest_data)

    async def _setup_ble(self) -> None:
        """Set up BlueZ D-Bus GATT server and advertising.

        This is a placeholder — full implementation requires:
        - Register GATT application via D-Bus
        - Register advertisement with FTMS service UUID
        - Handle client connect/disconnect callbacks
        """
        import platform

        if platform.system() != "Linux":
            raise RuntimeError("BlueZ only available on Linux")

        # TODO: Implement BlueZ D-Bus GATT server registration
        # This will use dbus-next or similar to:
        # 1. Register GATT application with FTMS service + Rower Data characteristic
        # 2. Start LE advertising as "BuoyCast"
        # 3. Handle ReadValue requests with self._latest_data
        logger.info("BlueZ FTMS GATT server setup (placeholder)")

    async def _teardown_ble(self) -> None:
        """Tear down BlueZ advertising and GATT server."""
        logger.info("BlueZ FTMS GATT server teardown")

    async def _update_characteristic(self, data: bytes) -> None:
        """Update the Rower Data characteristic value.

        On Linux with BlueZ, this would trigger a notification to
        connected clients. In data-only mode, this is a no-op.
        """
        pass
