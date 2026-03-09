"""SQL query functions for workouts and strokes.

All functions take a Database instance and operate on Pydantic models.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models import StrokeRecord, StravaUploadStatus, WorkoutRecord
from src.storage.db import Database


async def insert_workout(db: Database, record: WorkoutRecord) -> None:
    """Insert a new workout record."""
    await db.execute(
        """INSERT INTO workouts (
            id, started_at, ended_at, total_distance_m, total_strokes,
            elapsed_seconds, avg_pace_s_per_500m, avg_stroke_rate,
            avg_power_watts, avg_heart_rate, max_heart_rate, calories,
            strava_upload_status, strava_activity_id, strava_error, fit_file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.id,
            record.started_at.isoformat(),
            record.ended_at.isoformat() if record.ended_at else "",
            record.total_distance_m,
            record.total_strokes,
            record.elapsed_seconds,
            record.avg_pace_s_per_500m,
            record.avg_stroke_rate,
            record.avg_power_watts,
            record.avg_heart_rate,
            record.max_heart_rate,
            record.calories,
            record.strava_upload_status.value,
            record.strava_activity_id,
            record.strava_error,
            record.fit_file_path,
        ),
    )


async def update_workout(db: Database, workout_id: str, **fields: object) -> None:
    """Partial update of a workout record."""
    if not fields:
        return
    # Convert enum values to strings for storage
    processed = {}
    for k, v in fields.items():
        if isinstance(v, StravaUploadStatus):
            processed[k] = v.value
        elif isinstance(v, datetime):
            processed[k] = v.isoformat()
        else:
            processed[k] = v
    set_clause = ", ".join(f"{k} = ?" for k in processed)
    values = tuple(processed.values()) + (workout_id,)
    await db.execute(f"UPDATE workouts SET {set_clause} WHERE id = ?", values)


async def get_workout(db: Database, workout_id: str) -> WorkoutRecord | None:
    """Fetch a single workout by ID."""
    row = await db.fetch_one("SELECT * FROM workouts WHERE id = ?", (workout_id,))
    if row is None:
        return None
    return _row_to_workout(row)


async def list_workouts(
    db: Database, limit: int = 20, offset: int = 0
) -> list[WorkoutRecord]:
    """List workouts ordered by start time (newest first)."""
    rows = await db.fetch_all(
        "SELECT * FROM workouts ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [_row_to_workout(r) for r in rows]


async def delete_workout(db: Database, workout_id: str) -> None:
    """Delete a workout and its associated strokes."""
    await db.execute("DELETE FROM strokes WHERE workout_id = ?", (workout_id,))
    await db.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))


async def insert_strokes(db: Database, strokes: list[StrokeRecord]) -> None:
    """Bulk insert stroke records."""
    if not strokes:
        return
    await db.execute_many(
        """INSERT INTO strokes (
            workout_id, ts, distance_m, stroke_rate, power_watts,
            pace_s_per_500m, heart_rate_bpm, rr_intervals_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                s.workout_id,
                s.ts.isoformat(),
                s.distance_m,
                s.stroke_rate,
                s.power_watts,
                s.pace_s_per_500m,
                s.heart_rate_bpm,
                json.dumps(s.rr_intervals_ms) if s.rr_intervals_ms else None,
            )
            for s in strokes
        ],
    )


async def get_strokes(db: Database, workout_id: str) -> list[StrokeRecord]:
    """Fetch all strokes for a workout."""
    rows = await db.fetch_all(
        "SELECT * FROM strokes WHERE workout_id = ? ORDER BY ts", (workout_id,)
    )
    return [_row_to_stroke(r) for r in rows]


async def get_incomplete_workout(db: Database) -> WorkoutRecord | None:
    """Find a workout missing ended_at — for boot-time recovery."""
    row = await db.fetch_one(
        "SELECT * FROM workouts WHERE ended_at = '' OR ended_at IS NULL"
    )
    if row is None:
        return None
    return _row_to_workout(row)


def _row_to_workout(row: dict) -> WorkoutRecord:
    """Convert a database row dict to a WorkoutRecord."""
    return WorkoutRecord(
        id=row["id"],
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
        total_distance_m=row["total_distance_m"],
        total_strokes=row["total_strokes"],
        elapsed_seconds=row["elapsed_seconds"],
        avg_pace_s_per_500m=row["avg_pace_s_per_500m"],
        avg_stroke_rate=row["avg_stroke_rate"],
        avg_power_watts=row["avg_power_watts"],
        avg_heart_rate=row["avg_heart_rate"],
        max_heart_rate=row["max_heart_rate"],
        calories=row["calories"],
        strava_upload_status=StravaUploadStatus(row["strava_upload_status"]),
        strava_activity_id=row["strava_activity_id"],
        strava_error=row["strava_error"],
        fit_file_path=row["fit_file_path"],
    )


def _row_to_stroke(row: dict) -> StrokeRecord:
    """Convert a database row dict to a StrokeRecord."""
    rr = row["rr_intervals_ms"]
    return StrokeRecord(
        workout_id=row["workout_id"],
        ts=datetime.fromisoformat(row["ts"]),
        distance_m=row["distance_m"],
        stroke_rate=row["stroke_rate"],
        power_watts=row["power_watts"],
        pace_s_per_500m=row["pace_s_per_500m"],
        heart_rate_bpm=row["heart_rate_bpm"],
        rr_intervals_ms=json.loads(rr) if rr else None,
    )
