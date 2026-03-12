/**
 * LiveMetrics - real-time rowing data display.
 *
 * iPhone: single column, large metrics
 * iPad: two columns - metrics left, sparkline right
 */

import { useRef, useState, useEffect } from "react";
import { Activity, Timer, Ruler, Gauge, Zap, Flame, Heart } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime, formatPace, formatDistance, formatNum } from "@/lib/format";
import { MetricSparkline } from "./MetricSparkline";
import type { RowingMetrics, WorkoutState } from "@/types";

type LiveMetricsProps = {
  metrics: RowingMetrics | null;
  workoutState: WorkoutState;
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

export function LiveMetrics({ metrics, workoutState }: LiveMetricsProps) {
  const strokeRateHistoryRef = useRef<number[]>([]);
  const lastActiveStrokeMs = useRef<number>(0);
  const [effectiveStrokeRate, setEffectiveStrokeRate] = useState<number | null>(null);
  const [msgIdx, setMsgIdx] = useState(0);

  useEffect(() => {
    if (workoutState !== "ACTIVE") {
      setMsgIdx(0);
      return;
    }
    const id = setInterval(() => {
      setMsgIdx((i) => (i + 1) % ACTIVE_MESSAGES.length);
    }, 30_000);
    return () => clearInterval(id);
  }, [workoutState]);

  // Track last time we saw an active stroke rate
  useEffect(() => {
    if (metrics?.stroke_rate != null && metrics.stroke_rate > 0) {
      lastActiveStrokeMs.current = Date.now();
      setEffectiveStrokeRate(metrics.stroke_rate);
    }
  }, [metrics?.stroke_rate, metrics?.timestamp]);

  // Decay stroke rate to 0 after 3s without active rowing
  useEffect(() => {
    const id = setInterval(() => {
      if (lastActiveStrokeMs.current > 0 && Date.now() - lastActiveStrokeMs.current > 3000) {
        setEffectiveStrokeRate(0);
      }
    }, 500);
    return () => clearInterval(id);
  }, []);

  const strokeRateForDisplay = effectiveStrokeRate;

  // Only record active stroke rates — zeros from the decay interval would
  // scale the Y-axis down to 0 and make the sparkline appear to bottom out.
  if (strokeRateForDisplay != null && strokeRateForDisplay > 0) {
    const history = strokeRateHistoryRef.current;
    history.push(strokeRateForDisplay);
    if (history.length > 60) history.shift();
  }

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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <MetricTile
          icon={<Timer className="h-3.5 w-3.5" />}
          label="Time"
          value={formatTime(metrics?.elapsed_seconds ?? null)}
          tone="slate"
        />
        <MetricTile
          icon={<Ruler className="h-3.5 w-3.5" />}
          label="Distance"
          value={formatDistance(metrics?.distance_m ?? null)}
          unit="m"
          tone="teal"
        />
        <MetricTile
          icon={<Gauge className="h-3.5 w-3.5" />}
          label="Pace"
          value={formatPace(metrics?.pace_s_per_500m ?? null)}
          unit="/500m"
          tone="ember"
        />
        <MetricTile
          icon={<Activity className="h-3.5 w-3.5" />}
          label="Stroke Rate"
          value={formatNum(strokeRateForDisplay, 1)}
          unit="spm"
          tone="ember"
          highlight
        />
        <MetricTile
          icon={<Zap className="h-3.5 w-3.5" />}
          label="Power"
          value={formatNum(metrics?.power_watts ?? null)}
          unit="W"
          tone="teal"
        />
        <MetricTile
          icon={<Flame className="h-3.5 w-3.5" />}
          label="Calories"
          value={formatNum(metrics?.calories ?? null)}
          unit="kcal"
          tone="ember"
        />
        <MetricTile
          icon={<Heart className="h-3.5 w-3.5 fill-current" />}
          label="Heart Rate"
          value={formatNum(metrics?.heart_rate_bpm ?? null)}
          unit="bpm"
          tone="rose"
          pulseRate={metrics?.heart_rate_bpm}
        />
      </div>

      <div className="mt-4 hidden md:block">
        <MetricSparkline
          data={strokeRateHistoryRef.current}
          label="Stroke rate, last 60 seconds"
          color="var(--color-chart-2)"
        />
      </div>
    </div>
  );
}
