"""Tests for the cross-site / DNS-rebinding guard (src/web/guard.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.events import EventBus
from src.storage.db import Database
from src.web.guard import host_allowed
from src.web.server import create_app
from src.workout.state import WorkoutStateMachine

PI = "http://buoycast.local:8080"


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


@pytest.fixture
def client(db):
    bus = EventBus()
    app = create_app(
        event_bus=bus,
        state_machine=WorkoutStateMachine(bus),
        db=db,
        allowed_hosts=["rower.example.com"],
    )
    with TestClient(app, base_url=PI) as tc:
        yield tc


class TestHostAllowed:
    @pytest.mark.parametrize(
        "host",
        ["localhost", "raspberrypi", "buoycast.local", "192.168.1.40", "::1", "testserver"],
    )
    def test_allowed(self, host):
        assert host_allowed(host)

    @pytest.mark.parametrize("host", ["evil.com", "buoycast.local.evil.com", "10.0.0.1.nip.io", ""])
    def test_rejected(self, host):
        assert not host_allowed(host)

    def test_configured_extra_host(self):
        assert host_allowed("rower.example.com", ["Rower.Example.com"])


class TestCrossSite:
    def test_same_origin_post_allowed(self, client):
        r = client.post("/api/workout/start", headers={"Origin": PI})
        assert r.status_code == 200

    def test_post_without_origin_allowed(self, client):
        """curl and scripts send no Origin header."""
        assert client.post("/api/workout/start").status_code == 200

    @pytest.mark.parametrize(
        "origin",
        [
            "https://evil.com",
            "null",
            "http://buoycast.local:9999",  # other port = other origin
            "http://buoycast.local",  # default port 80 != 8080
        ],
    )
    def test_cross_site_post_blocked(self, client, origin):
        r = client.post("/api/system/restart", headers={"Origin": origin})
        assert r.status_code == 403

    @pytest.mark.parametrize("method", ["put", "delete"])
    def test_other_unsafe_methods_blocked(self, client, method):
        url = "/api/settings" if method == "put" else "/api/workouts/x"
        r = client.request(method.upper(), url, headers={"Origin": "https://evil.com"}, json={})
        assert r.status_code == 403

    def test_sec_fetch_site_cross_site_blocked_without_origin(self, client):
        r = client.post("/api/workout/start", headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403

    def test_cross_site_get_still_allowed(self, client):
        """Top-level navigations (e.g. the Strava OAuth redirect) are GETs."""
        r = client.get("/api/status", headers={"Origin": "https://evil.com"})
        assert r.status_code == 200

    def test_no_cors_headers(self, client):
        r = client.get("/api/status", headers={"Origin": "https://evil.com"})
        assert "access-control-allow-origin" not in r.headers


class TestHost:
    def test_rebinding_host_rejected_even_for_get(self, client):
        r = client.get("/api/status", headers={"Host": "evil.com:8080"})
        assert r.status_code == 400

    def test_rebinding_same_origin_post_rejected(self, client):
        r = client.post(
            "/api/system/restart",
            headers={"Host": "evil.com:8080", "Origin": "http://evil.com:8080"},
        )
        assert r.status_code == 400

    def test_ip_host_allowed(self, client):
        r = client.post(
            "/api/workout/start",
            headers={"Host": "192.168.1.40:8080", "Origin": "http://192.168.1.40:8080"},
        )
        assert r.status_code == 200

    def test_configured_host_allowed(self, client):
        r = client.get("/api/status", headers={"Host": "rower.example.com"})
        assert r.status_code == 200


class TestWebSocket:
    def test_same_origin_ws_allowed(self, client):
        # The test client always sends Host: testserver for WebSockets.
        with client.websocket_connect("/ws/live", headers={"Origin": "http://testserver"}):
            pass

    def test_cross_site_ws_rejected(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/live", headers={"Origin": "https://evil.com"}):
                pass
