/**
 * StrokeClock — drives the animated rower's stroke phase.
 *
 * With live stroke events from the S4 (SS at the catch, SE at the finish) the
 * rower is phase-locked to the real rower:
 *   - Catch is the anchor: each SS starts his drive. If the real catch is late
 *     he waits at full compression instead of starting the next stroke early.
 *   - Finish is a soft correction: at each SE he speeds up if behind, or holds
 *     briefly if ahead (never moves backwards).
 *   - Stroke period comes from catch-to-catch time and the drive:recovery split
 *     from catch-to-finish time, so he takes on the real rower's rhythm.
 *
 * Without stroke events (simulator off, or firmware that doesn't send them) it
 * free-runs at the displayed stroke rate, as a metronome.
 *
 * `phase` is real-time stroke fraction (0 = catch, driveFrac = finish).
 * `posePhase()` remaps it onto rowerPose's fixed DRIVE_FRACTION timeline.
 */

import { DRIVE_FRACTION } from "./rowerSprite";

export type StrokeKind = "drive" | "recovery";
export type ClockInput = { isRowing: boolean; strokeRate: number };

/** How many expected strokes without an SS before falling back to free-run. */
const SYNC_TIMEOUT_STROKES = 1.6;
const MIN_SYNC_TIMEOUT_MS = 2500;
/** Correction time constant (s⁻¹): ~100 ms to absorb a phase error. */
const CORRECTION_RATE = 10;

export class StrokeClock {
  phase = DRIVE_FRACTION + 0.04;
  atRest = true;
  /** Real drive fraction of the stroke (learned from SS→SE). */
  driveFrac = DRIVE_FRACTION;
  /** Stroke period in seconds (learned from SS→SS). */
  period = 3;
  private lastCatchAt: number | null = null;
  private catchArmed = false;
  private correction = 0;
  private freeSpm = 0;

  /** Feed a stroke event; `at` is performance.now() when it arrived. */
  onStroke(kind: StrokeKind, at: number): void {
    if (kind === "drive") {
      if (this.lastCatchAt != null) {
        const t = (at - this.lastCatchAt) / 1000;
        if (t >= 1.2 && t <= 8) this.period += (t - this.period) * 0.5;
      } else if (this.freeSpm > 0) {
        this.period = 60 / this.freeSpm;
      }
      this.lastCatchAt = at;

      if (this.atRest) {
        this.atRest = false;
        this.phase = 0;
        this.correction = 0;
        this.catchArmed = false;
      } else if (this.phase >= 0.85) {
        // Nearly at the catch: glide the rest of the way, then wrap.
        this.correction = 1 - this.phase;
        this.catchArmed = true;
      } else if (this.phase <= 0.15) {
        // Already started the drive early: hold until the real stroke catches up.
        this.correction = -this.phase;
        this.catchArmed = false;
      } else {
        // Far out of step (e.g. just started syncing): snap to the catch.
        this.phase = 0;
        this.correction = 0;
        this.catchArmed = false;
      }
      return;
    }

    // Finish (SE)
    if (this.lastCatchAt != null) {
      const d = (at - this.lastCatchAt) / 1000;
      if (d > 0.3 && d < this.period * 0.75) {
        const frac = Math.min(0.55, Math.max(0.2, d / this.period));
        this.driveFrac += (frac - this.driveFrac) * 0.5;
      }
    }
    if (!this.atRest) {
      const err = this.phase - this.driveFrac;
      if (Math.abs(err) < 0.3) this.correction = -err;
    }
  }

  isSynced(now: number): boolean {
    if (this.lastCatchAt == null) return false;
    const timeout = Math.max(this.period * SYNC_TIMEOUT_STROKES * 1000, MIN_SYNC_TIMEOUT_MS);
    return now - this.lastCatchAt < timeout;
  }

  /** Advance by `dt` seconds. `now` is performance.now(). */
  tick(dt: number, now: number, input: ClockInput): void {
    const synced = this.isSynced(now);
    if (input.isRowing) {
      this.atRest = false;
      this.freeSpm += (input.strokeRate - this.freeSpm) * Math.min(dt * 2, 1);
    }
    if (synced) this.atRest = false;
    if (this.atRest) return;

    // Strokes per second: real rhythm when synced; otherwise the displayed
    // rate (and a gentle minimum so a stopping rower finishes the stroke).
    const rate = synced
      ? 1 / this.period
      : (input.isRowing ? this.freeSpm : Math.max(this.freeSpm, 16)) / 60;
    let step = rate * dt;

    if (this.correction > 0) {
      const d = this.correction * Math.min(1, dt * CORRECTION_RATE);
      step += d;
      this.correction -= d;
    } else if (this.correction < 0) {
      const used = Math.min(-this.correction, step); // hold rather than go backwards
      step -= used;
      this.correction += used;
    }

    const prev = this.phase;
    let next = prev + step;
    if (next >= 1) {
      if (synced && !this.catchArmed) {
        next = 0.999; // wait at the catch for the real stroke
      } else {
        next -= 1;
        this.catchArmed = false;
      }
    }

    // Not rowing and no live strokes: finish this stroke, then rest.
    const restAt = this.driveFrac + 0.04;
    if (!input.isRowing && !synced) {
      const crossed = (prev < restAt && next >= restAt) || (next < prev && next >= restAt);
      if (crossed) {
        this.atRest = true;
        next = restAt;
        this.correction = 0;
      }
    }
    this.phase = next;
  }

  /** Phase on rowerPose's timeline (fixed DRIVE_FRACTION). */
  posePhase(): number {
    const p = this.phase;
    const d = this.driveFrac;
    return p < d
      ? (p / d) * DRIVE_FRACTION
      : DRIVE_FRACTION + ((p - d) / (1 - d)) * (1 - DRIVE_FRACTION);
  }
}
