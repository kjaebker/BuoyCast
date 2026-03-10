/**
 * CompletionScreen — workout summary with Strava upload option.
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

type StatProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit?: string;
};

function Stat({ icon, label, value, unit }: StatProps) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="text-muted-foreground">{icon}</div>
      <div className="flex-1">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-lg font-semibold tabular-nums">
          {value}
          {unit && (
            <span className="text-sm font-normal text-muted-foreground ml-1">
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

  // Load the most recent workout
  useEffect(() => {
    api.listWorkouts(1, 0).then(setWorkouts).catch(() => {});
  }, []);

  const workout = workouts[0] ?? null;

  // Load strokes for HR chart
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
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="text-muted-foreground">Loading summary...</div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4">
      <h2 className="text-xl font-bold text-center mb-4">Workout Complete</h2>

      <div className="max-w-md mx-auto space-y-1">
        <Stat
          icon={<Timer className="h-4 w-4" />}
          label="Duration"
          value={formatTime(workout.elapsed_seconds)}
        />
        <Stat
          icon={<Ruler className="h-4 w-4" />}
          label="Distance"
          value={formatDistance(workout.total_distance_m)}
          unit="m"
        />
        <Stat
          icon={<Gauge className="h-4 w-4" />}
          label="Avg Pace"
          value={formatPace(workout.avg_pace_s_per_500m)}
          unit="/500m"
        />
        <Stat
          icon={<Activity className="h-4 w-4" />}
          label="Avg Stroke Rate"
          value={formatNum(workout.avg_stroke_rate, 1)}
          unit="spm"
        />
        <Stat
          icon={<Zap className="h-4 w-4" />}
          label="Avg Power"
          value={formatNum(workout.avg_power_watts)}
          unit="W"
        />
        <Stat
          icon={<Flame className="h-4 w-4" />}
          label="Calories"
          value={formatNum(workout.calories)}
          unit="kcal"
        />
        {workout.avg_heart_rate != null && (
          <Stat
            icon={<Heart className="h-4 w-4" />}
            label="Avg / Max HR"
            value={`${workout.avg_heart_rate} / ${workout.max_heart_rate ?? "–"}`}
            unit="bpm"
          />
        )}
      </div>

      {/* HR chart */}
      {hrData.length > 1 && (
        <div className="mt-4 max-w-md mx-auto rounded-xl bg-card p-4 shadow-sm border border-border">
          <div className="text-xs text-muted-foreground mb-2">Heart Rate</div>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={hrData}>
                <XAxis dataKey="time" hide />
                <YAxis domain={["auto", "auto"]} hide />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--color-card))",
                    border: "1px solid hsl(var(--color-border))",
                    borderRadius: "0.5rem",
                    fontSize: "0.75rem",
                  }}
                  formatter={(value) => [`${value} bpm`, "HR"]}
                />
                <Area
                  type="monotone"
                  dataKey="hr"
                  stroke="hsl(0, 84%, 60%)"
                  fill="hsl(0, 84%, 60%)"
                  fillOpacity={0.2}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="mt-6 max-w-md mx-auto space-y-3">
        {uploadDone ? (
          <div className="text-center text-green-500 font-medium py-3">
            Upload queued — check Strava shortly
          </div>
        ) : (
          <Button
            size="lg"
            className="w-full h-14 text-lg"
            onClick={handleUpload}
            disabled={uploading}
          >
            <Upload className="h-5 w-5 mr-2" />
            {uploading ? "Uploading..." : "Upload to Strava"}
          </Button>
        )}
        <Button
          size="lg"
          variant="ghost"
          className="w-full h-12"
          onClick={handleSkip}
        >
          <X className="h-4 w-4 mr-2" />
          Maybe Later
        </Button>
      </div>
    </div>
  );
}
