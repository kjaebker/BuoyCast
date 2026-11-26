/**
 * LiveMetrics - real-time rowing data display.
 *
 * iPhone: single column, large metrics
 * iPad: two columns - metrics left, sparkline right
 *
 * The top visual is either the rowing scene or a live graph of one metric,
 * picked with LiveViewPicker.
 */

import { useState } from "react";
import { useNow } from "@/hooks/useNow";
import { Activity, Timer, Ruler, Gauge, Zap, Flame } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime, formatPace, formatDistance, formatNum } from "@/lib/format";
import { MetricSparkline } from "./MetricSparkline";
import { RowingScene } from "./RowingScene";
import { LiveGraph } from "./LiveGraph";
import { LiveViewPicker } from "./LiveViewPicker";
import { LiveView, useLiveView } from "@/hooks/useLiveView";
import type { RowingMetrics, WorkoutState } from "@/types";
import type { MetricsHistory, SubscribeStrokes } from "@/hooks/useWorkoutSocket";

type LiveMetricsProps = {
  metrics: RowingMetrics | null;
  history: MetricsHistory;
  workoutState: WorkoutState;
  subscribeStrokes: SubscribeStrokes;
};

type MetricTone = "ember" | "teal" | "rose" | "slate";

type MetricTileProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  tone?: MetricTone;
  highlight?: boolean;
  /** BPM — when set, animates the icon at that pulse rate */
  pulseRate?: number | null;
};

const toneClasses: Record<MetricTone, string> = {
  ember:
    "border-[color-mix(in_oklch,var(--color-primary)_28%,var(--color-border))] bg-[color-mix(in_oklch,var(--color-primary)_14%,var(--color-card))] text-[color-mix(in_oklch,var(--color-primary)_76%,white)]",
  teal:
    "border-[color-mix(in_oklch,var(--color-secondary)_34%,var(--color-border))] bg-[color-mix(in_oklch,var(--color-secondary)_16%,var(--color-card))] text-[color-mix(in_oklch,var(--color-secondary)_86%,white)]",
  rose:
    "border-[color-mix(in_oklch,var(--color-destructive)_28%,var(--color-border))] bg-[color-mix(in_oklch,var(--color-destructive)_14%,var(--color-card))] text-[color-mix(in_oklch,var(--color-destructive)_78%,white)]",
  slate:
    "border-border/90 bg-card/80 text-foreground",
};

function MetricTile({ icon, label, value, unit, tone = "slate", highlight, pulseRate }: MetricTileProps) {
  const animatedIcon =
    pulseRate != null && pulseRate > 0 ? (
      <span
        style={{
          display: "inline-flex",
          animation: `heartbeat ${(60 / pulseRate).toFixed(2)}s ease-in-out infinite`,
          transformOrigin: "center",
        }}
      >
        {icon}
      </span>
    ) : (
      icon
    );

  return (
    <div
      className={cn(
        "rounded-[1.4rem] border px-4 py-4 shadow-[0_18px_40px_-28px_rgba(0,0,0,0.9)] backdrop-blur-sm",
        toneClasses[tone],
        highlight && "ring-1 ring-[color-mix(in_oklch,var(--color-primary)_46%,transparent)]",
      )}
    >
      <div className="mb-3 flex items-center gap-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-current/80">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-black/10 text-current">
          {animatedIcon}
        </span>
        {label}
      </div>
      <div className="flex items-end gap-2">
        <div
          key={value}
          className="animate-in fade-in text-3xl font-bold tabular-nums text-foreground duration-200 sm:text-[2.2rem]"
        >
          {value}
        </div>
        {unit && (
          <div className="pb-1 text-xs font-medium uppercase tracking-[0.16em] text-current/75">
            {unit}
          </div>
        )}
      </div>
    </div>
  );
}

const ACTIVE_MESSAGES = [
  "Row with momentum",
  "Find your rhythm",
  "Settle into the stroke",
  "Build that power",
  "Dig deep",
  "Stay strong",
  "Keep the rate",
] as const;

