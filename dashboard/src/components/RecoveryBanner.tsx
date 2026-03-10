/**
 * RecoveryBanner - shown on startup when an incomplete workout is detected.
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
  const [workout, setWorkout] = useState<WorkoutRecord | null | undefined>(undefined);
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
      className="mx-4 mt-3 flex items-start gap-3 rounded-[1.5rem] border border-[color-mix(in_oklch,var(--color-primary)_30%,transparent)] bg-[linear-gradient(135deg,color-mix(in_oklch,var(--color-primary)_18%,var(--color-card))_0%,color-mix(in_oklch,var(--color-secondary)_12%,var(--color-card))_100%)] p-4 shadow-[0_18px_40px_-32px_rgba(0,0,0,0.95)]"
      role="alert"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_oklch,var(--color-primary)_20%,transparent)] text-primary">
        <AlertTriangle className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">
          Unfinished workout from {startedAt}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {formatDistance(workout.total_distance_m)}m · {formatTime(workout.elapsed_seconds)} · {workout.total_strokes} strokes
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="min-h-[2.5rem] shrink-0 rounded-xl border-[color-mix(in_oklch,var(--color-primary)_34%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_12%,transparent)] text-primary hover:bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)]"
        onClick={handleDiscard}
        disabled={discarding}
      >
        {discarding ? "Discarding..." : "Discard"}
      </Button>
    </div>
  );
}
