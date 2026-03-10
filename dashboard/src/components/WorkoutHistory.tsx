/**
 * WorkoutHistory — paginated list of completed workouts.
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
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

type WorkoutHistoryProps = {
  visible: boolean;
};

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
    <div className="flex-1 overflow-auto p-4">
      <h2 className="text-lg font-bold mb-3">Workout History</h2>

      {workouts.length === 0 && (
        <div className="text-center text-muted-foreground py-8">
          No workouts yet
        </div>
      )}

      <div className="space-y-2">
        {workouts.map((w) => (
          <button
            key={w.id}
            className="w-full text-left rounded-xl bg-card p-3 shadow-sm border border-border flex items-center gap-3 active:bg-accent transition-colors"
            onClick={() => setSelected(w)}
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">
                {new Date(w.started_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatTime(w.elapsed_seconds)}
                </span>
                <span className="flex items-center gap-1">
                  <Ruler className="h-3 w-3" />
                  {formatDistance(w.total_distance_m)}m
                </span>
              </div>
            </div>
            <Badge variant={statusBadgeVariant[w.strava_upload_status]}>
              {w.strava_upload_status}
            </Badge>
            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
          </button>
        ))}
      </div>

      {hasMore && workouts.length > 0 && (
        <Button
          variant="ghost"
          className="w-full mt-3"
          onClick={() => {
            const newOffset = offset + PAGE_SIZE;
            setOffset(newOffset);
            load(newOffset);
          }}
        >
          Load more
        </Button>
      )}

      {/* Detail sheet */}
      <Sheet open={selected !== null} onOpenChange={() => setSelected(null)}>
        <SheetContent side="bottom">
          {selected && (
            <>
              {/* Drag-handle hint */}
              <div className="flex justify-center pb-2 -mt-2">
                <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
              </div>

              <SheetHeader>
                <SheetTitle>
                  {new Date(selected.started_at).toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </SheetTitle>
              </SheetHeader>

              <div className="py-4 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Duration</span>
                  <span className="font-medium tabular-nums">
                    {formatTime(selected.elapsed_seconds)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Distance</span>
                  <span className="font-medium tabular-nums">
                    {formatDistance(selected.total_distance_m)} m
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Avg Pace</span>
                  <span className="font-medium tabular-nums">
                    {formatPace(selected.avg_pace_s_per_500m)} /500m
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Strokes</span>
                  <span className="font-medium tabular-nums">
                    {selected.total_strokes}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Avg Stroke Rate</span>
                  <span className="font-medium tabular-nums">
                    {formatNum(selected.avg_stroke_rate, 1)} spm
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Avg Power</span>
                  <span className="font-medium tabular-nums">
                    {formatNum(selected.avg_power_watts)} W
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Calories</span>
                  <span className="font-medium tabular-nums">
                    {selected.calories}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Avg / Max HR</span>
                  <span className="font-medium tabular-nums">
                    {selected.avg_heart_rate != null
                      ? `${selected.avg_heart_rate} / ${selected.max_heart_rate ?? "–"} bpm`
                      : "–"}
                  </span>
                </div>
              </div>

              <div className="flex gap-2 pt-2">
                {(selected.strava_upload_status === "PENDING" ||
                  selected.strava_upload_status === "FAILED" ||
                  selected.strava_upload_status === "SKIPPED") && (
                  <Button
                    className="flex-1"
                    onClick={() => handleUpload(selected.id)}
                  >
                    {selected.strava_upload_status === "FAILED" ? (
                      <RefreshCw className="h-4 w-4 mr-2" />
                    ) : (
                      <Upload className="h-4 w-4 mr-2" />
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
                          "_blank"
                        )
                      }
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
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

              {/* Explicit close — much clearer than the tiny X icon */}
              <Button
                variant="secondary"
                className="w-full mt-3 h-12"
                onClick={() => setSelected(null)}
              >
                <X className="h-4 w-4 mr-2" />
                Done
              </Button>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