export function LiveMetrics({
  metrics,
  history,
  workoutState,
  subscribeStrokes,
}: LiveMetricsProps) {
  const now = useNow(500);
  const [liveView, setLiveView] = useLiveView();

  // Stroke rate holds its last value briefly, then decays to 0 after 3 s
  // without an active stroke; null until the first stroke is seen.
  const { lastStroke, lastHrAt } = history;
  const effectiveStrokeRate =
    lastStroke == null ? null : now - lastStroke.at <= 3000 ? lastStroke.rate : 0;

  // Hide HR from the chart after 15 s without data — generous enough to ride
  // out BLE jitter and brief merge gaps without the chart flickering.
  const hrConnected = lastHrAt != null && now - lastHrAt <= 15_000;

  // Rotate the encouragement every 30 s while rowing; restart at the first
  // message each time a workout becomes active.
  const [activeSince, setActiveSince] = useState<number | null>(() =>
    workoutState === "ACTIVE" ? Date.now() : null,
  );
  const [prevWorkoutState, setPrevWorkoutState] = useState(workoutState);
  if (workoutState !== prevWorkoutState) {
    setPrevWorkoutState(workoutState);
    setActiveSince(workoutState === "ACTIVE" ? now : null);
  }
  const msgIdx =
    activeSince == null
      ? 0
      : Math.floor(Math.max(0, now - activeSince) / 30_000) % ACTIVE_MESSAGES.length;

  const isPaused = workoutState === "PAUSED";
  const stateLabel =
    workoutState === "ACTIVE"
      ? "Live effort"
      : workoutState === "PAUSED"
        ? "Paused"
        : "Ready to row";

  return (
    <div className="flex-1 px-4 pb-4 pt-5">
      <div className="mb-5 flex items-end justify-between gap-3">
        <div>
          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-primary/80">
            {stateLabel}
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            <span
              key={isPaused ? "paused" : msgIdx}
              className="inline-block animate-in fade-in slide-in-from-bottom-1 duration-500"
            >
              {isPaused ? "Catch your breath" : ACTIVE_MESSAGES[msgIdx]}
            </span>
          </h1>
        </div>
        <div
          className={cn(
            "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]",
            isPaused
              ? "border-[color-mix(in_oklch,var(--color-primary)_32%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary"
              : "border-[color-mix(in_oklch,var(--color-secondary)_32%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_18%,transparent)] text-secondary-foreground",
          )}
        >
          {workoutState}
        </div>
      </div>

      <LiveViewPicker value={liveView} onChange={setLiveView} />

      {liveView === LiveView.SCENE ? (
        <RowingScene
          strokeRate={effectiveStrokeRate}
          pace={metrics?.pace_s_per_500m ?? null}
          isActive={workoutState === "ACTIVE"}
          isPaused={workoutState === "PAUSED"}
          subscribeStrokes={subscribeStrokes}
        />
      ) : (
        <LiveGraph
          metric={liveView}
          samples={history.samples}
          current={
            liveView === LiveView.PACE
              ? (metrics?.pace_s_per_500m ?? null)
              : liveView === LiveView.POWER
                ? (metrics?.power_watts ?? null)
                : liveView === LiveView.STROKE_RATE
                  ? effectiveStrokeRate
                  : hrConnected
                    ? (metrics?.heart_rate_bpm ?? null)
                    : null
          }
        />
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <MetricTile
          icon={<Gauge className="h-3.5 w-3.5" />}
          label="Pace"
          value={formatPace(metrics?.pace_s_per_500m ?? null)}
          unit="/500m"
        />
        <MetricTile
          icon={<Activity className="h-3.5 w-3.5" />}
          label="Stroke Rate"
          value={formatNum(effectiveStrokeRate, 1)}
          unit="spm"
        />
        <MetricTile
          icon={<Zap className="h-3.5 w-3.5" />}
          label="Power"
          value={formatNum(metrics?.power_watts ?? null)}
          unit="W"
        />
        <MetricTile
          icon={<Timer className="h-3.5 w-3.5" />}
          label="Time"
          value={formatTime(metrics?.elapsed_seconds ?? null)}
        />
        <MetricTile
          icon={<Ruler className="h-3.5 w-3.5" />}
          label="Distance"
          value={formatDistance(metrics?.distance_m ?? null)}
          unit="m"
        />
        <MetricTile
          icon={<Flame className="h-3.5 w-3.5" />}
          label="Calories"
          value={formatNum(metrics?.calories ?? null)}
          unit="kcal"
        />
      </div>

      <div className="mt-4">
        <MetricSparkline
          strokeRateData={history.strokeRate}
          heartRateData={history.heartRate}
          currentHr={metrics?.heart_rate_bpm ?? null}
          hrConnected={hrConnected}
          label="Stroke rate, last 60 seconds"
        />
      </div>
    </div>
  );
}
