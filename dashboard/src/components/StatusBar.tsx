/**
 * StatusBar — S4 + TICKR connection status, Strava auth, HR preview.
 * Responsive: collapses to icons on iPhone.
 */

import { useEffect, useState } from "react";
import {
  Wifi,
  WifiOff,
  Heart,
  HeartOff,
  Upload,
  UploadCloud,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getStravaStatus } from "@/lib/api";
import type { StravaStatus } from "@/types";
import type { WorkoutSocketState } from "@/hooks/useWorkoutSocket";

type StatusBarProps = {
  connectionStatus: WorkoutSocketState["connectionStatus"];
  metrics: WorkoutSocketState["metrics"];
};

export function StatusBar({ connectionStatus, metrics }: StatusBarProps) {
  const [strava, setStrava] = useState<StravaStatus | null>(null);

  useEffect(() => {
    getStravaStatus()
      .then(setStrava)
      .catch(() => setStrava(null));
  }, []);

  const s4Connected = connectionStatus === "connected";
  const hrValue = metrics?.heart_rate_bpm;

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-card text-card-foreground">
      {/* S4 status */}
      <div
        className={cn(
          "flex items-center gap-1.5 text-sm",
          s4Connected ? "text-green-500" : "text-red-500"
        )}
      >
        {s4Connected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
        <span className="hidden sm:inline">S4</span>
      </div>

      {/* TICKR / HR status */}
      <div
        className={cn(
          "flex items-center gap-1.5 text-sm",
          hrValue != null ? "text-red-400" : "text-muted-foreground"
        )}
      >
        {hrValue != null ? (
          <Heart className="h-4 w-4 fill-current" />
        ) : (
          <HeartOff className="h-4 w-4" />
        )}
        <span className="hidden sm:inline">
          {hrValue != null ? `${hrValue} bpm` : "–"}
        </span>
      </div>

      <div className="flex-1" />

      {/* Strava status */}
      <div
        className={cn(
          "flex items-center gap-1.5 text-sm",
          strava?.connected ? "text-orange-500" : "text-muted-foreground"
        )}
      >
        {strava?.connected ? (
          <UploadCloud className="h-4 w-4" />
        ) : (
          <Upload className="h-4 w-4" />
        )}
        <span className="hidden sm:inline">
          {strava?.connected ? "Strava" : "No Strava"}
        </span>
      </div>
    </div>
  );
}
