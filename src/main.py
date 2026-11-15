"""BuoyCast entry point — wires all async tasks and runs the server.

Starts four top-level coroutines:
  - s4_reader_task:    polls WaterRower S4 via USB serial
  - tickr_reader_task: reads HR from Wahoo TICKR via BLE
  - ftms_broadcaster:  advertises BLE FTMS Rower Data to Peloton
  - web_server_task:   FastAPI + WebSocket dashboard
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from src.ble.ftms import FTMSBroadcaster
from src.config import Settings, load_settings
from src.events import EventBus
from src.export.http import WorkoutExporter
from src.logging_config import configure_logging
from src.merger import DataMerger
from src.storage.db import Database
from src.strava.auth import StravaAuth
from src.web.server import create_app
from src.workout.recorder import StrokeRecorder
from src.workout.state import WorkoutStateMachine

logger = logging.getLogger(__name__)


async def run(settings: Settings, simulate: bool = False) -> None:
    """Wire all components and run the application."""
    # Ensure data directories exist
    Path(settings.storage.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.storage.fit_dir).mkdir(parents=True, exist_ok=True)

    event_bus = EventBus()
    db = Database(settings.storage.db_path)
    await db.connect()

    state_machine = WorkoutStateMachine(event_bus)
    merger = DataMerger(event_bus)
    recorder = StrokeRecorder(event_bus, state_machine, db)
    ftms = FTMSBroadcaster(event_bus)
    exporter = WorkoutExporter(
        event_bus,
        db,
        settings.export,
        fit_dir=settings.storage.fit_dir,
        min_distance_m=settings.workout.min_workout_distance_m,
    )

    strava_auth = None
    if settings.strava.client_id and settings.strava.client_secret:
        redirect_uri = (
            f"http://{settings.server.mdns_name}.local:{settings.server.port}/api/strava/callback"
        )
        strava_auth = StravaAuth(
            db=db,
            client_id=settings.strava.client_id,
            client_secret=settings.strava.client_secret,
            redirect_uri=redirect_uri,
        )

    app = create_app(
        event_bus=event_bus,
        state_machine=state_machine,
        db=db,
        strava_auth=strava_auth,
        exporter=exporter,
        update_repo=settings.updates.repo,
        allowed_hosts=settings.server.allowed_hosts,
    )
    app_state = app.state.app_state

    # Track components for cleanup
    components = [merger, recorder, ftms, exporter]

    # Start core components (each manages its own background tasks)
    await merger.start()
    await recorder.start()
    await ftms.start()
    await exporter.start()

    # Start S4 reader
    s4_reader = None
    if simulate:
        from src.simulator import SimulatedS4Reader

        s4_reader = SimulatedS4Reader(event_bus)
        await s4_reader.start()
        components.append(s4_reader)
        app_state.s4_reader = s4_reader
        logger.info("S4 reader: simulation mode")
    else:
        try:
            import serial

            from src.s4.reader import AsyncSerial, S4Reader

            _raw_serial = serial.Serial()
            _raw_serial.port = settings.s4.port
            _raw_serial.baudrate = settings.s4.baud_rate
            _raw_serial.timeout = 0.1  # S4 responds in ~6ms; 100ms timeout avoids orphaned threads
            serial_port = AsyncSerial(_raw_serial)
            s4_reader = S4Reader(serial_port, event_bus, settings.s4)
            await s4_reader.start()
            components.append(s4_reader)
            app_state.s4_reader = s4_reader
        except ImportError:
            logger.warning("pyserial not available — S4 reader disabled")
        except Exception as exc:
            logger.warning("S4 reader init failed: %s", exc)

    # Start TICKR reader
    tickr_reader = None
    if simulate:
        from src.simulator import SimulatedHRReader

        tickr_reader = SimulatedHRReader(event_bus)
        await tickr_reader.start()
        components.append(tickr_reader)
        app_state.tickr_reader = tickr_reader
        logger.info("HR reader: simulation mode")
    elif settings.heart_rate.enabled and settings.heart_rate.device_mac:
        try:
            from bleak import BleakClient, BleakScanner

            from src.ble.tickr import TickrReader

            _mac = settings.heart_rate.device_mac

            async def ble_factory() -> BleakClient:
                """Scan for TICKR before connecting — required on Linux/BlueZ to
                populate the device cache, otherwise connect raises DeviceNotFound.

                We pass the MAC string (not the BLEDevice object) to BleakClient so
                that bleak re-resolves the D-Bus object path at connect time rather
                than using a potentially-stale path captured during the scan.
                """
                logger.debug("TICKR: scanning for %s (timeout=20s)...", _mac)
                device = await BleakScanner.find_device_by_address(_mac, timeout=20.0)
                if device is not None:
                    logger.debug("TICKR: found via scan, connecting via MAC string")
                    return BleakClient(_mac, timeout=10.0)
                raise OSError(f"TICKR {_mac} not found in BLE scan — is it worn and awake?")

            tickr_reader = TickrReader(ble_factory, event_bus, settings.heart_rate)
            await tickr_reader.start()
            components.append(tickr_reader)
            app_state.tickr_reader = tickr_reader
        except ImportError:
            logger.warning("bleak not available — TICKR reader disabled")
        except Exception as exc:
            logger.warning("TICKR reader init failed: %s", exc)

    # Run uvicorn (blocks until shutdown)
    config = uvicorn.Config(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    logger.info(
        "BuoyCast started — http://%s:%d",
        settings.server.host,
        settings.server.port,
    )

    try:
        await server.serve()
    finally:
        # Stop all components gracefully
        for component in reversed(components):
            try:
                await component.stop()
            except Exception as exc:
                logger.warning("Error stopping %s: %s", type(component).__name__, exc)
        await db.close()
        logger.info("BuoyCast shutdown complete")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="BuoyCast rowing bridge")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Replace real S4/TICKR hardware with simulated data sources (for local dev)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml (default: ./config.toml)",
    )
    args = parser.parse_args()

    config_path: Path = args.config
    if not config_path.exists():
        if args.simulate and Path("config.toml.example").exists():
            config_path = Path("config.toml.example")
            print("config.toml not found — using config.toml.example for simulation")
        else:
            logger.error("config.toml not found — copy config.toml.example and edit it")
            sys.exit(1)

    settings = load_settings(config_path)
    configure_logging(
        level=settings.logging.level,
        log_dir=settings.logging.log_dir,
        json_logs=settings.logging.json_logs,
    )
    asyncio.run(run(settings, simulate=args.simulate))


if __name__ == "__main__":
    main()
