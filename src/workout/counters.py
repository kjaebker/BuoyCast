"""Workout-relative counters on top of the S4's running totals.

The S4 monitor reports cumulative counters (distance, strokes, calories,
elapsed time) since it was last reset. BuoyCast only resets it when a workout
ends, so anything rowed while idle (a warm-up, strokes after declining the
auto-start prompt, or whatever was on the monitor when the Pi booted) would
otherwise leak into the next workout.

WorkoutCounters rebases those counters:

- While idle, values count from the start of the current rowing burst (so the
  idle screen shows the burst the auto-start prompt is about), or read zero
  when not rowing.
- On workout start, the baseline is the start of the current burst if that
  burst began within BURST_CARRY_S (auto-start keeps the strokes rowed during
  the countdown); otherwise it is the current counters, so rowing that went
  on long before Start (e.g. after declining the prompt) isn't counted.
- If a counter goes backwards mid-workout (the monitor was reset or power
  cycled), the total carries forward instead of dropping.
"""

from __future__ import annotations

from datetime import datetime

from src.models import RowingMetrics

COUNTER_FIELDS = ("stroke_count", "distance_m", "calories", "elapsed_seconds")
# Longest rowing lead-in carried into a workout; comfortably covers the
# dashboard's 8 s auto-start countdown.
BURST_CARRY_S = 30.0

Snapshot = dict[str, float]


def _snapshot(m: RowingMetrics) -> Snapshot:
    return {f: float(getattr(m, f) or 0) for f in COUNTER_FIELDS}


class WorkoutCounters:
    def __init__(self) -> None:
        self._in_workout = False
        self._last_raw: Snapshot | None = None
        self._burst_base: Snapshot | None = None  # counters just before rowing began
        self._burst_at: datetime | None = None
        self._last_ts: datetime | None = None
        self._base: Snapshot = dict.fromkeys(COUNTER_FIELDS, 0.0)
        self._carry: Snapshot = dict.fromkeys(COUNTER_FIELDS, 0.0)
        self._last_out: Snapshot = dict.fromkeys(COUNTER_FIELDS, 0.0)

    def start_workout(self) -> None:
        current = self._last_raw or dict.fromkeys(COUNTER_FIELDS, 0.0)
        recent_burst = (
            self._burst_base is not None
            and self._burst_at is not None
            and self._last_ts is not None
            and (self._last_ts - self._burst_at).total_seconds() <= BURST_CARRY_S
        )
        self._base = dict(self._burst_base if recent_burst else current)
        self._carry = dict.fromkeys(COUNTER_FIELDS, 0.0)
        self._in_workout = True

    def end_workout(self) -> None:
        self._in_workout = False
        self._burst_base = None
        self._burst_at = None

    def apply(self, raw: RowingMetrics) -> RowingMetrics:
        """Return `raw` with its counters rebased (other fields untouched)."""
        snap = _snapshot(raw)
        rowing = (raw.stroke_rate or 0) > 0

        if self._in_workout:
            out: Snapshot = {}
            for f in COUNTER_FIELDS:
                if self._last_raw is not None and snap[f] < self._last_raw[f]:
                    # Monitor reset mid-workout: keep what we had, count from 0 again.
                    self._carry[f] = self._last_out[f]
                    self._base[f] = 0.0
                out[f] = self._carry[f] + max(0.0, snap[f] - self._base[f])
        else:
            if rowing and self._burst_base is None:
                self._burst_base = dict(self._last_raw or snap)
                self._burst_at = raw.timestamp
            elif not rowing:
                self._burst_base = None
                self._burst_at = None
            base = self._burst_base or snap
            out = {f: max(0.0, snap[f] - base[f]) for f in COUNTER_FIELDS}

        self._last_raw = snap
        self._last_ts = raw.timestamp
        out["distance_m"] = round(out["distance_m"], 1)  # drop float subtraction noise
        self._last_out = out
        return raw.model_copy(
            update={
                f: (None if getattr(raw, f) is None else type(getattr(raw, f))(out[f]))
                for f in COUNTER_FIELDS
            }
        )
