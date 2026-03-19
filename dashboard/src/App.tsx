import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { History, Waves } from "lucide-react";
import { useWorkoutSocket } from "@/hooks/useWorkoutSocket";
import { useWakeLock } from "@/hooks/useWakeLock";
import { StatusBar } from "@/components/StatusBar";
import { LiveMetrics } from "@/components/LiveMetrics";
import { WorkoutControls } from "@/components/WorkoutControls";
import { CompletionScreen } from "@/components/CompletionScreen";
import { WorkoutHistory } from "@/components/WorkoutHistory";
import { RecoveryBanner } from "@/components/RecoveryBanner";
import { RowingDetectedPrompt } from "@/components/RowingDetectedPrompt";
import { SettingsScreen } from "@/components/SettingsScreen";
import { Button } from "@/components/ui/button";

function App() {
  const { metrics, workoutState, connectionStatus, dismissSummary } = useWorkoutSocket();
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const [rowingPromptDismissed, setRowingPromptDismissed] = useState(false);

  // Reset dismissal once the user stops rowing so the prompt can reappear
  useEffect(() => {
    if (!metrics?.stroke_rate) {
      setRowingPromptDismissed(false);
    }
  }, [metrics?.stroke_rate]);

  const showRowingPrompt =
    workoutState === "IDLE" &&
    !rowingPromptDismissed &&
    (metrics?.stroke_rate ?? 0) > 0;

  useWakeLock(workoutState);

  const handleDismissCompletion = () => {
    dismissSummary();
    setShowHistory(true);
  };

  return (
    <div className="dark relative isolate flex min-h-dvh flex-col overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--color-primary)_22%,transparent)_0%,color-mix(in_oklch,var(--color-primary)_12%,transparent)_28%,transparent_74%)] opacity-80 blur-[2px]" />
      <div className="pointer-events-none absolute right-[-4rem] top-28 h-48 w-48 rounded-full bg-[color-mix(in_oklch,var(--color-secondary)_36%,transparent)] blur-3xl" />
      <div className="pointer-events-none absolute left-[-5rem] top-72 h-56 w-56 rounded-full bg-[color-mix(in_oklch,var(--color-primary)_16%,transparent)] blur-3xl" />

      <StatusBar
        connectionStatus={connectionStatus}
        metrics={metrics}
        onOpenSettings={() => setShowSettings(true)}
      />

      {connectionStatus === "disconnected" && (
        <div className="mx-4 mt-3 rounded-2xl border border-destructive/35 bg-destructive/12 px-4 py-3 text-center text-sm font-medium text-destructive-foreground shadow-[0_0_0_1px_color-mix(in_oklch,var(--color-destructive)_18%,transparent)]">
          Connection lost. Reconnecting to the rower...
        </div>
      )}

      {showRowingPrompt && (
        <RowingDetectedPrompt
          onStart={async () => {
            setRowingPromptDismissed(true);
            // startWorkout auto-resets from SUMMARY; force-reset handles other stuck states
            try {
              await api.startWorkout();
            } catch {
              await api.forceResetWorkout().catch(() => {});
              await api.startWorkout().catch(() => {});
            }
          }}
          onDismiss={() => setRowingPromptDismissed(true)}
        />
      )}

      {showSettings ? (
        <SettingsScreen onBack={() => setShowSettings(false)} />
      ) : workoutState === "SUMMARY" ? (
        <CompletionScreen onDismiss={handleDismissCompletion} />
      ) : showHistory ? (
        <>
          <div className="px-4 pt-3">
            <Button
              variant="ghost"
              size="sm"
              className="rounded-full border border-border/80 bg-card/55 px-4 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              onClick={() => setShowHistory(false)}
            >
              <Waves className="mr-1 h-4 w-4" />
              Live
            </Button>
          </div>
          <WorkoutHistory key={historyKey} visible />
        </>
      ) : (
        <>
          {workoutState === "IDLE" && (
            <RecoveryBanner onDiscard={() => setHistoryKey((k) => k + 1)} />
          )}

          <LiveMetrics metrics={metrics} workoutState={workoutState} />

          {workoutState === "IDLE" && (
            <div className="px-4 pb-2">
              <Button
                variant="ghost"
                size="sm"
                className="w-full rounded-2xl border border-border/80 bg-card/55 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => setShowHistory(true)}
              >
                <History className="mr-1 h-4 w-4" />
                Workout History
              </Button>
            </div>
          )}

          <WorkoutControls workoutState={workoutState} />
        </>
      )}
    </div>
  );
}

export default App;

