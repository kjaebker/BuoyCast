"""BlueZ pairing agent (org.bluez.Agent1) that auto-accepts bond requests.

dbus-next and dbus-fast read D-Bus signatures from method annotations, so
this module deliberately does NOT use ``from __future__ import annotations``.
With it, ``-> None`` reaches the library as the string ``"None"``, which it
evaluates to Python ``None`` and rejects, and the agent never registers.
Without it, ``None`` means "no return value" and each quoted type code
("o", "s", "u", "q") is passed through as the signature.
"""

from typing import Any


def pairing_agent_class(service_interface: type, method: Any) -> type:
    """Build the Agent1 interface class from the D-Bus library's primitives.

    The library is passed in because it is imported lazily (Linux only).
    """

    class PairingAgent(service_interface):  # type: ignore[misc, valid-type]
        """BlueZ Agent1 implementation: auto-accepts everything."""

        def __init__(self) -> None:
            super().__init__("org.bluez.Agent1")

        @method()  # type: ignore[misc]
        def Release(self) -> None:  # noqa: N802
            pass

        @method()  # type: ignore[misc]
        def RequestPinCode(self, device: "o") -> "s":  # noqa: N802, F821
            return "0000"

        @method()  # type: ignore[misc]
        def DisplayPinCode(self, device: "o", pincode: "s") -> None:  # noqa: N802, F821
            pass

        @method()  # type: ignore[misc]
        def RequestPasskey(self, device: "o") -> "u":  # noqa: N802, F821
            return 0

        @method()  # type: ignore[misc]
        def DisplayPasskey(self, device: "o", passkey: "u", entered: "q") -> None:  # noqa: N802, F821
            pass

        @method()  # type: ignore[misc]
        def RequestConfirmation(self, device: "o", passkey: "u") -> None:  # noqa: N802, F821
            pass  # auto-accept

        @method()  # type: ignore[misc]
        def RequestAuthorization(self, device: "o") -> None:  # noqa: N802, F821
            pass  # auto-accept

        @method()  # type: ignore[misc]
        def AuthorizeService(self, device: "o", uuid: "s") -> None:  # noqa: N802, F821
            pass  # auto-accept

        @method()  # type: ignore[misc]
        def Cancel(self) -> None:  # noqa: N802
            pass

    return PairingAgent
