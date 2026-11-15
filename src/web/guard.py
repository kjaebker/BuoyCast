"""Stops other web pages from controlling BuoyCast through the viewer's browser.

BuoyCast has no login: anyone who can reach it on the network can use it
(see SECURITY.md). What this guard prevents is a page on some *other* site,
open in a browser on that network, quietly sending commands to the Pi
(reboot, update, delete workouts). Two attacks are covered:

- Cross-site requests. Browsers attach an ``Origin`` header to every POST,
  PUT, PATCH and DELETE and to WebSocket handshakes. Those are rejected
  unless the origin is the address the request was sent to. Requests
  without an Origin header (curl, scripts, the Strava OAuth redirect) are
  allowed, unless ``Sec-Fetch-Site`` says they came from another site.
- DNS rebinding. An attacker's domain can be made to resolve to the Pi's
  address, which makes the attacker's page "same-origin" with it. The
  browser still sends the attacker's domain in the ``Host`` header, so
  requests are only accepted for hosts that can't belong to an attacker:
  IP addresses, single-label names (``localhost``, ``raspberrypi``),
  ``*.local`` mDNS names, and anything listed in ``[server] allowed_hosts``.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def _split_host(host: str) -> tuple[str, int | None]:
    """Split a Host header value into (lowercased hostname, port or None)."""
    parts = urlsplit(f"//{host}")
    try:
        port = parts.port
    except ValueError:
        port = None
    return (parts.hostname or "").lower(), port


def host_allowed(hostname: str, extra: Iterable[str] = ()) -> bool:
    """True when *hostname* can't be an attacker-controlled DNS name."""
    if not hostname:
        return False
    if hostname in {h.lower() for h in extra}:
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    return "." not in hostname or hostname.endswith(".local")


def _origin_matches_host(origin: str, host: str, scheme: str) -> bool:
    """True when the Origin header names the same host and port as Host."""
    o = urlsplit(origin)
    if not o.hostname:
        return False
    try:
        o_port = o.port or _DEFAULT_PORTS.get(o.scheme)
    except ValueError:
        return False
    h_name, h_port = _split_host(host)
    h_port = h_port or _DEFAULT_PORTS.get(scheme)
    return o.hostname.lower() == h_name and o_port == h_port


class RequestGuard:
    """ASGI middleware applying the Host and cross-site checks above."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] = ()) -> None:
        self.app = app
        self.allowed_hosts = tuple(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        reason = self._reject_reason(scope, headers, host)
        if reason is None:
            await self.app(scope, receive, send)
            return

        logger.warning(
            "Blocked %s %s (host=%r origin=%r): %s",
            scope.get("method", "WS"),
            scope.get("path"),
            host,
            headers.get("origin"),
            reason,
        )
        if scope["type"] == "websocket":
            # Refuse the handshake; Starlette turns this into an HTTP 403.
            await send({"type": "websocket.close", "code": 1008})
            return
        status = 400 if reason.startswith("host") else 403
        await PlainTextResponse(reason, status_code=status)(scope, receive, send)

    def _reject_reason(self, scope: Scope, headers: dict[str, str], host: str) -> str | None:
        hostname, _ = _split_host(host)
        if not host_allowed(hostname, self.allowed_hosts):
            return f"host {hostname!r} not allowed; add it to [server] allowed_hosts"

        is_ws = scope["type"] == "websocket"
        if not is_ws and scope.get("method", "GET").upper() in _SAFE_METHODS:
            return None

        origin = headers.get("origin")
        if origin is not None:
            if origin == "null" or not _origin_matches_host(origin, host, scope["scheme"]):
                return "cross-site request blocked"
            return None
        if headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            return "cross-site request blocked"
        return None
