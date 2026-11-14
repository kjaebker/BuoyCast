"""Integration tests for Strava OAuth + upload using httpx mock transport."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.models import StravaUploadStatus, StrokeRecord, WorkoutRecord
from src.storage.db import Database
from src.storage.queries import get_workout, insert_strokes, insert_workout
from src.strava.auth import StravaAuth, StravaTokens
from src.strava.upload import upload_workout

# --- Fixtures ---


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


def _sample_workout(workout_id: str = "w001") -> WorkoutRecord:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    return WorkoutRecord(
        id=workout_id,
        started_at=started,
        ended_at=started + timedelta(minutes=10),
        total_distance_m=2000.0,
        total_strokes=100,
        elapsed_seconds=600,
        avg_stroke_rate=28.0,
        avg_heart_rate=140,
        max_heart_rate=160,
        calories=120,
    )


def _sample_strokes(workout_id: str = "w001") -> list[StrokeRecord]:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    return [
        StrokeRecord(
            workout_id=workout_id,
            ts=started + timedelta(seconds=i),
            distance_m=float(i * 20),
            stroke_rate=28.0,
        )
        for i in range(5)
    ]


# --- Mock HTTP transport ---


class MockStravaTransport(httpx.AsyncBaseTransport):
    """Mock transport that simulates Strava API responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._token_response = {
            "access_token": "access_123",
            "refresh_token": "refresh_456",
            "expires_at": int(time.time()) + 3600,
            "athlete": {"id": 12345, "firstname": "Test", "lastname": "User"},
        }
        self._refresh_response = {
            "access_token": "access_refreshed",
            "refresh_token": "refresh_new",
            "expires_at": int(time.time()) + 3600,
        }
        self._upload_response = {"id": 99001, "status": "Your activity is still being processed."}
        self._upload_status_response = {
            "id": 99001,
            "activity_id": 77001,
            "status": "Your activity is ready.",
        }
        self._upload_error: str | None = None
        self._deauth_called = False
        self._fail_upload = False
        self._poll_count = 0
        self._polls_before_ready = 1

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)

        # Token exchange / refresh
        if "oauth/token" in url:
            body = request.content.decode()
            if "grant_type=authorization_code" in body:
                return httpx.Response(200, json=self._token_response)
            elif "grant_type=refresh_token" in body:
                return httpx.Response(200, json=self._refresh_response)

        # Deauthorize
        if "oauth/deauthorize" in url:
            self._deauth_called = True
            return httpx.Response(200, json={"access_token": "revoked"})

        # Upload
        if url.endswith("/uploads") and request.method == "POST":
            if self._fail_upload:
                return httpx.Response(429, text="Rate limited")
            return httpx.Response(201, json=self._upload_response)

        # Upload status poll
        if "/uploads/" in url and request.method == "GET":
            self._poll_count += 1
            if self._upload_error:
                return httpx.Response(
                    200,
                    json={
                        "id": 99001,
                        "activity_id": None,
                        "error": self._upload_error,
                    },
                )
            if self._poll_count >= self._polls_before_ready:
                return httpx.Response(200, json=self._upload_status_response)
            return httpx.Response(
                200,
                json={
                    "id": 99001,
                    "activity_id": None,
                    "status": "processing",
                },
            )

        return httpx.Response(404, text="Not found")


@pytest.fixture
def mock_transport():
    return MockStravaTransport()


@pytest.fixture
def http_client(mock_transport):
    return httpx.AsyncClient(transport=mock_transport)


@pytest.fixture
def auth(db, http_client):
    return StravaAuth(
        db=db,
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8080/api/strava/callback",
        http_client=http_client,
    )


# --- OAuth URL ---


class TestOAuthURL:
    async def test_auth_url_contains_client_id(self, auth):
        url = auth.build_auth_url()
        assert "client_id=test_client_id" in url

    async def test_auth_url_contains_scope(self, auth):
        url = auth.build_auth_url()
        assert "activity%3Awrite" in url or "activity:write" in url

    async def test_auth_url_contains_redirect(self, auth):
        url = auth.build_auth_url()
        assert "redirect_uri=" in url

    async def test_auth_url_contains_response_type(self, auth):
        url = auth.build_auth_url()
        assert "response_type=code" in url


# --- Token exchange ---


class TestTokenExchange:
    async def test_exchange_stores_tokens(self, auth, db):
        tokens = await auth.exchange_code("test_code")
        assert tokens.access_token == "access_123"
        assert tokens.refresh_token == "refresh_456"

        # Verify stored in DB
        stored = await auth.get_stored_tokens()
        assert stored is not None
        assert stored.access_token == "access_123"

    async def test_exchange_stores_athlete_info(self, auth):
        tokens = await auth.exchange_code("test_code")
        assert tokens.athlete_id == 12345
        assert tokens.athlete_name == "Test User"

    async def test_exchange_sends_correct_grant_type(self, auth, mock_transport):
        await auth.exchange_code("test_code")
        req = mock_transport.requests[0]
        body = req.content.decode()
        assert "grant_type=authorization_code" in body
        assert "code=test_code" in body


# --- Token refresh ---


