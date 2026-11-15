"""The JSON body BuoyCast POSTs to an export endpoint (format = "json").

This is a public contract, documented in docs/export.md. Add fields freely,
but bump SCHEMA_VERSION for any change that breaks an existing receiver
(renaming, removing, or changing the meaning or unit of a field).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models import StrokeRecord, WorkoutRecord

SCHEMA_VERSION = 1


class ExportSource(BaseModel):
    app: Literal["buoycast"] = "buoycast"
    version: str


class ExportWorkout(BaseModel):
    """Summary of one workout. Times are UTC ISO 8601; distances in metres."""

    id: str
    sport: Literal["rowing"] = "rowing"
    sub_sport: Literal["indoor_rowing"] = "indoor_rowing"
    started_at: datetime
    ended_at: datetime
    elapsed_seconds: int = Field(ge=0)
    total_distance_m: float = Field(ge=0)
    total_strokes: int = Field(ge=0)
    calories: int = Field(ge=0)
    avg_pace_s_per_500m: float | None = None
    avg_stroke_rate: float | None = None
    avg_power_watts: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None


class ExportSample(BaseModel):
    """One sample, recorded about once per second while the workout was active."""

    ts: datetime
    distance_m: float = Field(ge=0)
    stroke_rate: float = Field(ge=0)
    power_watts: float | None = None
    pace_s_per_500m: float | None = None
    heart_rate_bpm: int | None = None
    rr_intervals_ms: list[int] | None = None


class ExportPayload(BaseModel):
    schema_version: int = SCHEMA_VERSION
    source: ExportSource
    workout: ExportWorkout
    samples: list[ExportSample]


def build_payload(
    workout: WorkoutRecord,
    strokes: list[StrokeRecord],
    version: str,
    include_hr: bool = True,
) -> ExportPayload:
    """Build the export body for a finished workout."""
    if workout.ended_at is None:
        raise ValueError(f"workout {workout.id} has not ended")

    samples = [
        ExportSample(
            ts=s.ts,
            distance_m=s.distance_m,
            stroke_rate=s.stroke_rate,
            power_watts=s.power_watts,
            pace_s_per_500m=s.pace_s_per_500m,
            heart_rate_bpm=s.heart_rate_bpm if include_hr else None,
            rr_intervals_ms=s.rr_intervals_ms if include_hr else None,
        )
        for s in strokes
    ]
    return ExportPayload(
        source=ExportSource(version=version),
        workout=ExportWorkout(
            id=workout.id,
            started_at=workout.started_at,
            ended_at=workout.ended_at,
            elapsed_seconds=workout.elapsed_seconds,
            total_distance_m=workout.total_distance_m,
            total_strokes=workout.total_strokes,
            calories=workout.calories,
            avg_pace_s_per_500m=workout.avg_pace_s_per_500m,
            avg_stroke_rate=workout.avg_stroke_rate,
            avg_power_watts=workout.avg_power_watts,
            avg_heart_rate=workout.avg_heart_rate if include_hr else None,
            max_heart_rate=workout.max_heart_rate if include_hr else None,
        ),
        samples=samples,
    )
