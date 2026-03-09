"""Tests for Pydantic data models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models import (
    RowingMetrics,
    StravaUploadStatus,
    StrokeRecord,
    WorkoutRecord,
    WorkoutState,
    WSMessage,
)

NOW = datetime.now(tz=timezone.utc)


# --- WorkoutState ---


class TestWorkoutState:
    def test_values(self):
        assert WorkoutState.IDLE == "IDLE"
        assert WorkoutState.ACTIVE == "ACTIVE"
        assert WorkoutState.PAUSED == "PAUSED"
        assert WorkoutState.SUMMARY == "SUMMARY"

    def test_is_str_enum(self):
        assert isinstance(WorkoutState.IDLE, str)


# --- RowingMetrics ---


class TestRowingMetrics:
    def test_minimal(self):
        m = RowingMetrics(timestamp=NOW)
        assert m.timestamp == NOW
        assert m.stroke_rate is None
        assert m.heart_rate_bpm is None

    def test_full(self):
        m = RowingMetrics(
            timestamp=NOW,
            stroke_rate=28.5,
            stroke_count=100,
            distance_m=500.0,
            pace_s_per_500m=120.0,
            power_watts=150.0,
            calories=50,
            elapsed_seconds=300,
            drive_length_cm=80.0,
            heart_rate_bpm=155,
            rr_intervals_ms=[800, 750],
        )
        assert m.stroke_rate == 28.5
        assert m.heart_rate_bpm == 155
        assert m.rr_intervals_ms == [800, 750]

    def test_stroke_rate_too_high(self):
        with pytest.raises(ValidationError, match="less than or equal to 60"):
            RowingMetrics(timestamp=NOW, stroke_rate=61)

    def test_stroke_rate_negative(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            RowingMetrics(timestamp=NOW, stroke_rate=-1)

    def test_heart_rate_too_low(self):
        with pytest.raises(ValidationError, match="greater than or equal to 20"):
            RowingMetrics(timestamp=NOW, heart_rate_bpm=10)

    def test_heart_rate_too_high(self):
        with pytest.raises(ValidationError, match="less than or equal to 250"):
            RowingMetrics(timestamp=NOW, heart_rate_bpm=300)

    def test_rr_interval_too_low(self):
        with pytest.raises(ValidationError, match="RR intervals must be between"):
            RowingMetrics(timestamp=NOW, rr_intervals_ms=[100])

    def test_rr_interval_too_high(self):
        with pytest.raises(ValidationError, match="RR intervals must be between"):
            RowingMetrics(timestamp=NOW, rr_intervals_ms=[2500])

    def test_rr_intervals_none_is_valid(self):
        m = RowingMetrics(timestamp=NOW, rr_intervals_ms=None)
        assert m.rr_intervals_ms is None

    def test_rr_intervals_empty_list(self):
        m = RowingMetrics(timestamp=NOW, rr_intervals_ms=[])
        assert m.rr_intervals_ms == []

    def test_distance_negative(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            RowingMetrics(timestamp=NOW, distance_m=-5)

    def test_drive_length_over_200(self):
        with pytest.raises(ValidationError, match="less than or equal to 200"):
            RowingMetrics(timestamp=NOW, drive_length_cm=201)

    def test_serialization_roundtrip(self):
        m = RowingMetrics(timestamp=NOW, stroke_rate=25.0, heart_rate_bpm=140)
        data = m.model_dump()
        m2 = RowingMetrics.model_validate(data)
        assert m == m2


# --- StrokeRecord ---


class TestStrokeRecord:
    def test_valid(self):
        s = StrokeRecord(
            workout_id="abc-123",
            ts=NOW,
            distance_m=100.0,
            stroke_rate=28.0,
            power_watts=150.0,
            pace_s_per_500m=120.0,
            heart_rate_bpm=145,
        )
        assert s.workout_id == "abc-123"
        assert s.power_watts == 150.0

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            StrokeRecord(workout_id="abc", ts=NOW)  # type: ignore[call-arg]

    def test_stroke_rate_bounds(self):
        with pytest.raises(ValidationError):
            StrokeRecord(workout_id="x", ts=NOW, distance_m=0, stroke_rate=61)

    def test_negative_distance(self):
        with pytest.raises(ValidationError):
            StrokeRecord(workout_id="x", ts=NOW, distance_m=-1, stroke_rate=0)

    def test_heart_rate_optional(self):
        s = StrokeRecord(workout_id="x", ts=NOW, distance_m=0, stroke_rate=0)
        assert s.heart_rate_bpm is None


# --- WorkoutRecord ---


class TestWorkoutRecord:
    def _make(self, **overrides):
        defaults = dict(
            id="wk-001",
            started_at=NOW,
            ended_at=NOW,
            total_distance_m=2000.0,
            total_strokes=500,
            elapsed_seconds=600,
        )
        defaults.update(overrides)
        return WorkoutRecord(**defaults)

    def test_valid_minimal(self):
        w = self._make()
        assert w.strava_upload_status == StravaUploadStatus.PENDING
        assert w.calories == 0

    def test_full_record(self):
        w = self._make(
            avg_pace_s_per_500m=120.0,
            avg_stroke_rate=28.0,
            avg_power_watts=150.0,
            avg_heart_rate=145,
            max_heart_rate=172,
            calories=300,
            strava_upload_status=StravaUploadStatus.UPLOADED,
            strava_activity_id=123456,
        )
        assert w.strava_upload_status == StravaUploadStatus.UPLOADED
        assert w.strava_activity_id == 123456

    def test_negative_distance_rejected(self):
        with pytest.raises(ValidationError):
            self._make(total_distance_m=-1)

    def test_negative_strokes_rejected(self):
        with pytest.raises(ValidationError):
            self._make(total_strokes=-1)

    def test_strava_status_values(self):
        for status in StravaUploadStatus:
            w = self._make(strava_upload_status=status)
            assert w.strava_upload_status == status

    def test_serialization_roundtrip(self):
        w = self._make(avg_heart_rate=140, calories=250)
        data = w.model_dump()
        w2 = WorkoutRecord.model_validate(data)
        assert w == w2


# --- WSMessage ---


class TestWSMessage:
    def test_metrics_message(self):
        msg = WSMessage(type="metrics_update", data={"stroke_rate": 24.5})
        assert msg.type == "metrics_update"
        assert msg.data["stroke_rate"] == 24.5

    def test_state_change_message(self):
        msg = WSMessage(type="workout_started", data={"workout_id": "abc"})
        assert msg.type == "workout_started"

    def test_json_roundtrip(self):
        msg = WSMessage(type="test", data={"key": "value"})
        json_str = msg.model_dump_json()
        msg2 = WSMessage.model_validate_json(json_str)
        assert msg == msg2
