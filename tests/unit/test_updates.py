"""Tests for release-based update checking."""

import httpx
import pytest

from src import updates
from src.updates import check_for_update, parse_version


def _transport(status: int, payload: dict | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/owner/repo/releases/latest"
        return httpx.Response(status, json=payload or {})

    return httpx.MockTransport(handler)


class TestParseVersion:
    def test_orders_numerically(self):
        assert parse_version("v0.10.0") > parse_version("v0.9.9")

    def test_final_sorts_after_prerelease(self):
        assert parse_version("1.2.3") > parse_version("1.2.3-rc1")

    def test_local_build_is_not_prerelease(self):
        assert parse_version("0.0.0+unknown") == (0, 0, 0, True)

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_version("latest")


class TestCheckForUpdate:
    @pytest.fixture(autouse=True)
    def _pin_version(self, monkeypatch):
        monkeypatch.setattr(updates, "current_version", lambda: "0.2.0")

    async def test_newer_release_available(self):
        payload = {"tag_name": "v0.3.0", "body": "notes", "html_url": "https://x.invalid"}
        info = await check_for_update("owner/repo", transport=_transport(200, payload))
        assert info.update_available is True
        assert info.latest_version == "0.3.0"
        assert info.release_notes == "notes"
        assert info.error is None

    async def test_same_release_is_up_to_date(self):
        info = await check_for_update("owner/repo", transport=_transport(200, {"tag_name": "v0.2.0"}))
        assert info.update_available is False
        assert info.error is None

    async def test_no_releases(self):
        info = await check_for_update("owner/repo", transport=_transport(404))
        assert info.update_available is False
        assert info.error == "No releases published yet"

    async def test_network_error_is_reported_not_raised(self):
        def boom(request):
            raise httpx.ConnectError("offline")

        info = await check_for_update("owner/repo", transport=httpx.MockTransport(boom))
        assert info.update_available is False
        assert "Could not reach GitHub" in info.error
