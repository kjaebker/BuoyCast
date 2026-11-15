"""Pydantic v2 data models for BuoyCast."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkoutState(str, Enum):
    """Workout lifecycle states."""

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    SUMMARY = "SUMMARY"


class StravaUploadStatus(str, Enum):
    """Strava upload lifecycle."""

    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ExportStatus(str, Enum):
    """HTTP export lifecycle (see docs/export.md)."""

    PENDING = "PENDING"  # waiting to be sent (or export not configured yet)
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"  # network error / 408 / 429 / 5xx: retried automatically
    REJECTED = "REJECTED"  # other 4xx: not retried until sent manually
    SKIPPED = "SKIPPED"  # not sent (too short, discarded, or recorded before export existed)


class StrokePhase(str, Enum):
    """Which part of the stroke just began."""

    DRIVE = "drive"  # catch: S4 "SS" (stroke start)
    RECOVERY = "recovery"  # finish: S4 "SE" (stroke end)


class StrokeEvent(BaseModel):
    """A stroke boundary pushed by the S4, used to sync the dashboard animation."""

    phase: StrokePhase
    timestamp: datetime


class RowingMetrics(BaseModel):
    """Unified real-time data from S4 + TICKR, shared across all components."""

    timestamp: datetime
    # S4 data
    stroke_rate: float | None = Field(None, ge=0, le=100)
    stroke_count: int | None = Field(None, ge=0)
    distance_m: float | None = Field(None, ge=0)
    pace_s_per_500m: float | None = Field(None, ge=0)
    power_watts: float | None = Field(None, ge=0)
    calories: int | None = Field(None, ge=0)
    elapsed_seconds: int | None = Field(None, ge=0)
    drive_length_cm: float | None = Field(None, ge=0, le=200)
    # TICKR data
    heart_rate_bpm: int | None = Field(None, ge=20, le=250)
    rr_intervals_ms: list[int] | None = None

    @field_validator("rr_intervals_ms")
    @classmethod
    def validate_rr_intervals(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            if any(i < 200 or i > 2000 for i in v):
                raise ValueError("RR intervals must be between 200ms and 2000ms")
        return v


class StrokeRecord(BaseModel):
    """Time series data — one record per second during active workout."""

    workout_id: str
    ts: datetime
    distance_m: float = Field(ge=0)
    stroke_rate: float = Field(ge=0, le=100)
    power_watts: float | None = None
    pace_s_per_500m: float | None = None
    heart_rate_bpm: int | None = Field(None, ge=20, le=250)
    rr_intervals_ms: list[int] | None = None


class WorkoutRecord(BaseModel):
    """Stored in SQLite — one record per completed workout."""

    id: str
    started_at: datetime
    ended_at: datetime | None = None
    total_distance_m: float = Field(ge=0)
    total_strokes: int = Field(ge=0)
    elapsed_seconds: int = Field(ge=0)
    avg_pace_s_per_500m: float | None = None
    avg_stroke_rate: float | None = None
    avg_power_watts: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    calories: int = Field(default=0, ge=0)
    strava_upload_status: StravaUploadStatus = StravaUploadStatus.PENDING
    strava_activity_id: int | None = None
    strava_error: str | None = None
    fit_file_path: str | None = None
    export_status: ExportStatus = ExportStatus.PENDING
    export_error: str | None = None
    export_attempts: int = Field(default=0, ge=0)
    exported_at: datetime | None = None


class AppSettings(BaseModel):
    """Application-level settings."""

    include_hr_in_strava_upload: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WSMessage(BaseModel):
    """WebSocket message envelope pushed to dashboard clients."""

    type: str
    data: dict[str, Any]
