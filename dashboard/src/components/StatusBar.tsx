/**
 * StatusBar - S4 + TICKR connection status, Strava auth, HR preview.
 * Responsive: collapses to icons on iPhone.
 */

import { useEffect, useState } from "react";
import { Wifi, WifiOff, Heart, HeartOff, Upload, UploadCloud, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { getStravaStatus } from "@/lib/api";
import type { StravaStatus } from "@/types";
import type { WorkoutSocketState } from "@/hooks/useWorkoutSocket";

type StatusBarProps = {
  connectionStatus: WorkoutSocketState["connectionStatus"];
  metrics: WorkoutSocketState["metrics"];
  onOpenSettings: () => void;
};

type PillProps = {
  active: boolean;
  activeClassName: string;
  inactiveClassName: string;
  icon: React.ReactNode;
  label: string;
};

function StatusPill({ active, activeClassName, inactiveClassName, icon, label }: PillProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em]",
        active ? activeClassName : inactiveClassName,
      )}
    >
      {icon}
      {active && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current opacity-90" />
      )}
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}

export function StatusBar({ connectionStatus, metrics, onOpenSettings }: StatusBarProps) {
  const [strava, setStrava] = useState<StravaStatus | null>(null);

  useEffect(() => {
    getStravaStatus()
      .then(setStrava)
      .catch(() => setStrava(null));
  }, []);

  const s4Connected = connectionStatus === "connected";
  const hrValue = metrics?.heart_rate_bpm;

  return (
    <div className="sticky top-0 z-10 border-b border-border/70 bg-[color-mix(in_oklch,var(--color-card)_82%,transparent)] px-4 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-2.5 overflow-x-auto">
        <StatusPill
          active={s4Connected}
          activeClassName="border-[color-mix(in_oklch,var(--color-secondary)_45%,transparent)] bg-[color-mix(in_oklch,var(--color-secondary)_18%,transparent)] text-secondary-foreground"
          inactiveClassName="border-border bg-card/70 text-muted-foreground"
          icon={s4Connected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
          label={s4Connected ? "S4 live" : "S4 offline"}
        />

        <StatusPill
          active={hrValue != null}
          activeClassName="border-[color-mix(in_oklch,var(--color-destructive)_38%,transparent)] bg-[color-mix(in_oklch,var(--color-destructive)_16%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_82%,white)]"
          inactiveClassName="border-border bg-card/70 text-muted-foreground"
          icon={hrValue != null ? <Heart className="h-3.5 w-3.5 fill-current" /> : <HeartOff className="h-3.5 w-3.5" />}
          label={hrValue != null ? `${hrValue} bpm` : "HR waiting"}
        />

        <div className="ml-auto flex items-center gap-2.5">
          <StatusPill
            active={Boolean(strava?.connected)}
            activeClassName="border-[color-mix(in_oklch,var(--color-primary)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary"
            inactiveClassName="border-border bg-card/70 text-muted-foreground"
            icon={strava?.connected ? <UploadCloud className="h-3.5 w-3.5" /> : <Upload className="h-3.5 w-3.5" />}
            label={strava?.connected ? "Strava ready" : "No Strava"}
          />
          <button
            onClick={onOpenSettings}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border/80 bg-card/70 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            aria-label="Settings"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