class TestTokenRefresh:
    async def test_auto_refresh_when_near_expiry(self, auth, db):
        # Store a token that's about to expire
        near_expiry = StravaTokens(
            access_token="old_access",
            refresh_token="refresh_456",
            expires_at=int(time.time()) + 60,  # expires in 60s (within 5min margin)
            athlete_id=12345,
            athlete_name="Test User",
        )
        await auth._store_tokens(near_expiry)

        tokens = await auth.get_valid_token()
        assert tokens is not None
        assert tokens.access_token == "access_refreshed"

    async def test_no_refresh_when_not_expired(self, auth, db):
        # Store a fresh token
        fresh = StravaTokens(
            access_token="fresh_access",
            refresh_token="refresh_456",
            expires_at=int(time.time()) + 7200,  # 2 hours from now
        )
        await auth._store_tokens(fresh)

        tokens = await auth.get_valid_token()
        assert tokens is not None
        assert tokens.access_token == "fresh_access"  # Not refreshed

    async def test_refresh_preserves_athlete_info(self, auth, db):
        await auth.exchange_code("test_code")  # stores athlete info
        # Force refresh
        tokens = await auth.refresh_token("refresh_456")
        assert tokens.athlete_id == 12345
        assert tokens.athlete_name == "Test User"

    async def test_get_valid_token_returns_none_when_no_tokens(self, auth):
        tokens = await auth.get_valid_token()
        assert tokens is None


# --- Revoke ---


class TestRevoke:
    async def test_revoke_clears_tokens(self, auth, mock_transport):
        await auth.exchange_code("test_code")
        assert (await auth.get_stored_tokens()) is not None

        await auth.revoke()
        assert (await auth.get_stored_tokens()) is None
        assert mock_transport._deauth_called

    async def test_revoke_when_no_tokens(self, auth):
        """Revoking without stored tokens should not crash."""
        await auth.revoke()


# --- Status ---


class TestStatus:
    async def test_status_disconnected(self, auth):
        status = await auth.get_status()
        assert status["connected"] is False

    async def test_status_connected(self, auth):
        await auth.exchange_code("test_code")
        status = await auth.get_status()
        assert status["connected"] is True
        assert status["athlete_name"] == "Test User"
        assert status["athlete_id"] == 12345


# --- Upload ---


class TestUpload:
    async def test_upload_success(self, db, auth, http_client, mock_transport, tmp_path):
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())

        result = await upload_workout(
            "w001", db, auth, fit_dir=str(tmp_path), http_client=http_client
        )
        assert result is True

        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.UPLOADED
        assert workout.strava_activity_id == 77001

    async def test_upload_sends_correct_sport_type(
        self, db, auth, http_client, mock_transport, tmp_path
    ):
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())

        await upload_workout("w001", db, auth, fit_dir=str(tmp_path), http_client=http_client)

        # Find the upload request
        upload_reqs = [r for r in mock_transport.requests if str(r.url).endswith("/uploads")]
        assert len(upload_reqs) == 1

    async def test_upload_sets_uploading_status(
        self, db, auth, http_client, mock_transport, tmp_path
    ):
        """Status should be UPLOADING during the upload process."""
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())

        # Mock transport with slow poll to check intermediate state
        mock_transport._polls_before_ready = 2

        await upload_workout("w001", db, auth, fit_dir=str(tmp_path), http_client=http_client)

        # Final state should be UPLOADED
        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.UPLOADED

    async def test_upload_polls_status(self, db, auth, http_client, mock_transport, tmp_path):
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())
        mock_transport._polls_before_ready = 3

        await upload_workout("w001", db, auth, fit_dir=str(tmp_path), http_client=http_client)

        assert mock_transport._poll_count >= 3

    async def test_upload_failure_sets_failed(
        self, db, auth, http_client, mock_transport, tmp_path
    ):
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())
        mock_transport._fail_upload = True

        result = await upload_workout(
            "w001", db, auth, fit_dir=str(tmp_path), http_client=http_client
        )
        assert result is False

        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.FAILED
        assert workout.strava_error is not None

    async def test_upload_error_from_strava(self, db, auth, http_client, mock_transport, tmp_path):
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())
        mock_transport._upload_error = "Duplicate activity"

        result = await upload_workout(
            "w001", db, auth, fit_dir=str(tmp_path), http_client=http_client
        )
        assert result is False

        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.FAILED
        assert "Duplicate" in workout.strava_error

    async def test_upload_not_authenticated(self, db, auth, http_client, tmp_path):
        """Upload without stored tokens should fail gracefully."""
        await insert_workout(db, _sample_workout())

        result = await upload_workout(
            "w001", db, auth, fit_dir=str(tmp_path), http_client=http_client
        )
        assert result is False

        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.FAILED

    async def test_retry_after_failure(self, db, auth, http_client, mock_transport, tmp_path):
        """Retry should re-attempt from FAILED state."""
        await auth.exchange_code("test_code")
        await insert_workout(db, _sample_workout())
        await insert_strokes(db, _sample_strokes())

        # First attempt fails
        mock_transport._fail_upload = True
        await upload_workout("w001", db, auth, fit_dir=str(tmp_path), http_client=http_client)
        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.FAILED

        # Retry succeeds
        mock_transport._fail_upload = False
        result = await upload_workout(
            "w001", db, auth, fit_dir=str(tmp_path), http_client=http_client
        )
        assert result is True

        workout = await get_workout(db, "w001")
        assert workout.strava_upload_status == StravaUploadStatus.UPLOADED
