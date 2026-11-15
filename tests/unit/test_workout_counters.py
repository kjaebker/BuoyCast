"""Workout-relative counters on top of the S4's cumulative totals."""

from datetime import UTC, datetime, timedelta

from src.models import RowingMetrics
from src.workout.counters import WorkoutCounters

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def s4(distance: float, strokes: int, elapsed: int, rate: float = 22.0, calories: int = 0):
    # Timestamps follow the monitor's elapsed time so burst ages are realistic.
    return RowingMetrics(
        timestamp=T0 + timedelta(seconds=elapsed),
        stroke_rate=rate,
        stroke_count=strokes,
        distance_m=distance,
        elapsed_seconds=elapsed,
        calories=calories,
        pace_s_per_500m=120.0,
    )


def test_idle_rowing_before_start_is_not_counted():
    c = WorkoutCounters()
    c.apply(s4(1400, 150, 380))  # warm-up already on the monitor
    c.apply(s4(1430, 153, 390, rate=0))  # stops rowing
    c.start_workout()  # manual start while not rowing
    out = c.apply(s4(1440, 154, 393))
    assert out.distance_m == 10
    assert out.stroke_count == 1
    assert out.elapsed_seconds == 3


def test_auto_start_keeps_strokes_from_the_current_burst():
    c = WorkoutCounters()
    c.apply(s4(500, 50, 200, rate=0))  # idle, old counters on the monitor
    c.apply(s4(510, 51, 202))  # rowing begins
    idle = c.apply(s4(540, 54, 210))  # still idle: shows the burst so far
    assert idle.distance_m == 40
    c.start_workout()  # auto-start after the countdown
    out = c.apply(s4(560, 56, 215))
    assert out.distance_m == 60  # includes the countdown strokes
    assert out.elapsed_seconds == 15


def test_idle_and_not_rowing_reads_zero():
    c = WorkoutCounters()
    out = c.apply(s4(900, 90, 300, rate=0))
    assert out.distance_m == 0 and out.stroke_count == 0 and out.elapsed_seconds == 0


def test_monitor_reset_mid_workout_carries_total_forward():
    c = WorkoutCounters()
    c.apply(s4(0, 0, 0, rate=0))
    c.start_workout()
    c.apply(s4(800, 80, 200))
    out = c.apply(s4(5, 1, 2))  # S4 power-cycled: counters restart near zero
    assert out.distance_m == 805
    assert out.stroke_count == 81
    later = c.apply(s4(105, 11, 32))
    assert later.distance_m == 905


def test_non_counter_fields_and_none_pass_through():
    c = WorkoutCounters()
    c.start_workout()
    raw = RowingMetrics(timestamp=datetime.now(tz=UTC), stroke_rate=20.0, power_watts=150.0)
    out = c.apply(raw)
    assert out.power_watts == 150.0
    assert out.distance_m is None and out.calories is None


def test_long_rowing_before_start_is_not_counted():
    """Rowing for minutes (e.g. after declining the prompt) then pressing Start."""
    c = WorkoutCounters()
    c.apply(s4(0, 0, 0, rate=0))
    c.apply(s4(5, 1, 2))  # burst starts
    c.apply(s4(1600, 140, 400))  # ~6.5 minutes later, still rowing
    c.start_workout()
    out = c.apply(s4(1612, 141, 404))
    assert out.distance_m == 12
    assert out.elapsed_seconds == 4
