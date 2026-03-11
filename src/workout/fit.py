"""FIT file generation for completed workouts.

Produces Garmin FIT files with Sport.ROWING + SubSport.INDOOR_ROWING,
session summary, and per-stroke record messages with HR time series.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    Event,
    EventType,
    FileType,
    Manufacturer,
    Sport,
    SubSport,
)

from src.models import StrokeRecord, WorkoutRecord

logger = logging.getLogger(__name__)

def _to_fit_timestamp(dt: datetime) -> int:
    """Convert datetime to milliseconds since Unix epoch.

    fit_tool expects Unix milliseconds internally — it handles the conversion
    to FIT binary timestamps (seconds since Dec 31, 1989) when writing.
    """
    return int(dt.timestamp() * 1000)


def generate_fit(
    workout: WorkoutRecord,
    strokes: list[StrokeRecord],
    output_dir: str | Path = "data/fit",
) -> Path:
    """Generate a FIT file from a completed workout and its stroke data.

    Args:
        workout: The completed WorkoutRecord with summary stats.
        strokes: List of StrokeRecord entries for the workout.
        output_dir: Directory to write the FIT file to.

    Returns:
        Path to the generated FIT file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    builder = FitFileBuilder(auto_define=True)

    start_ts = _to_fit_timestamp(workout.started_at)
    end_ts = _to_fit_timestamp(workout.ended_at) if workout.ended_at else start_ts
    elapsed_ms = float(workout.elapsed_seconds * 1000)

    # File ID
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 1
    file_id.serial_number = abs(hash(workout.id)) % 2**31
    file_id.time_created = start_ts
    builder.add(file_id)

    # Timer start event
    start_event = EventMessage()
    start_event.event = Event.TIMER
    start_event.event_type = EventType.START
    start_event.timestamp = start_ts
    builder.add(start_event)

    # Record messages — one per stroke
    for stroke in strokes:
        record = RecordMessage()
        record.timestamp = _to_fit_timestamp(stroke.ts)

        if stroke.heart_rate_bpm is not None:
            record.heart_rate = stroke.heart_rate_bpm

        if stroke.stroke_rate > 0:
            record.cadence = int(stroke.stroke_rate)

        if stroke.power_watts is not None and stroke.power_watts > 0:
            record.power = int(stroke.power_watts)

        # Distance in meters — fit_tool handles the m→cm FIT scaling internally
        record.distance = stroke.distance_m

        # Speed in m/s — explicit field so Strava can render the speed chart
        if stroke.pace_s_per_500m is not None and stroke.pace_s_per_500m > 0:
            record.speed = 500.0 / stroke.pace_s_per_500m

        builder.add(record)

    # Timer stop event
    stop_event = EventMessage()
    stop_event.event = Event.TIMER
    stop_event.event_type = EventType.STOP_ALL
    stop_event.timestamp = end_ts
    builder.add(stop_event)

    # Lap message (single lap for the whole workout)
    lap = LapMessage()
    lap.timestamp = end_ts
    lap.start_time = start_ts
    lap.total_elapsed_time = elapsed_ms
    lap.total_timer_time = elapsed_ms
    lap.total_distance = workout.total_distance_m
    if workout.avg_heart_rate is not None:
        lap.avg_heart_rate = workout.avg_heart_rate
    if workout.max_heart_rate is not None:
        lap.max_heart_rate = workout.max_heart_rate
    if workout.avg_stroke_rate is not None:
        lap.avg_cadence = int(workout.avg_stroke_rate)
    if workout.avg_power_watts is not None:
        lap.avg_power = int(workout.avg_power_watts)
    builder.add(lap)

    # Session message
    session = SessionMessage()
    session.sport = Sport.ROWING
    session.sub_sport = SubSport.INDOOR_ROWING
    session.timestamp = end_ts
    session.start_time = start_ts
    session.total_elapsed_time = elapsed_ms
    session.total_timer_time = elapsed_ms
    session.total_distance = workout.total_distance_m
    session.total_strokes = workout.total_strokes
    session.total_calories = workout.calories
    session.num_laps = 1
    if workout.avg_heart_rate is not None:
        session.avg_heart_rate = workout.avg_heart_rate
    if workout.max_heart_rate is not None:
        session.max_heart_rate = workout.max_heart_rate
    if workout.avg_stroke_rate is not None:
        session.avg_cadence = int(workout.avg_stroke_rate)
    if workout.avg_power_watts is not None:
        session.avg_power = int(workout.avg_power_watts)
    if workout.avg_pace_s_per_500m is not None and workout.avg_pace_s_per_500m > 0:
        session.avg_speed = 500.0 / workout.avg_pace_s_per_500m
    builder.add(session)

    # Activity message
    activity = ActivityMessage()
    activity.timestamp = end_ts
    activity.total_timer_time = elapsed_ms
    activity.num_sessions = 1
    builder.add(activity)

    # Build and write
    fit_file = builder.build()
    filename = f"buoycast_{workout.id}.fit"
    file_path = output_path / filename
    fit_file.to_file(str(file_path))

    logger.info("FIT file generated: %s", file_path)
    return file_path
