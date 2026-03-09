/**
 * WebSocket hook for live workout data.
 *
 * Connects to WS /ws/live, parses WSMessage events into typed state,
 * auto-reconnects with exponential backoff, and re-connects on
 * visibilitychange (handles iOS tab resume).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { RowingMetrics, WorkoutState } from "@/types";

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;

type ConnectionStatus = "connecting" | "connected" | "disconnected";

export type WorkoutSocketState = {
  metrics: RowingMetrics | null;
  workoutState: WorkoutState;
  connectionStatus: ConnectionStatus;
};

export function useWorkoutSocket(url?: string): WorkoutSocketState {
  const wsUrl =
    url ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/live`;

  const [metrics, setMetrics] = useState<RowingMetrics | null>(null);
  const [workoutState, setWorkoutState] = useState<WorkoutState>("IDLE");
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    // Clean up existing
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    setConnectionStatus("connecting");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnectionStatus("connected");
      backoffRef.current = INITIAL_BACKOFF_MS;
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(event.data) as {
          type: string;
          data: Record<string, unknown>;
        };

        switch (msg.type) {
          case "metrics_update":
            setMetrics(msg.data as unknown as RowingMetrics);
            break;
          case "workout_started":
            setWorkoutState("ACTIVE");
            break;
          case "workout_paused":
            setWorkoutState("PAUSED");
            break;
          case "workout_resumed":
            setWorkoutState("ACTIVE");
            break;
          case "workout_ended":
            setWorkoutState("SUMMARY");
            setMetrics(null);
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnectionStatus("disconnected");
      // Exponential backoff reconnect
      const delay = backoffRef.current;
      backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror
    };
  }, [wsUrl]);

  // Connect on mount
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  // Reconnect on visibilitychange (iOS tab resume)
  useEffect(() => {
    const handleVisibility = () => {
      if (
        document.visibilityState === "visible" &&
        wsRef.current?.readyState !== WebSocket.OPEN
      ) {
        backoffRef.current = INITIAL_BACKOFF_MS;
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        connect();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibility);
  }, [connect]);

  return { metrics, workoutState, connectionStatus };
}
