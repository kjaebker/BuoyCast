"""Unit tests for FIT file generation."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from garmin_fit_sdk import Decoder, Stream

from src.models import StrokeRecord, WorkoutRecord
from src.workout.fit import generate_fit


def _workout(
    hr: int | None = 140,
    max_hr: int | None = 160,
    strokes: int = 10,
) -> WorkoutRecord:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    return WorkoutRecord(
        id="test123",
        started_at=started,
        ended_at=started + timedelta(minutes=10),
        total_distance_m=2000.0,
        total_strokes=strokes,
        elapsed_seconds=600,
        avg_pace_s_per_500m=150.0,
        avg_stroke_rate=28.0,
        avg_power_watts=150.0,
        avg_heart_rate=hr,
        max_heart_rate=max_hr,
        calories=120,
    )


def _strokes(count: int = 10, include_hr: bool = True) -> list[StrokeRecord]:
    started = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
    records = []
    for i in range(count):
        records.append(
            StrokeRecord(
                workout_id="test123",
                ts=started + timedelta(seconds=i),
                distance_m=float(i * 20),
                stroke_rate=28.0,
                power_watts=150.0,
                pace_s_per_500m=150.0,
                heart_rate_bpm=140 + (i % 20) if include_hr else None,
            )
        )
    return records


def _decode_fit(path: Path) -> tuple[dict, list]:
    """Decode a FIT file and return (messages, errors)."""
    stream = Stream.from_file(str(path))
    decoder = Decoder(stream)
    messages, errors = decoder.read()
    return messages, errors


class TestFitGeneration:
    def test_generates_valid_fit_file(self, tmp_path):
        """Generated FIT file should parse without errors."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".fit"

        messages, errors = _decode_fit(path)
        assert len(errors) == 0

    def test_filename_contains_workout_id(self, tmp_path):
        """FIT filename should contain the workout ID."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        assert "test123" in path.name

    def test_creates_output_directory(self):
        """Should create the output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "nested" / "dir"
            path = generate_fit(_workout(), _strokes(), output_dir=out)
            assert path.exists()

    def test_session_sport_set_correctly(self, tmp_path):
        """Session should have Sport.ROWING and SubSport.INDOOR_ROWING."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        sessions = messages.get("session_mesgs", [])
        assert len(sessions) == 1
        session = sessions[0]
        # Sport enum: ROWING = 15
        assert session.get("sport") == "rowing" or session.get("sport") == 15
        # SubSport: INDOOR_ROWING = 14
        sub = session.get("sub_sport")
        assert sub == "indoor_rowing" or sub == 14

    def test_stroke_count_matches_input(self, tmp_path):
        """Number of record messages should match input strokes."""
        strokes = _strokes(count=15)
        path = generate_fit(_workout(strokes=15), strokes, output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        records = messages.get("record_mesgs", [])
        assert len(records) == 15

    def test_hr_present_when_input_includes_hr(self, tmp_path):
        """Record messages should include heart_rate when strokes have HR."""
        path = generate_fit(_workout(), _strokes(include_hr=True), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        records = messages.get("record_mesgs", [])
        assert len(records) > 0
        # At least some records should have heart_rate
        hr_records = [r for r in records if r.get("heart_rate") is not None]
        assert len(hr_records) == len(records)

    def test_hr_omitted_when_no_hr_data(self, tmp_path):
        """Record messages should not have heart_rate when strokes lack HR."""
        workout = _workout(hr=None, max_hr=None)
        strokes = _strokes(include_hr=False)
        path = generate_fit(workout, strokes, output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        records = messages.get("record_mesgs", [])
        assert len(records) > 0
        # No records should have heart_rate
        hr_records = [r for r in records if r.get("heart_rate") is not None]
        assert len(hr_records) == 0

    def test_session_hr_stats(self, tmp_path):
        """Session should include avg and max HR when available."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        session = messages["session_mesgs"][0]
        assert session.get("avg_heart_rate") == 140
        assert session.get("max_heart_rate") == 160

    def test_session_no_hr_stats_when_none(self, tmp_path):
        """Session should omit HR stats when not available."""
        workout = _workout(hr=None, max_hr=None)
        path = generate_fit(workout, _strokes(include_hr=False), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        session = messages["session_mesgs"][0]
        assert session.get("avg_heart_rate") is None
        assert session.get("max_heart_rate") is None

    def test_empty_strokes(self, tmp_path):
        """Should generate a valid FIT file even with no strokes."""
        path = generate_fit(_workout(strokes=0), [], output_dir=tmp_path)
        messages, errors = _decode_fit(path)
        assert len(errors) == 0

    def test_session_distance_and_calories(self, tmp_path):
        """Session should include total distance and calories."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        session = messages["session_mesgs"][0]
        dist = session.get("total_distance")
        # Decoder returns meters; should exactly match the workout's total_distance_m
        assert dist == 2000.0

    def test_activity_message_present(self, tmp_path):
        """Activity message should be present."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        activities = messages.get("activity_mesgs", [])
        assert len(activities) == 1

    def test_timestamp_year_correct(self, tmp_path):
        """Session timestamp year should match the workout start year (not 20 years off)."""
        path = generate_fit(_workout(), _strokes(), output_dir=tmp_path)
        messages, _ = _decode_fit(path)

        session = messages["session_mesgs"][0]
        ts = session.get("start_time") or session.get("timestamp")
        assert ts is not None
        assert ts.year == 2026
