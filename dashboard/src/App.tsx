import { useState } from "react";
import { History, Waves } from "lucide-react";
import { useWorkoutSocket } from "@/hooks/useWorkoutSocket";
import { useWakeLock } from "@/hooks/useWakeLock";
import { StatusBar } from "@/components/StatusBar";
import { LiveMetrics } from "@/components/LiveMetrics";
import { WorkoutControls } from "@/components/WorkoutControls";
import { CompletionScreen } from "@/components/CompletionScreen";
import { WorkoutHistory } from "@/components/WorkoutHistory";
import { RecoveryBanner } from "@/components/RecoveryBanner";
import { Button } from "@/components/ui/button";

function App() {
  const { metrics, workoutState, connectionStatus } = useWorkoutSocket();
  const [showHistory, setShowHistory] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);

  useWakeLock(workoutState);

  const handleDismissCompletion = () => {
    // After dismissing completion screen, show history
    setShowHistory(true);
  };

  return (
    <div className="flex flex-col min-h-dvh bg-background text-foreground dark">
      <StatusBar connectionStatus={connectionStatus} metrics={metrics} />

      {/* Connection lost banner */}
      {connectionStatus === "disconnected" && (
        <div className="bg-destructive/20 text-destructive px-4 py-2 text-center text-sm font-medium">
          Connection lost — reconnecting...
        </div>
      )}

      {/* Main content area */}
      {workoutState === "SUMMARY" ? (
        <CompletionScreen onDismiss={handleDismissCompletion} />
      ) : showHistory ? (
        <>
          <div className="flex items-center px-4 pt-3 gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowHistory(false)}
            >
              <Waves className="h-4 w-4 mr-1" />
              Live
            </Button>
          </div>
          <WorkoutHistory key={historyKey} visible />
        </>
      ) : (
        <>
          {/* Boot-time recovery prompt — only when IDLE */}
          {workoutState === "IDLE" && (
            <RecoveryBanner
              onDiscard={() => setHistoryKey((k) => k + 1)}
            />
          )}

          <LiveMetrics metrics={metrics} workoutState={workoutState} />

          {/* History toggle — only when IDLE */}
          {workoutState === "IDLE" && (
            <div className="px-4 pb-2">
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setShowHistory(true)}
              >
                <History className="h-4 w-4 mr-1" />
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
