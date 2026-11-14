"""Integration tests for the storage layer against in-memory SQLite."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.models import StravaUploadStatus, StrokeRecord, WorkoutRecord
from src.storage.db import Database
from src.storage.queries import (
    delete_workout,
    get_incomplete_workout,
    get_strokes,
    get_workout,
    insert_strokes,
    insert_workout,
    list_workouts,
    update_workout,
)


@pytest.fixture
async def db():
    """Provide a fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


def _make_workout(
    id: str = "w-001",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    **kwargs,
) -> WorkoutRecord:
    now = datetime.now(tz=UTC)
    return WorkoutRecord(
        id=id,
        started_at=started_at or now - timedelta(minutes=30),
        ended_at=ended_at or now,
        total_distance_m=kwargs.get("total_distance_m", 5000.0),
        total_strokes=kwargs.get("total_strokes", 600),
        elapsed_seconds=kwargs.get("elapsed_seconds", 1800),
        avg_pace_s_per_500m=kwargs.get("avg_pace_s_per_500m", 120.0),
        avg_stroke_rate=kwargs.get("avg_stroke_rate", 28.0),
        avg_power_watts=kwargs.get("avg_power_watts", 150.0),
        avg_heart_rate=kwargs.get("avg_heart_rate", 145),
        max_heart_rate=kwargs.get("max_heart_rate", 170),
        calories=kwargs.get("calories", 300),
        strava_upload_status=kwargs.get("strava_upload_status", StravaUploadStatus.PENDING),
    )


def _make_stroke(
    workout_id: str = "w-001",
    offset_s: int = 0,
    distance_m: float = 10.0,
    stroke_rate: float = 28.0,
    heart_rate_bpm: int | None = 140,
) -> StrokeRecord:
    return StrokeRecord(
        workout_id=workout_id,
        ts=datetime.now(tz=UTC) + timedelta(seconds=offset_s),
        distance_m=distance_m,
        stroke_rate=stroke_rate,
        power_watts=150.0,
        pace_s_per_500m=120.0,
        heart_rate_bpm=heart_rate_bpm,
        rr_intervals_ms=[700, 710] if heart_rate_bpm else None,
    )


class TestWorkoutRoundTrip:
    async def test_insert_and_fetch(self, db: Database):
        w = _make_workout()
        await insert_workout(db, w)
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        assert fetched.id == w.id
        assert fetched.total_distance_m == w.total_distance_m
        assert fetched.total_strokes == w.total_strokes
        assert fetched.avg_heart_rate == w.avg_heart_rate
        assert fetched.strava_upload_status == StravaUploadStatus.PENDING

    async def test_fetch_nonexistent(self, db: Database):
        result = await get_workout(db, "nonexistent")
        assert result is None

    async def test_timestamps_preserved(self, db: Database):
        now = datetime.now(tz=UTC)
        w = _make_workout(started_at=now - timedelta(hours=1), ended_at=now)
        await insert_workout(db, w)
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        # Allow microsecond rounding
        assert abs((fetched.started_at - w.started_at).total_seconds()) < 0.01
        assert abs((fetched.ended_at - w.ended_at).total_seconds()) < 0.01


