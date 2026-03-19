/**
 * RowingDetectedPrompt — modal that appears when rowing is detected while idle.
 *
 * Counts down 5 seconds and auto-starts the workout unless the user dismisses.
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
  DialogFooter,
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

        <DialogFooter>
          <Button variant="ghost" onClick={onDismiss}>
            Don't start
          </Button>
          <Button onClick={onStart}>
            <Play className="mr-2 h-4 w-4" />
            Start now
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
