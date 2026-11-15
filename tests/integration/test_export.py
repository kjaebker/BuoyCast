"""Tests for the HTTP exporter (src/export/http.py) and its API routes."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config import ExportSettings
from src.events import EventBus, EventType
from src.export.http import FIT_CONTENT_TYPE, ExportNotConfiguredError, WorkoutExporter
from src.export.payload import SCHEMA_VERSION
from src.models import ExportStatus, StrokeRecord, WorkoutRecord
from src.storage.db import Database
from src.storage.queries import get_workout, insert_strokes, insert_workout, update_workout
from src.web.server import create_app

URL = "https://training.example.com/ingest/buoycast"


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


class Receiver:
    """httpx mock transport that records requests and replays canned statuses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []  # popped per request; empty = 200
        self.raise_error: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, text="nope" if status >= 400 else "ok")


@pytest.fixture
def receiver():
    return Receiver()


@pytest.fixture
def client(receiver):
    return httpx.AsyncClient(transport=httpx.MockTransport(receiver.handler))


def _settings(**kw) -> ExportSettings:
    base = {"url": URL, "token": "s3cret", "retry_interval_s": 0.05}
    base.update(kw)
    return ExportSettings(**base)


async def _add_workout(
    db: Database,
    workout_id: str = "w001",
    distance: float = 2000.0,
    ended: bool = True,
    minutes_ago: int = 30,
) -> WorkoutRecord:
    started = datetime(2026, 11, 14, 7, 0, tzinfo=UTC) - timedelta(minutes=minutes_ago)
    w = WorkoutRecord(
        id=workout_id,
        started_at=started,
        ended_at=started + timedelta(minutes=10) if ended else None,
        total_distance_m=distance,
        total_strokes=220,
        elapsed_seconds=600,
        avg_stroke_rate=22.0,
        avg_heart_rate=140,
        max_heart_rate=158,
        calories=120,
    )
    await insert_workout(db, w)
    await insert_strokes(
        db,
        [
            StrokeRecord(
                workout_id=workout_id,
                ts=started + timedelta(seconds=i),
                distance_m=float(i * 4),
                stroke_rate=22.0,
                power_watts=150.0,
                pace_s_per_500m=125.0,
                heart_rate_bpm=140 + i,
                rr_intervals_ms=[430],
            )
            for i in range(5)
        ],
    )
    return w


def _exporter(db, client, bus=None, **kw) -> WorkoutExporter:
    min_distance = kw.pop("min_distance_m", 100.0)
    return WorkoutExporter(
        bus or EventBus(),
        db,
        _settings(**kw),
        min_distance_m=min_distance,
        http_client=client,
        version="9.9.9",
    )


class TestRequest:
    async def test_json_post_has_headers_and_payload(self, db, client, receiver):
        await _add_workout(db)
        await _exporter(db, client).sweep()

        assert len(receiver.requests) == 1
        req = receiver.requests[0]
        assert req.method == "POST"
        assert str(req.url) == URL
        assert req.headers["authorization"] == "Bearer s3cret"
        assert req.headers["idempotency-key"] == "w001"
        assert req.headers["content-type"] == "application/json"
        assert req.headers["user-agent"] == "BuoyCast/9.9.9"

        body = json.loads(req.content)
        assert body["schema_version"] == SCHEMA_VERSION
        assert body["source"] == {"app": "buoycast", "version": "9.9.9"}
        assert body["workout"]["id"] == "w001"
        assert body["workout"]["sub_sport"] == "indoor_rowing"
        assert body["workout"]["avg_heart_rate"] == 140
        assert len(body["samples"]) == 5
        assert body["samples"][2]["heart_rate_bpm"] == 142

    async def test_no_token_means_no_auth_header(self, db, client, receiver):
        await _add_workout(db)
        await _exporter(db, client, token="").sweep()
        assert "authorization" not in receiver.requests[0].headers

    async def test_include_hr_false_strips_heart_rate(self, db, client, receiver):
        await _add_workout(db)
        await _exporter(db, client, include_hr=False).sweep()
        body = json.loads(receiver.requests[0].content)
        assert body["workout"]["avg_heart_rate"] is None
        assert body["workout"]["max_heart_rate"] is None
        assert all(s["heart_rate_bpm"] is None for s in body["samples"])
        assert all(s["rr_intervals_ms"] is None for s in body["samples"])

    async def test_fit_format_sends_fit_bytes(self, db, client, receiver, tmp_path):
        await _add_workout(db)
        exporter = WorkoutExporter(
            EventBus(), db, _settings(format="fit"), fit_dir=tmp_path, http_client=client
        )
        await exporter.sweep()
        req = receiver.requests[0]
        assert req.headers["content-type"] == FIT_CONTENT_TYPE
        assert req.content[8:12] == b".FIT"  # FIT header signature


