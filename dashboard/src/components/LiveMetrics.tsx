/**
 * LiveMetrics — real-time rowing data display.
 *
 * iPhone: single column, large metrics
 * iPad: two columns — metrics left, sparkline right
 */

import { useRef } from "react";
import { Activity, Timer, Ruler, Gauge, Zap, Flame, Heart } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime, formatPace, formatDistance, formatNum } from "@/lib/format";
import { MetricSparkline } from "./MetricSparkline";
import type { RowingMetrics, WorkoutState } from "@/types";

type LiveMetricsProps = {
  metrics: RowingMetrics | null;
  workoutState: WorkoutState;
};

type MetricTileProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  highlight?: boolean;
};

function MetricTile({ icon, label, value, unit, highlight }: MetricTileProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl bg-card p-4 shadow-sm border border-border",
        highlight && "ring-2 ring-primary"
      )}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
        {icon}
        {label}
      </div>
      <div className="text-3xl font-bold tabular-nums text-foreground">
        {value}
      </div>
      {unit && (
        <div className="text-xs text-muted-foreground mt-0.5">{unit}</div>
      )}
    </div>
  );
}

export function LiveMetrics({ metrics, workoutState }: LiveMetricsProps) {
  const strokeRateHistoryRef = useRef<number[]>([]);

  // Track stroke rate history for sparkline
  if (metrics?.stroke_rate != null) {
    const history = strokeRateHistoryRef.current;
    history.push(metrics.stroke_rate);
    if (history.length > 60) history.shift();
  }

  const isPaused = workoutState === "PAUSED";

  return (
    <div className="flex-1 p-4">
      {isPaused && (
        <div className="mb-4 text-center">
          <span className="inline-block rounded-full bg-yellow-500/20 px-4 py-1.5 text-sm font-medium text-yellow-500">
            PAUSED
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
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
          icon={<Gauge className="h-3.5 w-3.5" />}
          label="Pace"
          value={formatPace(metrics?.pace_s_per_500m ?? null)}
          unit="/500m"
        />
        <MetricTile
          icon={<Activity className="h-3.5 w-3.5" />}
          label="Stroke Rate"
          value={formatNum(metrics?.stroke_rate ?? null, 1)}
          unit="spm"
          highlight
        />
        <MetricTile
          icon={<Zap className="h-3.5 w-3.5" />}
          label="Power"
          value={formatNum(metrics?.power_watts ?? null)}
          unit="W"
        />
        <MetricTile
          icon={<Flame className="h-3.5 w-3.5" />}
          label="Calories"
          value={formatNum(metrics?.calories ?? null)}
          unit="kcal"
        />
        <MetricTile
          icon={<Heart className="h-3.5 w-3.5" />}
          label="Heart Rate"
          value={formatNum(metrics?.heart_rate_bpm ?? null)}
          unit="bpm"
        />
      </div>

      {/* Sparkline — visible on tablet */}
      <div className="hidden md:block mt-4">
        <MetricSparkline
          data={strokeRateHistoryRef.current}
          label="Stroke Rate (last 60s)"
          color="hsl(var(--color-chart-1))"
        />
      </div>
    </div>
  );
}
