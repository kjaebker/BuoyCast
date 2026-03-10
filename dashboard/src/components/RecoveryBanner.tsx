/**
 * RecoveryBanner — shown on startup when an incomplete workout is detected.
 * Lets the user discard (mark SKIPPED) the orphaned workout.
 */

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getRecoveryWorkout, discardRecoveryWorkout } from "@/lib/api";
import type { WorkoutRecord } from "@/types";
import { formatDistance, formatTime } from "@/lib/format";

type Props = {
  /** Called after successful discard so parent can react (e.g. refresh history). */
  onDiscard?: () => void;
};

export function RecoveryBanner({ onDiscard }: Props) {
  const [workout, setWorkout] = useState<WorkoutRecord | null | undefined>(
    undefined,
  );
  const [discarding, setDiscarding] = useState(false);

  useEffect(() => {
    getRecoveryWorkout()
      .then((r) => setWorkout(r.workout))
      .catch(() => setWorkout(null));
  }, []);

  if (!workout) return null;

  const startedAt = new Date(workout.started_at).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  async function handleDiscard() {
    if (!workout) return;
    setDiscarding(true);
    try {
      await discardRecoveryWorkout(workout.id);
      setWorkout(null);
      onDiscard?.();
    } catch {
      setDiscarding(false);
    }
  }

  return (
    <div
      className="flex items-start gap-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mx-4 mt-3 p-4"
      role="alert"
    >
      <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-amber-300">
          Unfinished workout from {startedAt}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {formatDistance(workout.total_distance_m)}m ·{" "}
          {formatTime(workout.elapsed_seconds)} · {workout.total_strokes} strokes
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0 border-amber-500/40 text-amber-300 hover:bg-amber-500/10 min-h-[2.5rem]"
        onClick={handleDiscard}
        disabled={discarding}
      >
        {discarding ? "Discarding…" : "Discard"}
      </Button>
    </div>
  );
}