class TestStatus:
    async def test_success_marks_sent(self, db, client):
        await _add_workout(db)
        await _exporter(db, client).sweep()
        w = await get_workout(db, "w001")
        assert w.export_status == ExportStatus.SENT
        assert w.export_attempts == 1
        assert w.exported_at is not None
        assert w.export_error is None

    @pytest.mark.parametrize("status", [500, 503, 429, 408])
    async def test_retryable_status_marks_failed(self, db, client, receiver, status):
        receiver.statuses = [status]
        await _add_workout(db)
        await _exporter(db, client).sweep()
        w = await get_workout(db, "w001")
        assert w.export_status == ExportStatus.FAILED
        assert w.export_error.startswith(f"HTTP {status}")

    @pytest.mark.parametrize("status", [400, 401, 404, 422])
    async def test_client_error_marks_rejected_and_is_not_retried(
        self, db, client, receiver, status
    ):
        receiver.statuses = [status]
        await _add_workout(db)
        exporter = _exporter(db, client)
        await exporter.sweep()
        await exporter.sweep()
        assert len(receiver.requests) == 1
        assert (await get_workout(db, "w001")).export_status == ExportStatus.REJECTED

    async def test_network_error_marks_failed(self, db, client, receiver):
        receiver.raise_error = httpx.ConnectError("no route to host")
        await _add_workout(db)
        await _exporter(db, client).sweep()
        w = await get_workout(db, "w001")
        assert w.export_status == ExportStatus.FAILED
        assert "ConnectError" in w.export_error

    async def test_failed_is_retried_on_next_sweep(self, db, client, receiver):
        receiver.statuses = [503]
        await _add_workout(db)
        exporter = _exporter(db, client)
        await exporter.sweep()
        await exporter.sweep()
        w = await get_workout(db, "w001")
        assert w.export_status == ExportStatus.SENT
        assert w.export_attempts == 2

    async def test_short_workout_is_skipped_without_request(self, db, client, receiver):
        await _add_workout(db, distance=40.0)
        await _exporter(db, client).sweep()
        assert receiver.requests == []
        w = await get_workout(db, "w001")
        assert w.export_status == ExportStatus.SKIPPED
        assert "100 m" in w.export_error

    async def test_unfinished_workout_is_not_sent(self, db, client, receiver):
        await _add_workout(db, ended=False)
        await _exporter(db, client).sweep()
        assert receiver.requests == []

    async def test_sent_and_skipped_are_left_alone(self, db, client, receiver):
        await _add_workout(db, "a", minutes_ago=60)
        await _add_workout(db, "b", minutes_ago=30)
        await update_workout(db, "a", export_status=ExportStatus.SENT)
        await update_workout(db, "b", export_status=ExportStatus.SKIPPED)
        await _exporter(db, client).sweep()
        assert receiver.requests == []

    async def test_auto_send_off_sends_nothing(self, db, client, receiver):
        await _add_workout(db)
        await _exporter(db, client, auto_send=False).sweep()
        assert receiver.requests == []

    async def test_sweep_sends_oldest_first_and_all_batches(self, db, client, receiver):
        for i in range(12):
            await _add_workout(db, f"w{i:02d}", minutes_ago=100 - i)
        await _exporter(db, client).sweep()
        assert [r.headers["idempotency-key"] for r in receiver.requests] == [
            f"w{i:02d}" for i in range(12)
        ]

    async def test_status_events_published(self, db, client):
        bus = EventBus()
        q = bus.subscribe(EventType.EXPORT_STATUS)
        await _add_workout(db)
        await _exporter(db, client, bus=bus).sweep()
        seen = [q.get_nowait().data["export_status"] for _ in range(q.qsize())]
        assert seen == ["SENDING", "SENT"]


