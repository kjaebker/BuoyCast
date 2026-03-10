/**
 * CompletionScreen - workout summary with Strava upload option.
 *
 * Shows summary stats, optional HR chart, Upload to Strava button,
 * and Maybe Later to dismiss.
 */

import { useEffect, useState } from "react";
import {
  Timer,
  Ruler,
  Gauge,
  Activity,
  Zap,
  Flame,
  Heart,
  Upload,
  X,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { Button } from "@/components/ui/button";
import { formatTime, formatPace, formatDistance, formatNum } from "@/lib/format";
import * as api from "@/lib/api";
import type { WorkoutRecord, StrokeRecord } from "@/types";

type CompletionScreenProps = {
  onDismiss: () => void;
};

type StatTone = "ember" | "teal" | "rose" | "slate";

type StatProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
  tone?: StatTone;
  /** Stagger index for entrance animation */
  index?: number;
};

const iconToneClasses: Record<StatTone, string> = {
  ember: "bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary",
  teal: "bg-[color-mix(in_oklch,var(--color-secondary)_22%,transparent)] text-secondary-foreground",
  rose: "bg-[color-mix(in_oklch,var(--color-destructive)_18%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_80%,white)]",
  slate: "bg-muted text-foreground",
};

function Stat({ icon, label, value, unit, tone = "slate", index = 0 }: StatProps) {
  return (
    <div
      className="flex items-center gap-3 rounded-2xl border border-border/80 bg-card/75 px-4 py-3 opacity-0 backdrop-blur-sm"
      style={{
        animation: `stat-in 0.4s ease-out ${index * 60}ms forwards`,
      }}
    >
      <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${iconToneClasses[tone]}`}>
        {icon}
      </div>
      <div className="flex-1">
        <div className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 text-lg font-semibold tabular-nums text-foreground">
          {value}
          {unit && (
            <span className="ml-1 text-sm font-normal text-muted-foreground">
              {unit}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function CompletionScreen({ onDismiss }: CompletionScreenProps) {
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>([]);
  const [strokes, setStrokes] = useState<StrokeRecord[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);

  useEffect(() => {
    api.listWorkouts(1, 0).then(setWorkouts).catch(() => {});
  }, []);

  const workout = workouts[0] ?? null;

  useEffect(() => {
    if (workout) {
      api.getStrokes(workout.id).then(setStrokes).catch(() => {});
    }
  }, [workout]);

  const handleUpload = async () => {
    if (!workout) return;
    setUploading(true);
    try {
      await api.uploadWorkout(workout.id);
      setUploadDone(true);
    } catch {
      // Error handled by API
    } finally {
      setUploading(false);
    }
  };

  const handleSkip = async () => {
    if (workout) {
      await api.skipWorkout(workout.id).catch(() => {});
    }
    await api.resetWorkout().catch(() => {});
    onDismiss();
  };

  const hrData = strokes
    .filter((s) => s.heart_rate_bpm != null)
    .map((s, i) => ({
      time: i,
      hr: s.heart_rate_bpm,
    }));

  if (!workout) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <div className="text-muted-foreground">Loading summary...</div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto px-4 pb-6 pt-5">
      <div className="mx-auto max-w-3xl">
        <div className="animate-in fade-in slide-in-from-bottom-3 rounded-[2rem] border border-[color-mix(in_oklch,var(--color-primary)_26%,transparent)] bg-[linear-gradient(135deg,color-mix(in_oklch,var(--color-primary)_24%,var(--color-card))_0%,color-mix(in_oklch,var(--color-secondary)_16%,var(--color-card))_100%)] px-5 py-6 shadow-[0_28px_60px_-40px_rgba(0,0,0,0.95)] duration-500">
          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-primary/80">
            Session complete
          </div>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-foreground">
            Strong finish.
          </h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Your workout is saved locally and ready for Strava whenever you are.
          </p>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Stat
            index={0}
            icon={<Timer className="h-4 w-4" />}
            label="Duration"
            value={formatTime(workout.elapsed_seconds)}
            tone="slate"
          />
          <Stat
            index={1}
            icon={<Ruler className="h-4 w-4" />}
            label="Distance"
            value={formatDistance(workout.total_distance_m)}
            unit="m"
            tone="teal"
          />
          <Stat
            index={2}
            icon={<Gauge className="h-4 w-4" />}
            label="Avg Pace"
            value={formatPace(workout.avg_pace_s_per_500m)}
            unit="/500m"
            tone="ember"
          />
          <Stat
            index={3}
            icon={<Activity className="h-4 w-4" />}
            label="Avg Stroke Rate"
            value={formatNum(workout.avg_stroke_rate, 1)}
            unit="spm"
            tone="ember"
          />
          <Stat
            index={4}
            icon={<Zap className="h-4 w-4" />}
            label="Avg Power"
            value={formatNum(workout.avg_power_watts)}
            unit="W"
            tone="teal"
          />
          <Stat
            index={5}
            icon={<Flame className="h-4 w-4" />}
            label="Calories"
            value={formatNum(workout.calories)}
            unit="kcal"
            tone="ember"
          />
          {workout.avg_heart_rate != null && (
            <Stat
              index={6}
              icon={<Heart className="h-4 w-4" />}
              label="Avg / Max HR"
              value={`${workout.avg_heart_rate} / ${workout.max_heart_rate ?? "-"}`}
              unit="bpm"
              tone="rose"
            />
          )}
        </div>

        {hrData.length > 1 && (
          <div className="mt-4 rounded-[1.75rem] border border-[color-mix(in_oklch,var(--color-destructive)_22%,transparent)] bg-[linear-gradient(180deg,color-mix(in_oklch,var(--color-destructive)_12%,var(--color-card))_0%,var(--color-card)_100%)] p-4 shadow-[0_18px_48px_-34px_rgba(0,0,0,0.9)]">
            <div className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[color-mix(in_oklch,var(--color-destructive)_78%,white)]">
              Heart rate
            </div>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={hrData}>
                  <XAxis dataKey="time" hide />
                  <YAxis domain={["auto", "auto"]} hide />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--color-card)",
                      border: "1px solid color-mix(in oklch, var(--color-destructive) 18%, transparent)",
                      borderRadius: "1rem",
                      fontSize: "0.75rem",
                      color: "var(--color-foreground)",
                    }}
                    formatter={(value) => [`${value} bpm`, "HR"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="hr"
                    stroke="var(--color-chart-4)"
                    fill="var(--color-chart-4)"
                    fillOpacity={0.2}
                    strokeWidth={2.5}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <div className="mt-6 space-y-3">
          {uploadDone ? (
            <div
              className="flex items-center justify-center gap-3 rounded-2xl border border-[color-mix(in_oklch,var(--color-secondary)_32%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_16%,transparent)] px-4 py-4"
              style={{ animation: "success-pop 0.4s cubic-bezier(0.34,1.3,0.64,1) forwards" }}
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[color-mix(in_oklch,var(--color-secondary)_30%,transparent)]">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-secondary-foreground"
                >
                  <polyline
                    points="4,10 8,14 16,6"
                    strokeDasharray="28"
                    strokeDashoffset="0"
                    style={{ animation: "check-draw 0.35s ease-out 0.15s both" }}
                  />
                </svg>
              </span>
              <div>
                <div className="font-semibold text-secondary-foreground">Queued for Strava</div>
                <div className="text-xs text-secondary-foreground/70">Should appear on your profile shortly.</div>
              </div>
            </div>
          ) : (
            <Button
              size="lg"
              className="h-14 w-full text-lg shadow-[0_16px_32px_-20px_color-mix(in_oklch,var(--color-primary)_55%,black)]"
              onClick={handleUpload}
              disabled={uploading}
            >
              <Upload className="mr-2 h-5 w-5" />
              {uploading ? "Uploading..." : "Upload to Strava"}
            </Button>
          )}
          <Button
            size="lg"
            variant="ghost"
            className="h-12 w-full rounded-2xl border border-border/80 bg-card/55"
            onClick={handleSkip}
          >
            <X className="mr-2 h-4 w-4" />
            Maybe Later
          </Button>
        </div>
      </div>
    </div>
  );
}
