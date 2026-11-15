/**
 * CompletionScreen - workout summary.
 *
 * Shows summary stats and an optional HR chart. Integrations only appear
 * when they are set up: the HTTP export's delivery status when an export URL
 * is configured, and the Strava upload when a Strava account is connected.
 * With neither, a single Done button dismisses the screen.
 */

import { useEffect, useRef, useState } from "react";
import {
  Timer,
  Ruler,
  Gauge,
  Activity,
  Zap,
  Flame,
  Heart,
  Upload,
  CheckCircle,
  AlertCircle,
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
import { exportStatusClassName, exportStatusLabel } from "@/lib/exportStatus";
import { exportConfigured, stravaReady } from "@/lib/integrations";
import type { ExportInfo, StravaStatus, WorkoutRecord, StrokeRecord } from "@/types";

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

type UploadState = "idle" | "uploading" | "polling" | "done" | "failed";

export function CompletionScreen({ onDismiss }: CompletionScreenProps) {
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>([]);
  const [strokes, setStrokes] = useState<StrokeRecord[]>([]);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [includeHr, setIncludeHr] = useState(true);
  const [strava, setStrava] = useState<StravaStatus | null>(null);
  const [exportInfo, setExportInfo] = useState<ExportInfo | null>(null);
  // Latest copy of the workout, refreshed while its export is in flight.
  const [exported, setExported] = useState<WorkoutRecord | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.listWorkouts(1, 0).then(setWorkouts).catch(() => {});
    api.getSettings().then(data => setIncludeHr(data.include_hr_in_strava_upload)).catch(() => {});
    api.getStravaStatus().then(setStrava).catch(() => {});
    api.getExportStatus().then(setExportInfo).catch(() => {});
  }, []);

  const workout = workouts[0] ?? null;
  const stravaOn = stravaReady(strava);
  const exportOn = exportConfigured(exportInfo);

  // The backend sends the workout as soon as it's saved; follow it until it
  // leaves PENDING/SENDING (or give up after ~40 s and show what we have).
  useEffect(() => {
    if (!workout || !exportOn) return;
    let cancelled = false;
    (async () => {
      for (let i = 0; i < 20 && !cancelled; i++) {
        try {
          const w = await api.getWorkout(workout.id);
          if (cancelled) return;
          setExported(w);
          if (w.export_status !== "PENDING" && w.export_status !== "SENDING") return;
          if (w.export_status === "PENDING" && !exportInfo?.auto_send) return;
        } catch {
          // keep trying
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workout, exportOn, exportInfo?.auto_send]);

  useEffect(() => {
    if (workout) {
      api.getStrokes(workout.id).then(setStrokes).catch(() => {});
    }
  }, [workout]);

  // Poll upload status after queuing
  useEffect(() => {
    if (uploadState !== "polling" || !workout) return;

    pollRef.current = setInterval(async () => {
      try {
        const w = await api.getWorkout(workout.id);
        if (w.strava_upload_status === "UPLOADED") {
          clearInterval(pollRef.current!);
          setUploadState("done");
        } else if (w.strava_upload_status === "FAILED") {
          clearInterval(pollRef.current!);
          setUploadError(w.strava_error ?? "Upload failed");
          setUploadState("failed");
        }
      } catch {
        // Keep polling
      }
    }, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [uploadState, workout]);

  const handleUpload = async () => {
    if (!workout) return;
    setUploadState("uploading");
    setUploadError(null);
    try {
      await api.uploadWorkout(workout.id, includeHr);
      setUploadState("polling");
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload request failed");
      setUploadState("failed");
    }
  };

  const handleDone = async () => {
    await api.resetWorkout().catch(() => {});
    onDismiss();
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
            {stravaOn
              ? "Your workout is saved and ready for Strava whenever you are."
              : "Your workout is saved."}
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
          {exportOn && (() => {
            const status = exported?.export_status ?? "PENDING";
            const inFlight = status === "PENDING" || status === "SENDING";
            return (
              <div className="flex items-center gap-3 rounded-2xl border border-border/80 bg-card/75 px-4 py-4">
                {inFlight && exportInfo?.auto_send ? (
                  <div className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-secondary-foreground/30 border-t-secondary-foreground" />
                ) : status === "SENT" ? (
                  <CheckCircle className="h-6 w-6 shrink-0 text-secondary-foreground" />
                ) : status === "FAILED" || status === "REJECTED" ? (
                  <AlertCircle className="h-6 w-6 shrink-0 text-destructive" />
                ) : null}
                <div className="min-w-0 flex-1">
                  <div className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Export to {exportInfo?.target_host}
                  </div>
                  <div className="mt-0.5 truncate text-sm text-foreground">
                    {status === "SENT"
                      ? "Delivered"
                      : status === "FAILED"
                        ? "Couldn't reach it. BuoyCast will keep retrying."
                        : exported?.export_error ??
                          (inFlight
                            ? exportInfo?.auto_send
                              ? "Sending..."
                              : "Auto-send is off. Send it from Workout History."
                            : "Not sent")}
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${exportStatusClassName[status]}`}
                >
                  {exportStatusLabel[status]}
                </span>
              </div>
            );
          })()}

          {!stravaOn ? null : uploadState === "done" ? (
            <div
              className="flex items-center gap-3 rounded-2xl border border-[color-mix(in_oklch,var(--color-secondary)_32%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_16%,transparent)] px-4 py-4"
              style={{ animation: "success-pop 0.4s cubic-bezier(0.34,1.3,0.64,1) forwards" }}
            >
              <CheckCircle className="h-9 w-9 shrink-0 text-secondary-foreground" />
              <div>
                <div className="font-semibold text-secondary-foreground">Uploaded to Strava</div>
                <div className="text-xs text-secondary-foreground/70">Activity is on your profile.</div>
              </div>
            </div>
          ) : uploadState === "polling" ? (
            <div className="flex items-center gap-3 rounded-2xl border border-[color-mix(in_oklch,var(--color-secondary)_22%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_10%,transparent)] px-4 py-4">
              <div className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-secondary-foreground/30 border-t-secondary-foreground" />
              <div className="text-sm font-medium text-secondary-foreground/80">Processing on Strava...</div>
            </div>
          ) : uploadState === "failed" ? (
            <div className="flex items-center gap-3 rounded-2xl border border-destructive/32 bg-destructive/10 px-4 py-4">
              <AlertCircle className="h-6 w-6 shrink-0 text-destructive" />
              <div>
                <div className="font-semibold text-destructive-foreground">Upload failed</div>
                {uploadError && <div className="text-xs text-destructive-foreground/70">{uploadError}</div>}
              </div>
            </div>
          ) : (
            <>
              {hrData.length > 0 && uploadState === "idle" && (
                <label className="flex cursor-pointer items-center gap-4 rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm hover:bg-card/90 transition-colors">
                  <div className="flex-1">
                    <div className="font-semibold text-foreground">Include Heart Rate Data</div>
                    <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                      Send HR to Strava
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={includeHr}
                    onChange={(e) => setIncludeHr(e.target.checked)}
                    className="h-6 w-6 rounded-md border-border accent-primary"
                  />
                </label>
              )}
              <Button
                size="lg"
                className="h-14 w-full text-lg shadow-[0_16px_32px_-20px_color-mix(in_oklch,var(--color-primary)_55%,black)]"
                onClick={handleUpload}
                disabled={uploadState === "uploading"}
              >
                <Upload className="mr-2 h-5 w-5" />
                {uploadState === "uploading" ? "Uploading..." : "Upload to Strava"}
              </Button>
            </>
          )}

          {!stravaOn || uploadState === "done" ? (
            <Button
              size="lg"
              className="h-14 w-full text-lg"
              onClick={handleDone}
            >
              Done
            </Button>
          ) : (
            <Button
              size="lg"
              variant="ghost"
              className="h-12 w-full rounded-2xl border border-border/80 bg-card/55"
              onClick={handleSkip}
              disabled={uploadState === "uploading" || uploadState === "polling"}
            >
              {uploadState === "failed" ? (
                <>
                  <X className="mr-2 h-4 w-4" />
                  Skip Strava
                </>
              ) : (
                <>
                  <X className="mr-2 h-4 w-4" />
                  Maybe Later
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