class TestManualSend:
    async def test_manual_send_ignores_status_and_min_distance(self, db, client, receiver):
        await _add_workout(db, distance=40.0)
        await update_workout(db, "w001", export_status=ExportStatus.REJECTED)
        status = await _exporter(db, client, auto_send=False).send("w001")
        assert status == ExportStatus.SENT
        assert len(receiver.requests) == 1

    async def test_manual_send_unconfigured_raises(self, db, client):
        await _add_workout(db)
        exporter = WorkoutExporter(EventBus(), db, ExportSettings(), http_client=client)
        with pytest.raises(ExportNotConfiguredError):
            await exporter.send("w001")

    async def test_manual_send_unknown_workout_raises(self, db, client):
        with pytest.raises(LookupError):
            await _exporter(db, client).send("missing")


class TestLifecycle:
    async def test_workout_saved_event_triggers_send(self, db, client, receiver):
        bus = EventBus()
        exporter = _exporter(db, client, bus=bus, retry_interval_s=60)
        await exporter.start()
        try:
            await asyncio.sleep(0.01)  # initial sweep: nothing to send
            await _add_workout(db)
            await bus.emit(EventType.WORKOUT_SAVED, "w001")
            for _ in range(100):
                if receiver.requests:
                    break
                await asyncio.sleep(0.01)
            assert len(receiver.requests) == 1
        finally:
            await exporter.stop()

    async def test_start_resets_interrupted_send(self, db, client, receiver):
        await _add_workout(db)
        await update_workout(db, "w001", export_status=ExportStatus.SENDING)
        exporter = _exporter(db, client)
        await exporter.start()
        try:
            for _ in range(100):
                if (await get_workout(db, "w001")).export_status == ExportStatus.SENT:
                    break
                await asyncio.sleep(0.01)
            assert (await get_workout(db, "w001")).export_status == ExportStatus.SENT
        finally:
            await exporter.stop()

    async def test_unconfigured_start_is_noop(self, db):
        exporter = WorkoutExporter(EventBus(), db, ExportSettings())
        await exporter.start()
        await exporter.stop()


class TestMigration:
    async def test_existing_rows_become_skipped_new_rows_pending(self, tmp_path):
        from src.storage import db as dbmod

        path = str(tmp_path / "old.db")
        old = [m for m in dbmod.MIGRATIONS if m[0] < 4]
        orig = dbmod.MIGRATIONS
        dbmod.MIGRATIONS = old
        try:
            d = Database(path)
            await d.connect()
            await d.execute(
                "INSERT INTO workouts (id, started_at, ended_at) VALUES ('old', ?, ?)",
                ("2026-01-01T00:00:00+00:00", "2026-01-01T00:10:00+00:00"),
            )
            await d.close()
        finally:
            dbmod.MIGRATIONS = orig

        d = Database(path)
        await d.connect()
        try:
            assert (await get_workout(d, "old")).export_status == ExportStatus.SKIPPED
            await _add_workout(d, "new")
            assert (await get_workout(d, "new")).export_status == ExportStatus.PENDING
        finally:
            await d.close()


class TestRoutes:
    async def test_status_hides_token_and_path(self, db, client):
        await _add_workout(db)
        exporter = _exporter(db, client)
        app = create_app(db=db, exporter=exporter)
        with TestClient(app) as tc:
            data = tc.get("/api/export/status").json()
        assert data["configured"] is True
        assert data["target_host"] == "training.example.com"
        assert data["counts"] == {"PENDING": 1}
        assert "s3cret" not in json.dumps(data)
        assert "/ingest" not in json.dumps(data)

    async def test_status_unconfigured(self, db):
        app = create_app(db=db, exporter=None)
        with TestClient(app) as tc:
            data = tc.get("/api/export/status").json()
        assert data["configured"] is False

    async def test_send_route_unconfigured_is_503(self, db):
        await _add_workout(db)
        app = create_app(db=db, exporter=None)
        with TestClient(app) as tc:
            assert tc.post("/api/workouts/w001/export").status_code == 503

    async def test_send_route_unknown_is_404(self, db, client):
        app = create_app(db=db, exporter=_exporter(db, client))
        with TestClient(app) as tc:
            assert tc.post("/api/workouts/nope/export").status_code == 404
