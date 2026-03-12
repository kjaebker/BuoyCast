"""BLE FTMS Rower broadcaster — advertises as peripheral for Peloton/WaterRower.

Two parts:
1. Byte packing functions (pack_rower_data) — platform-independent, fully testable
2. FTMSBroadcaster class — BlueZ GATT server via bless (Linux/Pi only)

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
FITNESS_MACHINE_FEATURE_UUID = "00002acc-0000-1000-8000-00805f9b34fb"

# --- Fitness Machine Feature value (0x2ACC) ---
# Reports which fields the rower can provide, as two uint32 LE values:
#   [0] Feature flags  [1] Target Setting flags (none supported)
# Bit  1: Cadence (stroke rate)
# Bit  2: Total Distance
# Bit  5: Pace
# Bit 10: Heart Rate
# Bit 14: Power
_FTMS_FEATURE_FLAGS = (1 << 1) | (1 << 2) | (1 << 5) | (1 << 10) | (1 << 14)
_FITNESS_MACHINE_FEATURE_VALUE = struct.pack("<II", _FTMS_FEATURE_FLAGS, 0)

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

    FTMS Rower Data field layout (flags uint16, then fields in order):
      BASE (bit 0 = 0, always present — no flag needed):
        Instantaneous Stroke Rate: uint8, resolution 0.5 SPM (raw = SPM × 2)
        Stroke Count:              uint16
      OPTIONAL (present only when corresponding flag bit is set):
        Bit 1 — Average Stroke Rate:    uint8 (we don't send this)
        Bit 2 — Total Distance:         uint24 LE, meters
        Bit 3 — Instantaneous Pace:     uint16, seconds/500m
        Bit 5 — Instantaneous Power:    int16, watts
        Bit 9 — Heart Rate:             uint8, BPM

    Note: bit 0 = 0 means "More Data = false", i.e. the base fields
    (Instantaneous Stroke Rate + Stroke Count) ARE present.  Setting bit 1
    would signal an *additional* Average Stroke Rate field — do NOT set it
    unless you also write that extra uint8, or clients will mis-parse every
    subsequent field and crash.

    Returns:
        bytes for the Rower Data characteristic value.
    """
    flags = 0
    data = bytearray()

    # Base fields — always present (bit 0 = 0 signals their presence).
    # No flag bit needed; writing them unconditionally is correct per spec.
    stroke_rate_raw = 0
    stroke_count = 0
    if metrics.stroke_rate is not None and metrics.stroke_rate > 0:
        stroke_rate_raw = min(int(round(metrics.stroke_rate * 2)), 255)
    if metrics.stroke_count is not None:
        stroke_count = min(metrics.stroke_count, 0xFFFF)
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

    Uses the `bless` library to register a BlueZ GATT application and start
    LE advertising as 'BuoyCast'. Subscribes to MERGED_METRICS events and
    updates the Rower Data characteristic (~1Hz), triggering BLE notifications
    to connected clients (Peloton app, WaterRower app, etc.).

    This class requires Linux with BlueZ and the `bless` package. On other
    platforms, or if bless is not installed, it logs a warning and runs in
    data-only mode (still packs data, but does not advertise).
    """

    def __init__(self, event_bus: EventBus, device_name: str = "BuoyCast") -> None:
        self._bus = event_bus
        self._device_name = device_name
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._server: object | None = None  # bless.BlessServer, lazily imported
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
        On non-Linux platforms, or if bless is unavailable, logs an error and
        runs in data-only mode (still packs data, but doesn't advertise over BLE).
        """
        self._running = True
        self._queue = self._bus.subscribe(EventType.MERGED_METRICS)
        self._task = asyncio.create_task(self._run_loop())

        try:
            await self._setup_ble()
        except Exception as exc:
            logger.error(
                "BlueZ GATT setup failed — BLE broadcasting disabled. "
                "BuoyCast will NOT appear to Peloton. Error: %s",
                exc,
                exc_info=True,
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
        """Set up BlueZ GATT server and LE advertising via bless.

        Retries up to _BLE_SETUP_ATTEMPTS times with _BLE_RETRY_DELAY_S seconds
        between attempts. This handles two real-world failure modes:
        1. The HCI adapter needs ~1-2s after `bluetoothctl power on` before its
           advertising stack accepts RegisterAdvertisement — attempting too early
           results in a silent failure where bless returns OK but no packets go
           out over the air.
        2. After a crash/restart, BlueZ can hold stale D-Bus GATT/advertisement
           registrations for several seconds. Retrying lets those expire before
           we re-register.
        """
        import platform

        if platform.system() != "Linux":
            raise RuntimeError("BlueZ only available on Linux")

        try:
            from bless import (  # type: ignore[import]
                BlessServer,
                GATTAttributePermissions,
                GATTCharacteristicProperties,
            )
        except ImportError as exc:
            raise RuntimeError(
                "bless not installed — run: pip install bless"
            ) from exc

        _BLE_SETUP_ATTEMPTS = 4
        _BLE_RETRY_DELAY_S = 3.0
        # Give the HCI adapter a moment to finish initialising its advertising
        # stack after being powered on (bluetoothctl power on returns before
        # BlueZ's LEAdvertisingManager is fully ready).
        _BLE_INITIAL_DELAY_S = 2.0

        logger.info("FTMS: waiting %.0fs for BT adapter to settle…", _BLE_INITIAL_DELAY_S)
        await asyncio.sleep(_BLE_INITIAL_DELAY_S)

        last_exc: Exception | None = None
        for attempt in range(1, _BLE_SETUP_ATTEMPTS + 1):
            try:
                # Always create a fresh BlessServer — reusing a stopped instance
                # leaves stale D-Bus objects and causes RegisterApplication to fail.
                server = BlessServer(name=self._device_name, name_overwrite=True)

                # Register the FTMS service
                await server.add_new_service(FTMS_SERVICE_UUID)

                # Fitness Machine Feature (0x2ACC) — READ
                # Required by the FTMS spec; tells clients which fields we can provide.
                await server.add_new_characteristic(
                    FTMS_SERVICE_UUID,
                    FITNESS_MACHINE_FEATURE_UUID,
                    GATTCharacteristicProperties.read,
                    bytearray(_FITNESS_MACHINE_FEATURE_VALUE),
                    GATTAttributePermissions.readable,
                )

                # Rower Data (0x2AD1) — READ + NOTIFY
                # Clients subscribe to notifications; we push updates at ~1Hz.
                await server.add_new_characteristic(
                    FTMS_SERVICE_UUID,
                    ROWER_DATA_CHAR_UUID,
                    GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
                    bytearray(self._latest_data),
                    GATTAttributePermissions.readable,
                )

                # bless requires a read callback — without it, any client READ
                # raises BlessError("Read Callback is undefined") and crashes
                # the D-Bus connection. Just return the characteristic's stored value.
                server.read_request_func = lambda char: char.value

                await server.start()
                self._server = server
                logger.info(
                    "FTMS advertising as '%s' — service UUID %s",
                    self._device_name,
                    FTMS_SERVICE_UUID,
                )
                return  # success — exit retry loop

            except Exception as exc:
                last_exc = exc
                if attempt < _BLE_SETUP_ATTEMPTS:
                    logger.warning(
                        "FTMS BLE setup attempt %d/%d failed: %s — retrying in %.0fs",
                        attempt,
                        _BLE_SETUP_ATTEMPTS,
                        exc,
                        _BLE_RETRY_DELAY_S,
                    )
                    await asyncio.sleep(_BLE_RETRY_DELAY_S)
                else:
                    logger.error(
                        "FTMS BLE setup failed after %d attempts — last error: %s",
                        _BLE_SETUP_ATTEMPTS,
                        exc,
                    )

        raise last_exc  # type: ignore[misc]

    async def _teardown_ble(self) -> None:
        """Stop BlueZ advertising and unregister the GATT application."""
        if self._server is not None:
            try:
                await self._server.stop()
            except Exception as exc:
                logger.debug("FTMS server stop error: %s", exc)
            self._server = None
        logger.info("FTMS advertising stopped")

    async def _update_characteristic(self, data: bytes) -> None:
        """Push new Rower Data to all subscribed BLE clients."""
        if self._server is None:
            return
        char = self._server.get_characteristic(ROWER_DATA_CHAR_UUID)
        if char is None:
            return
        char.value = bytearray(data)
        self._server.update_value(FTMS_SERVICE_UUID, ROWER_DATA_CHAR_UUID)