class TestListWorkouts:
    async def test_list_order(self, db: Database):
        now = datetime.now(tz=UTC)
        for i in range(5):
            w = _make_workout(
                id=f"w-{i:03d}",
                started_at=now - timedelta(hours=5 - i),
                ended_at=now - timedelta(hours=5 - i) + timedelta(minutes=30),
            )
            await insert_workout(db, w)

        results = await list_workouts(db, limit=10)
        assert len(results) == 5
        # Newest first
        assert results[0].id == "w-004"
        assert results[-1].id == "w-000"

    async def test_pagination(self, db: Database):
        now = datetime.now(tz=UTC)
        for i in range(10):
            w = _make_workout(
                id=f"w-{i:03d}",
                started_at=now - timedelta(hours=10 - i),
                ended_at=now - timedelta(hours=10 - i) + timedelta(minutes=30),
            )
            await insert_workout(db, w)

        page1 = await list_workouts(db, limit=3, offset=0)
        page2 = await list_workouts(db, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id

    async def test_empty_list(self, db: Database):
        results = await list_workouts(db)
        assert results == []


class TestUpdateWorkout:
    async def test_update_strava_status(self, db: Database):
        await insert_workout(db, _make_workout())
        await update_workout(db, "w-001", strava_upload_status=StravaUploadStatus.UPLOADED)
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        assert fetched.strava_upload_status == StravaUploadStatus.UPLOADED

    async def test_update_multiple_fields(self, db: Database):
        await insert_workout(db, _make_workout())
        await update_workout(
            db,
            "w-001",
            strava_upload_status=StravaUploadStatus.UPLOADED,
            strava_activity_id=12345,
        )
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        assert fetched.strava_upload_status == StravaUploadStatus.UPLOADED
        assert fetched.strava_activity_id == 12345

    async def test_update_strava_error(self, db: Database):
        await insert_workout(db, _make_workout())
        await update_workout(
            db,
            "w-001",
            strava_upload_status=StravaUploadStatus.FAILED,
            strava_error="Rate limit exceeded",
        )
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        assert fetched.strava_upload_status == StravaUploadStatus.FAILED
        assert fetched.strava_error == "Rate limit exceeded"

    async def test_update_empty_is_noop(self, db: Database):
        await insert_workout(db, _make_workout())
        await update_workout(db, "w-001")  # no fields
        fetched = await get_workout(db, "w-001")
        assert fetched is not None
        assert fetched.strava_upload_status == StravaUploadStatus.PENDING


class TestDeleteWorkout:
    async def test_delete_removes_workout(self, db: Database):
        await insert_workout(db, _make_workout())
        await delete_workout(db, "w-001")
        assert await get_workout(db, "w-001") is None

    async def test_delete_removes_strokes(self, db: Database):
        await insert_workout(db, _make_workout())
        strokes = [_make_stroke(offset_s=i) for i in range(10)]
        await insert_strokes(db, strokes)
        assert len(await get_strokes(db, "w-001")) == 10

        await delete_workout(db, "w-001")
        assert await get_strokes(db, "w-001") == []

    async def test_delete_nonexistent_is_noop(self, db: Database):
        await delete_workout(db, "nonexistent")  # should not raise


class TestStrokeInsertAndRetrieval:
    async def test_insert_and_fetch(self, db: Database):
        await insert_workout(db, _make_workout())
        strokes = [_make_stroke(offset_s=i, distance_m=i * 10.0) for i in range(5)]
        await insert_strokes(db, strokes)

        fetched = await get_strokes(db, "w-001")
        assert len(fetched) == 5
        assert fetched[0].distance_m == 0.0
        assert fetched[4].distance_m == 40.0

    async def test_rr_intervals_roundtrip(self, db: Database):
        await insert_workout(db, _make_workout())
        stroke = _make_stroke(heart_rate_bpm=140)
        await insert_strokes(db, [stroke])

        fetched = await get_strokes(db, "w-001")
        assert len(fetched) == 1
        assert fetched[0].rr_intervals_ms == [700, 710]

    async def test_null_hr_roundtrip(self, db: Database):
        await insert_workout(db, _make_workout())
        stroke = _make_stroke(heart_rate_bpm=None)
        await insert_strokes(db, [stroke])

        fetched = await get_strokes(db, "w-001")
        assert fetched[0].heart_rate_bpm is None
        assert fetched[0].rr_intervals_ms is None

    async def test_bulk_insert_1000(self, db: Database):
        await insert_workout(db, _make_workout())
        strokes = [_make_stroke(offset_s=i, distance_m=i * 2.0) for i in range(1000)]
        await insert_strokes(db, strokes)

        fetched = await get_strokes(db, "w-001")
        assert len(fetched) == 1000

    async def test_empty_insert(self, db: Database):
        await insert_workout(db, _make_workout())
        await insert_strokes(db, [])  # should not raise
        assert await get_strokes(db, "w-001") == []

    async def test_strokes_ordered_by_ts(self, db: Database):
        await insert_workout(db, _make_workout())
        # Insert out of order
        strokes = [_make_stroke(offset_s=i) for i in [3, 1, 4, 1, 5]]
        await insert_strokes(db, strokes)

        fetched = await get_strokes(db, "w-001")
        timestamps = [s.ts for s in fetched]
        assert timestamps == sorted(timestamps)


class TestIncompleteWorkout:
    async def test_detects_incomplete(self, db: Database):
        # Insert directly with empty ended_at to simulate incomplete
        await db.execute(
            """INSERT INTO workouts (id, started_at, ended_at, total_distance_m,
               total_strokes, elapsed_seconds)
               VALUES (?, ?, '', 0, 0, 0)""",
            ("w-incomplete", datetime.now(tz=UTC).isoformat()),
        )
        result = await get_incomplete_workout(db)
        assert result is not None
        assert result.id == "w-incomplete"

    async def test_no_incomplete(self, db: Database):
        await insert_workout(db, _make_workout())
        result = await get_incomplete_workout(db)
        assert result is None


class TestConcurrentWrites:
    async def test_concurrent_inserts(self, db: Database):
        await insert_workout(db, _make_workout(id="w-concurrent"))

        async def insert_batch(start: int):
            strokes = [
                _make_stroke(workout_id="w-concurrent", offset_s=start + i, distance_m=float(i))
                for i in range(50)
            ]
            await insert_strokes(db, strokes)

        await asyncio.gather(
            insert_batch(0),
            insert_batch(100),
            insert_batch(200),
        )

        fetched = await get_strokes(db, "w-concurrent")
        assert len(fetched) == 150


class TestMigrationIdempotency:
    async def test_double_connect(self):
        """Connecting twice should not fail — migrations are idempotent."""
        db = Database(":memory:")
        await db.connect()
        await db.close()
        db2 = Database(":memory:")
        await db2.connect()
        # Should still work
        await insert_workout(db2, _make_workout())
        fetched = await get_workout(db2, "w-001")
        assert fetched is not None
        await db2.close()
