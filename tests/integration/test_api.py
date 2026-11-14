"""Integration tests for REST API + WebSocket endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.events import EventBus, EventType
from src.models import (
    RowingMetrics,
    StravaUploadStatus,
    StrokeRecord,
    WorkoutRecord,
)
from src.storage.db import Database
from src.storage.queries import get_workout, insert_strokes, insert_workout
from src.web.server import create_app
from src.workout.state import WorkoutStateMachine

# --- Fixtures ---


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sm(event_bus):
    return WorkoutStateMachine(event_bus)


@pytest.fixture
def app(event_bus, sm, db):
    return create_app(event_bus=event_bus, state_machine=sm, db=db)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _sample_workout(
    workout_id: str = "w001",
    ended: bool = True,
) -> WorkoutRecord:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    return WorkoutRecord(
        id=workout_id,
        started_at=started,
        ended_at=started + timedelta(minutes=10) if ended else None,
        total_distance_m=2000.0,
        total_strokes=100,
        elapsed_seconds=600,
        avg_pace_s_per_500m=150.0,
        avg_stroke_rate=28.0,
        avg_power_watts=150.0,
        avg_heart_rate=140,
        max_heart_rate=160,
        calories=120,
    )


def _sample_strokes(workout_id: str = "w001", count: int = 5) -> list[StrokeRecord]:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    return [
        StrokeRecord(
            workout_id=workout_id,
            ts=started + timedelta(seconds=i),
            distance_m=float(i * 20),
            stroke_rate=28.0,
            power_watts=150.0,
            pace_s_per_500m=150.0,
            heart_rate_bpm=140,
        )
        for i in range(count)
    ]


# --- Status endpoint ---


class TestStatusEndpoint:
    async def test_status_returns_all_fields(self, client):
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "s4_connected" in data
        assert "tickr_connected" in data
        assert "workout_state" in data
        assert "uptime_seconds" in data
        assert "last_metrics_ts" in data

    async def test_status_default_values(self, client):
        resp = await client.get("/api/status")
        data = resp.json()
        assert data["s4_connected"] is False
        assert data["tickr_connected"] is False
        assert data["workout_state"] == "IDLE"
        assert data["uptime_seconds"] >= 0
        assert data["last_metrics_ts"] is None

    async def test_status_reflects_workout_state(self, client, sm):
        await sm.start()
        resp = await client.get("/api/status")
        assert resp.json()["workout_state"] == "ACTIVE"


# --- Workout CRUD ---


class TestWorkoutList:
    async def test_empty_list(self, client):
        resp = await client.get("/api/workouts")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_workouts(self, client, db):
        await insert_workout(db, _sample_workout("w001"))
        await insert_workout(db, _sample_workout("w002"))
        resp = await client.get("/api/workouts")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_list_pagination(self, client, db):
        for i in range(5):
            await insert_workout(db, _sample_workout(f"w{i:03d}"))
        resp = await client.get("/api/workouts?limit=2&offset=0")
        assert len(resp.json()) == 2
        resp2 = await client.get("/api/workouts?limit=2&offset=2")
        assert len(resp2.json()) == 2


class TestWorkoutDetail:
    async def test_get_existing(self, client, db):
        await insert_workout(db, _sample_workout("w001"))
        resp = await client.get("/api/workouts/w001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "w001"
        assert data["total_distance_m"] == 2000.0

    async def test_get_nonexistent(self, client):
        resp = await client.get("/api/workouts/nope")
        assert resp.status_code == 404


class TestWorkoutStrokes:
    async def test_get_strokes(self, client, db):
        await insert_workout(db, _sample_workout("w001"))
        await insert_strokes(db, _sample_strokes("w001", count=3))
        resp = await client.get("/api/workouts/w001/strokes")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_get_strokes_nonexistent(self, client):
        resp = await client.get("/api/workouts/nope/strokes")
        assert resp.status_code == 404


class TestWorkoutDelete:
    async def test_delete_existing(self, client, db):
        await insert_workout(db, _sample_workout("w001"))
        resp = await client.delete("/api/workouts/w001")
        assert resp.status_code == 200
        assert (await get_workout(db, "w001")) is None

    async def test_delete_nonexistent(self, client):
        resp = await client.delete("/api/workouts/nope")
        assert resp.status_code == 404


# --- Workout control ---


class TestWorkoutControl:
    async def test_start(self, client):
        resp = await client.post("/api/workout/start")
        assert resp.status_code == 200
        assert resp.json()["state"] == "ACTIVE"

    async def test_pause(self, client, sm):
        await sm.start()
        resp = await client.post("/api/workout/pause")
        assert resp.status_code == 200
        assert resp.json()["state"] == "PAUSED"

    async def test_resume(self, client, sm):
        await sm.start()
        await sm.pause()
        resp = await client.post("/api/workout/resume")
        assert resp.status_code == 200
        assert resp.json()["state"] == "ACTIVE"

    async def test_end(self, client, sm):
        await sm.start()
        resp = await client.post("/api/workout/end")
        assert resp.status_code == 200
        assert resp.json()["state"] == "SUMMARY"

    async def test_invalid_pause_from_idle_returns_409(self, client):
        resp = await client.post("/api/workout/pause")
        assert resp.status_code == 409

    async def test_invalid_start_from_active_returns_409(self, client, sm):
        await sm.start()
        resp = await client.post("/api/workout/start")
        assert resp.status_code == 409

    async def test_invalid_resume_from_active_returns_409(self, client, sm):
        await sm.start()
        resp = await client.post("/api/workout/resume")
        assert resp.status_code == 409

    async def test_reset(self, client, sm):
        await sm.start()
        await sm.end()
        resp = await client.post("/api/workout/reset")
        assert resp.status_code == 200
        assert resp.json()["state"] == "IDLE"

    async def test_reset_from_idle_returns_409(self, client):
        resp = await client.post("/api/workout/reset")
        assert resp.status_code == 409

    async def test_full_control_flow_with_reset(self, client):
        resp = await client.post("/api/workout/start")
        assert resp.json()["state"] == "ACTIVE"
        resp = await client.post("/api/workout/pause")
        assert resp.json()["state"] == "PAUSED"
        resp = await client.post("/api/workout/resume")
        assert resp.json()["state"] == "ACTIVE"
        resp = await client.post("/api/workout/end")
        assert resp.json()["state"] == "SUMMARY"
        resp = await client.post("/api/workout/reset")
        assert resp.json()["state"] == "IDLE"
        # Should be able to start a new workout immediately
        resp = await client.post("/api/workout/start")
        assert resp.json()["state"] == "ACTIVE"


# --- Upload / skip ---


class TestUploadAndSkip:
    async def test_upload_returns_503_without_strava_auth(self, client, db):
        # When no Strava auth is configured, upload returns 503
        await insert_workout(db, _sample_workout("w001"))
        resp = await client.post("/api/workouts/w001/upload")
        assert resp.status_code == 503

    async def test_upload_nonexistent_returns_404(self, client):
        resp = await client.post("/api/workouts/nope/upload")
        assert resp.status_code == 404

    async def test_skip_workout(self, client, db):
        await insert_workout(db, _sample_workout("w001"))
        resp = await client.post("/api/workouts/w001/skip")
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"
        # Verify in DB
        w = await get_workout(db, "w001")
        assert w.strava_upload_status == StravaUploadStatus.SKIPPED

    async def test_skip_nonexistent_returns_404(self, client):
        resp = await client.post("/api/workouts/nope/skip")
        assert resp.status_code == 404


# --- WebSocket ---


class TestWebSocket:
    async def test_ws_connect_and_disconnect(self, app):
        """WebSocket client can connect and disconnect cleanly."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/live") as ws:
                # Connection established
                assert ws is not None

    async def test_ws_receives_metrics(self, app, event_bus):
        """WebSocket client receives metrics broadcast."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/live") as ws:
                # Emit a merged metrics event
                metrics = RowingMetrics(
                    timestamp=datetime.now(tz=UTC),
                    stroke_rate=28.0,
                    distance_m=100.0,
                )
                await event_bus.emit(EventType.MERGED_METRICS, data=metrics)

                # Give broadcast loop time to process
                await asyncio.sleep(0.05)

                # Receive the message
                msg = ws.receive_json(mode="text")
                assert msg["type"] == "metrics_update"
                assert msg["data"]["stroke_rate"] == 28.0

    async def test_ws_receives_state_change(self, app, event_bus, sm):
        """WebSocket client receives workout state change events."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/live") as ws:
                await sm.start()
                await asyncio.sleep(0.05)

                msg = ws.receive_json(mode="text")
                assert msg["type"] == "workout_started"
                assert msg["data"]["new_state"] == "ACTIVE"


