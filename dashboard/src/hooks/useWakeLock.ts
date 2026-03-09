/**
 * Screen Wake Lock hook.
 *
 * Acquires wake lock when workout is ACTIVE, releases on PAUSED/IDLE/SUMMARY.
 * Handles Safari quirks and re-acquires on visibilitychange.
 */

import { useEffect, useRef } from "react";
import type { WorkoutState } from "@/types";

export function useWakeLock(workoutState: WorkoutState): void {
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);

  const acquire = async () => {
    if (!("wakeLock" in navigator)) return;
    try {
      wakeLockRef.current = await navigator.wakeLock.request("screen");
    } catch {
      // Wake lock request failed (e.g. low battery, background tab)
    }
  };

  const release = async () => {
    if (wakeLockRef.current) {
      try {
        await wakeLockRef.current.release();
      } catch {
        // Already released
      }
      wakeLockRef.current = null;
    }
  };

  // Acquire/release based on workout state
  useEffect(() => {
    if (workoutState === "ACTIVE") {
      acquire();
    } else {
      release();
    }

    return () => {
      release();
    };
  }, [workoutState]);

  // Re-acquire on visibility change (Safari releases wake lock on tab switch)
  useEffect(() => {
    const handleVisibility = () => {
      if (
        document.visibilityState === "visible" &&
        workoutState === "ACTIVE" &&
        !wakeLockRef.current
      ) {
        acquire();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibility);
  }, [workoutState]);
}
