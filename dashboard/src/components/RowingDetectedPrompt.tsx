/**
 * RowingDetectedPrompt — modal that appears when rowing is detected while idle.
 *
 * Counts down COUNTDOWN_S seconds and auto-starts the workout unless the user
 * dismisses. "Start now" takes focus and is the big target; "Not now" is a
 * quieter, separated button so a mid-stroke tap doesn't cancel by accident.
 * Backdrop click and the X button both dismiss (via onOpenChange → onDismiss).
 */

import { useEffect, useState } from "react";
import { Play, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

const COUNTDOWN_S = 10;

type Props = {
  onStart: () => void;
  onDismiss: () => void;
};

export function RowingDetectedPrompt({ onStart, onDismiss }: Props) {
  const [remaining, setRemaining] = useState(COUNTDOWN_S);

  // Single effect: tick down and fire onStart when count reaches 0
  useEffect(() => {
    let count = COUNTDOWN_S;
    const timer = setInterval(() => {
      count -= 1;
      setRemaining(count);
      if (count <= 0) {
        clearInterval(timer);
        onStart();
      }
    }, 1000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onDismiss(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            Rowing detected
          </DialogTitle>
          <DialogDescription>
            {remaining > 0
              ? `Workout will start automatically in ${remaining}s.`
              : "Starting…"}
          </DialogDescription>
        </DialogHeader>

        {/* Countdown progress bar */}
        <div className="h-1.5 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-1000 ease-linear"
            style={{ width: `${(remaining / COUNTDOWN_S) * 100}%` }}
          />
        </div>

        <div className="mt-2 flex flex-col gap-4">
          <Button autoFocus className="h-16 w-full text-lg" onClick={onStart}>
            <Play className="mr-2 h-5 w-5" />
            Start now
          </Button>
          <Button
            variant="ghost"
            className="h-16 w-full text-base text-muted-foreground"
            onClick={onDismiss}
          >
            Not now
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
