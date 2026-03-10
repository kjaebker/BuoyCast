/**
 * WorkoutControls — large touch targets for workout state transitions.
 *
 * IDLE: Start Workout
 * ACTIVE: Pause + End Workout
 * PAUSED: Resume + End Workout
 * SUMMARY: (handled by CompletionScreen)
 *
 * End Workout shows a confirmation dialog.
 */

import { useState } from "react";
import { Play, Pause, Square, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import * as api from "@/lib/api";
import type { WorkoutState } from "@/types";

type WorkoutControlsProps = {
  workoutState: WorkoutState;
};

export function WorkoutControls({ workoutState }: WorkoutControlsProps) {
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: () => Promise<unknown>) => {
    setLoading(true);
    try {
      await action();
    } catch {
      // API errors handled elsewhere
    } finally {
      setLoading(false);
    }
  };

  if (workoutState === "SUMMARY") return null;

  return (
    <div className="border-t border-border bg-card p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <div className="flex gap-3 justify-center">
        {workoutState === "IDLE" && (
          <Button
            size="lg"
            className="h-16 px-8 text-lg flex-1 max-w-xs"
            onClick={() => handleAction(api.startWorkout)}
            disabled={loading}
          >
            <Play className="h-5 w-5 mr-2" />
            Start Workout
          </Button>
        )}

        {workoutState === "ACTIVE" && (
          <>
            <Button
              size="lg"
              variant="secondary"
              className="h-16 px-6 text-lg flex-1 max-w-[10rem]"
              onClick={() => handleAction(api.pauseWorkout)}
              disabled={loading}
            >
              <Pause className="h-5 w-5 mr-2" />
              Pause
            </Button>
            <Button
              size="lg"
              variant="destructive"
              className="h-16 px-6 text-lg flex-1 max-w-[10rem]"
              onClick={() => setConfirmEnd(true)}
              disabled={loading}
            >
              <Square className="h-5 w-5 mr-2" />
              End
            </Button>
          </>
        )}

        {workoutState === "PAUSED" && (
          <>
            <Button
              size="lg"
              className="h-16 px-6 text-lg flex-1 max-w-[10rem]"
              onClick={() => handleAction(api.resumeWorkout)}
              disabled={loading}
            >
              <RotateCcw className="h-5 w-5 mr-2" />
              Resume
            </Button>
            <Button
              size="lg"
              variant="destructive"
              className="h-16 px-6 text-lg flex-1 max-w-[10rem]"
              onClick={() => setConfirmEnd(true)}
              disabled={loading}
            >
              <Square className="h-5 w-5 mr-2" />
              End
            </Button>
          </>
        )}
      </div>

      {/* End confirmation dialog */}
      <Dialog open={confirmEnd} onOpenChange={setConfirmEnd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>End Workout?</DialogTitle>
            <DialogDescription>
              This will finish your current workout session. You can upload it to
              Strava afterwards.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmEnd(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmEnd(false);
                handleAction(api.endWorkout);
              }}
            >
              End Workout
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
