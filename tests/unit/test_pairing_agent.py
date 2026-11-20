"""The BlueZ pairing agent must build with the real D-Bus library.

Regression: with ``from __future__ import annotations`` the agent's ``-> None``
methods failed dbus-fast's signature parsing, so the agent never registered.
"""

import pytest

from src.ble.pairing import pairing_agent_class

EXPECTED = {
    "Release": ("", ""),
    "RequestPinCode": ("o", "s"),
    "DisplayPinCode": ("os", ""),
    "RequestPasskey": ("o", "u"),
    "DisplayPasskey": ("ouq", ""),
    "RequestConfirmation": ("ou", ""),
    "RequestAuthorization": ("o", ""),
    "AuthorizeService": ("os", ""),
    "Cancel": ("", ""),
}


# The agent tries dbus_next first (bless uses it), then dbus_fast.
@pytest.mark.parametrize("library", ["dbus_next.service", "dbus_fast.service"])
def test_agent_builds_with_bluez_agent1_signatures(library: str) -> None:
    dbus_service = pytest.importorskip(library)
    agent = pairing_agent_class(dbus_service.ServiceInterface, dbus_service.method)()
    intro = agent.introspect()

    assert intro.name == "org.bluez.Agent1"
    got = {
        m.name: (
            "".join(a.signature for a in m.in_args),
            "".join(a.signature for a in m.out_args),
        )
        for m in intro.methods
    }
    assert got == EXPECTED