# --- Recovery endpoint ---


class TestRecovery:
    async def test_recovery_returns_null_when_no_incomplete(self, client):
        """GET /api/recovery returns null when all workouts are complete."""
        resp = await client.get("/api/recovery")
        assert resp.status_code == 200
        assert resp.json() == {"workout": None}

    async def test_recovery_returns_incomplete_workout(self, client, db):
        """GET /api/recovery returns the incomplete workout."""
        workout = _sample_workout("w-incomplete", ended=False)
        await insert_workout(db, workout)

        resp = await client.get("/api/recovery")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workout"] is not None
        assert data["workout"]["id"] == "w-incomplete"
        assert data["workout"]["ended_at"] is None

    async def test_recovery_ignores_completed_workouts(self, client, db):
        """GET /api/recovery returns null when only completed workouts exist."""
        workout = _sample_workout("w-done", ended=True)
        await insert_workout(db, workout)

        resp = await client.get("/api/recovery")
        assert resp.status_code == 200
        assert resp.json() == {"workout": None}

    async def test_discard_sets_ended_at_and_skipped(self, client, db):
        """POST /api/recovery/{id}/discard closes the workout as SKIPPED."""
        workout = _sample_workout("w-orphan", ended=False)
        await insert_workout(db, workout)

        resp = await client.post("/api/recovery/w-orphan/discard")
        assert resp.status_code == 200
        assert resp.json()["status"] == "discarded"

        updated = await get_workout(db, "w-orphan")
        assert updated is not None
        assert updated.ended_at is not None
        assert updated.strava_upload_status == StravaUploadStatus.SKIPPED

    async def test_discard_404_for_unknown_id(self, client):
        """POST /api/recovery/{id}/discard returns 404 for unknown workout."""
        resp = await client.post("/api/recovery/nonexistent/discard")
        assert resp.status_code == 404

    async def test_recovery_absent_after_discard(self, client, db):
        """After discard, GET /api/recovery returns null."""
        workout = _sample_workout("w-gone", ended=False)
        await insert_workout(db, workout)

        await client.post("/api/recovery/w-gone/discard")

        resp = await client.get("/api/recovery")
        assert resp.json() == {"workout": None}


