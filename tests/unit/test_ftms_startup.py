"""FTMS startup must never block the rest of BuoyCast on Bluetooth."""

import asyncio

from src.ble.ftms import FTMSBroadcaster
from src.events import EventBus


async def test_start_returns_while_bluez_setup_hangs(monkeypatch):
    setup_started = asyncio.Event()

    async def hanging_setup(self):
        setup_started.set()
        await asyncio.Event().wait()  # e.g. org.bluez never answers

    monkeypatch.setattr(FTMSBroadcaster, "_setup_ble", hanging_setup)
    ftms = FTMSBroadcaster(EventBus())

    await asyncio.wait_for(ftms.start(), timeout=1.0)
    await asyncio.wait_for(setup_started.wait(), timeout=1.0)

    # stop() must cancel the pending setup rather than wait for it.
    await asyncio.wait_for(ftms.stop(), timeout=1.0)
    assert ftms._setup_task is not None and ftms._setup_task.done()
