/**
 * WorkoutHistory - paginated list of completed workouts.
 *
 * Per-workout Strava status badges, upload/retry/link actions.
 * Uses Sheet for mobile slide-up detail panel.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Clock,
  Ruler,
  ChevronRight,
  Upload,
  RefreshCw,
  ExternalLink,
  Trash2,
  X,
  Gauge,
  Activity,
  Zap,
  Flame,
  Heart,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { formatTime, formatDistance, formatPace, formatNum } from "@/lib/format";
import * as api from "@/lib/api";
import type { WorkoutRecord, StravaUploadStatus } from "@/types";

const PAGE_SIZE = 10;

const statusBadgeVariant: Record<
  StravaUploadStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  PENDING: "outline",
  UPLOADING: "secondary",
  UPLOADED: "default",
  FAILED: "destructive",
  SKIPPED: "secondary",
};

const statusBadgeClassName: Record<StravaUploadStatus, string> = {
  PENDING: "border-[color-mix(in_oklch,var(--color-primary)_36%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_12%,transparent)] text-primary",
  UPLOADING: "border-transparent bg-[color-mix(in_oklch,var(--color-secondary)_24%,transparent)] text-secondary-foreground",
  UPLOADED: "border-transparent bg-[color-mix(in_oklch,var(--color-secondary)_34%,transparent)] text-secondary-foreground",
  FAILED: "border-transparent bg-[color-mix(in_oklch,var(--color-destructive)_20%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_84%,white)]",
  SKIPPED: "border-transparent bg-muted text-muted-foreground",
};

type WorkoutHistoryProps = {
  visible: boolean;
};

type DetailStatTone = "ember" | "teal" | "rose" | "slate";

type DetailStatProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: DetailStatTone;
};

const detailStatToneClasses: Record<DetailStatTone, string> = {
  ember:
    "border-[color-mix(in_oklch,var(--color-primary)_26%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_12%,var(--color-card))] text-primary",
  teal:
    "border-[color-mix(in_oklch,var(--color-secondary)_28%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_14%,var(--color-card))] text-secondary-foreground",
  rose:
    "border-[color-mix(in_oklch,var(--color-destructive)_24%,transparent)] bg-[color-mix(in_oklch,var(--color-destructive)_12%,var(--color-card))] text-[color-mix(in_oklch,var(--color-destructive)_84%,white)]",
  slate: "border-border/80 bg-card/70 text-foreground",
};

function DetailStat({ icon, label, value, tone = "slate" }: DetailStatProps) {
  return (
    <div className={`rounded-[1.35rem] border p-4 shadow-[0_16px_34px_-28px_rgba(0,0,0,0.95)] ${detailStatToneClasses[tone]}`}>
      <div className="mb-3 flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-current/75">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-black/10 text-current">
          {icon}
        </span>
        {label}
      </div>
      <div className="text-lg font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  );
}

export function WorkoutHistory({ visible }: WorkoutHistoryProps) {
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [selected, setSelected] = useState<WorkoutRecord | null>(null);

  const load = useCallback(async (off: number) => {
    try {
      const data = await api.listWorkouts(PAGE_SIZE, off);
      if (off === 0) {
        setWorkouts(data);
      } else {
        setWorkouts((prev) => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE_SIZE);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (visible) load(0);
  }, [visible, load]);

  const handleUpload = async (id: string) => {
    await api.uploadWorkout(id).catch(() => {});
    load(0);
  };

  const handleDelete = async (id: string) => {
    await api.deleteWorkout(id).catch(() => {});
    setSelected(null);
    load(0);
  };

  if (!visible) return null;

  return (
    <div className="flex-1 overflow-auto px-4 pb-4 pt-5">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-primary/80">
            Past sessions
          </div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-foreground">
            Workout History
          </h2>
        </div>
      </div>

      {workouts.length === 0 && (
        <div className="rounded-[1.5rem] border border-border/80 bg-card/70 px-4 py-8 text-center text-muted-foreground">
          No workouts yet
        </div>
      )}

      <div className="space-y-3">
        {workouts.map((w) => (
          <button
            key={w.id}
            className="group flex w-full items-center gap-3 rounded-[1.5rem] border border-border/80 bg-[linear-gradient(135deg,color-mix(in_oklch,var(--color-card)_90%,transparent)_0%,color-mix(in_oklch,var(--color-primary)_8%,var(--color-card))_100%)] p-4 text-left shadow-[0_18px_40px_-32px_rgba(0,0,0,0.95)] transition-colors active:bg-accent/50"
            onClick={() => setSelected(w)}
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-foreground">
                {new Date(w.started_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-primary/90" />
                  {formatTime(w.elapsed_seconds)}
                </span>
                <span className="flex items-center gap-1">
                  <Ruler className="h-3 w-3 text-secondary-foreground" />
                  {formatDistance(w.total_distance_m)}m
                </span>
              </div>
            </div>
            <Badge
              variant={statusBadgeVariant[w.strava_upload_status]}
              className={statusBadgeClassName[w.strava_upload_status]}
            >
              {w.strava_upload_status}
            </Badge>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-active:translate-x-0.5" />
          </button>
        ))}
      </div>

      {hasMore && workouts.length > 0 && (
        <Button
          variant="ghost"
          className="mt-3 w-full rounded-2xl border border-border/80 bg-card/55"
          onClick={() => {
            const newOffset = offset + PAGE_SIZE;
            setOffset(newOffset);
            load(newOffset);
          }}
        >
          Load more
        </Button>
      )}

      <Sheet open={selected !== null} onOpenChange={() => setSelected(null)}>
        <SheetContent side="bottom">
          {selected && (
            <>
              <div className="relative z-10 mx-auto mb-4 h-1.5 w-12 rounded-full bg-muted-foreground/30" />

              <SheetHeader className="relative z-10 mb-4 pr-12">
                <div className="inline-flex w-fit items-center rounded-full border border-[color-mix(in_oklch,var(--color-primary)_28%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_14%,transparent)] px-3 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-primary">
                  Saved workout
                </div>
                <SheetTitle className="mt-2 text-2xl font-bold tracking-tight">
                  {new Date(selected.started_at).toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                  })}
                </SheetTitle>
                <SheetDescription>
                  Started at {new Date(selected.started_at).toLocaleTimeString(undefined, {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </SheetDescription>
              </SheetHeader>

              <div className="relative z-10 rounded-[1.75rem] border border-[color-mix(in_oklch,var(--color-primary)_24%,transparent)] bg-[linear-gradient(135deg,color-mix(in_oklch,var(--color-primary)_20%,var(--color-card))_0%,color-mix(in_oklch,var(--color-secondary)_16%,var(--color-card))_100%)] px-5 py-5 shadow-[0_24px_56px_-34px_rgba(0,0,0,0.95)]">
                <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-primary/80">
                  Session snapshot
                </div>
                <div className="mt-2 flex items-end gap-3">
                  <div>
                    <div className="text-3xl font-bold tabular-nums text-foreground">
                      {formatDistance(selected.total_distance_m)}
                    </div>
                    <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      meters rowed
                    </div>
                  </div>
                  <div className="mb-1 rounded-full border border-[color-mix(in_oklch,var(--color-secondary)_24%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_16%,transparent)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-secondary-foreground">
                    {selected.strava_upload_status}
                  </div>
                </div>
              </div>

              <div className="relative z-10 mt-4 grid grid-cols-2 gap-3">
                <DetailStat
                  icon={<Clock className="h-4 w-4" />}
                  label="Duration"
                  value={formatTime(selected.elapsed_seconds)}
                  tone="slate"
                />
                <DetailStat
                  icon={<Gauge className="h-4 w-4" />}
                  label="Avg Pace"
                  value={`${formatPace(selected.avg_pace_s_per_500m)} /500m`}
                  tone="ember"
                />
                <DetailStat
                  icon={<Activity className="h-4 w-4" />}
                  label="Stroke Rate"
                  value={`${formatNum(selected.avg_stroke_rate, 1)} spm`}
                  tone="ember"
                />
                <DetailStat
                  icon={<Zap className="h-4 w-4" />}
                  label="Avg Power"
                  value={`${formatNum(selected.avg_power_watts)} W`}
                  tone="teal"
                />
                <DetailStat
                  icon={<Flame className="h-4 w-4" />}
                  label="Calories"
                  value={`${selected.calories}`}
                  tone="ember"
                />
                <DetailStat
                  icon={<Heart className="h-4 w-4" />}
                  label="Avg / Max HR"
                  value={
                    selected.avg_heart_rate != null
                      ? `${selected.avg_heart_rate} / ${selected.max_heart_rate ?? "-"} bpm`
                      : "-"
                  }
                  tone="rose"
                />
              </div>

              <div className="relative z-10 mt-4 flex gap-2">
                {(selected.strava_upload_status === "PENDING" ||
                  selected.strava_upload_status === "FAILED" ||
                  selected.strava_upload_status === "SKIPPED") && (
                  <Button className="flex-1" onClick={() => handleUpload(selected.id)}>
                    {selected.strava_upload_status === "FAILED" ? (
                      <RefreshCw className="mr-2 h-4 w-4" />
                    ) : (
                      <Upload className="mr-2 h-4 w-4" />
                    )}
                    {selected.strava_upload_status === "FAILED"
                      ? "Retry Upload"
                      : "Upload to Strava"}
                  </Button>
                )}
                {selected.strava_upload_status === "UPLOADED" &&
                  selected.strava_activity_id && (
                    <Button
                      variant="secondary"
                      className="flex-1"
                      onClick={() =>
                        window.open(
                          `https://www.strava.com/activities/${selected.strava_activity_id}`,
                          "_blank",
                        )
                      }
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View on Strava
                    </Button>
                  )}
                <Button
                  variant="destructive"
                  size="icon"
                  onClick={() => handleDelete(selected.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <Button
                variant="ghost"
                className="relative z-10 mt-3 h-12 w-full rounded-2xl border border-border/80 bg-card/55"
                onClick={() => setSelected(null)}
              >
                <X className="mr-2 h-4 w-4" />
                Done
              </Button>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