class TestUpdateEndpoints:
    """Tests for /api/system/update/check and /api/system/update."""

    async def test_check_update_returns_structure(self, client, monkeypatch):
        """GET /api/system/update/check returns the UpdateInfo shape."""
        from src.updates import UpdateInfo
        from src.web import server

        async def mock_check(repo):
            assert repo == "kjaebker/BuoyCast"
            return UpdateInfo(
                current_version="0.2.0",
                latest_version="0.3.0",
                update_available=True,
                release_notes="New stuff",
                release_url="https://example.invalid/r",
            )

        monkeypatch.setattr(server, "check_for_update", mock_check)

        resp = await client.get("/api/system/update/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_version"] == "0.2.0"
        assert data["latest_version"] == "0.3.0"
        assert data["update_available"] is True
        assert data["release_notes"] == "New stuff"
        assert data["can_self_update"] is False
        assert data["error"] is None

    async def test_trigger_update_without_helper_returns_503(self, client, monkeypatch, tmp_path):
        """POST /api/system/update returns 503 when not installed via install.sh."""
        from src.web import server

        monkeypatch.setattr(server, "UPDATE_HELPER", tmp_path / "missing")
        resp = await client.post("/api/system/update")
        assert resp.status_code == 503

    async def test_trigger_update_with_helper_returns_202(self, client, monkeypatch, tmp_path):
        """POST /api/system/update starts the helper when it is installed."""
        from src.web import server

        helper = tmp_path / "buoycast-update"
        helper.write_text("#!/bin/sh\n")
        monkeypatch.setattr(server, "UPDATE_HELPER", helper)
        ran = []

        async def fake_run_after(delay_s, *cmd):
            ran.append(cmd)

        monkeypatch.setattr(server, "_run_after", fake_run_after)

        resp = await client.post("/api/system/update")
        assert resp.status_code == 202
        assert resp.json()["status"] == "update_started"
        await asyncio.sleep(0)
        assert ran == [("systemctl", "start", "--no-block", "buoycast-update.service")]


class TestSpaStaticServing:
    """The SPA catch-all must never serve files outside dashboard/dist."""

    @pytest.fixture
    def dist_app(self, tmp_path):
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>spa</html>")
        (dist / "app.js").write_text("console.log(1)")
        (tmp_path / "config.toml").write_text('client_secret = "s3cret"')
        return create_app(dist_dir=dist)

    async def test_serves_files_inside_dist(self, dist_app):
        transport = ASGITransport(app=dist_app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            assert (await c.get("/app.js")).text == "console.log(1)"
            assert (await c.get("/some/route")).text == "<html>spa</html>"

    @pytest.mark.parametrize(
        "path", ["/..%2Fconfig.toml", "/..%2F..%2Fconfig.toml", "/%2E%2E/config.toml"]
    )
    async def test_rejects_path_traversal(self, dist_app, path):
        transport = ASGITransport(app=dist_app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get(path)
        assert "s3cret" not in resp.text
