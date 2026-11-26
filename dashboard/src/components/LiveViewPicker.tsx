/**
 * LiveViewPicker — choose between the rowing scene and a live graph of one
 * metric. The choice is remembered per device.
 */

import { Activity, Gauge, Heart, Sailboat, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { LiveView } from "@/hooks/useLiveView";

const OPTIONS: { view: LiveView; label: string; icon: React.ReactNode }[] = [
  { view: LiveView.SCENE, label: "Scene", icon: <Sailboat className="h-5 w-5" /> },
  { view: LiveView.PACE, label: "Pace", icon: <Gauge className="h-5 w-5" /> },
  { view: LiveView.POWER, label: "Watts", icon: <Zap className="h-5 w-5" /> },
  { view: LiveView.STROKE_RATE, label: "SPM", icon: <Activity className="h-5 w-5" /> },
  { view: LiveView.HEART_RATE, label: "HR", icon: <Heart className="h-5 w-5" /> },
];

type LiveViewPickerProps = {
  value: LiveView;
  onChange: (view: LiveView) => void;
};

export function LiveViewPicker({ value, onChange }: LiveViewPickerProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Live view"
      className="mb-3 grid grid-cols-5 gap-1 rounded-2xl border border-border/80 bg-card/70 p-1"
    >
      {OPTIONS.map((o) => {
        const selected = o.view === value;
        return (
          <button
            key={o.view}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(o.view)}
            className={cn(
              "flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl text-[0.7rem] font-semibold uppercase tracking-[0.12em] transition-colors",
              selected
                ? "bg-primary text-primary-foreground shadow-[0_8px_24px_-12px_var(--color-primary)]"
                : "text-muted-foreground active:bg-muted/60",
            )}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
