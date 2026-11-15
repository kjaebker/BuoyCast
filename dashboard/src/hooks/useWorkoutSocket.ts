/**
 * WebSocket hook for live workout data.
 *
 * Connects to WS /ws/live, parses WSMessage events into typed state,
 * auto-reconnects with exponential backoff, and re-connects on
 * visibilitychange (handles iOS tab resume).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { RowingMetrics, StrokePhase, WorkoutState } from "@/types";

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;
/** Sparkline window: one point per metrics message (~1 Hz), so ~60 s. */
const HISTORY_LENGTH = 60;

type ConnectionStatus = "connecting" | "connected" | "disconnected";

export type MetricsHistory = {
  /** Recent non-zero stroke rates (zeros would flatten the chart's Y axis). */
  strokeRate: number[];
  heartRate: number[];
  /** Most recent non-zero stroke rate and when it arrived (ms epoch). */
  lastStroke: { rate: number; at: number } | null;
  /** When heart rate was last present in a message (ms epoch). */
  lastHrAt: number | null;
};

/** A stroke boundary from the S4, stamped with the client's performance.now(). */
export type StrokeSignal = { phase: StrokePhase; at: number };
export type StrokeListener = (signal: StrokeSignal) => void;
/** Subscribe to live stroke events; returns an unsubscribe function. */
export type SubscribeStrokes = (listener: StrokeListener) => () => void;

export type WorkoutSocketState = {
  metrics: RowingMetrics | null;
  history: MetricsHistory;
  workoutState: WorkoutState;
  connectionStatus: ConnectionStatus;
  dismissSummary: () => void;
  /** Stroke events go to listeners directly (no re-render per stroke). */
  subscribeStrokes: SubscribeStrokes;
};

const EMPTY_HISTORY: MetricsHistory = {
  strokeRate: [],
  heartRate: [],
  lastStroke: null,
  lastHrAt: null,
};

function appendCapped(values: number[], value: number): number[] {
  const next = values.length >= HISTORY_LENGTH ? values.slice(1) : values.slice();
  next.push(value);
  return next;
}

export function useWorkoutSocket(url?: string): WorkoutSocketState {
  const wsUrl =
    url ??
    `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/live`;

  const [metrics, setMetrics] = useState<RowingMetrics | null>(null);
  const [history, setHistory] = useState<MetricsHistory>(EMPTY_HISTORY);
  const [workoutState, setWorkoutState] = useState<WorkoutState>("IDLE");
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const strokeListeners = useRef(new Set<StrokeListener>());

  const subscribeStrokes = useCallback<SubscribeStrokes>((listener) => {
    const listeners = strokeListeners.current;
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  useEffect(() => {
    const listeners = strokeListeners.current;
    let mounted = true;
    let ws: WebSocket | null = null;
    let backoff = INITIAL_BACKOFF_MS;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const handleMessage = (event: MessageEvent) => {
      let msg: { type: string; data: Record<string, unknown> };
      try {
        msg = JSON.parse(event.data);
      } catch {
        return; // ignore malformed messages
      }
      switch (msg.type) {
        case "metrics_update": {
          const m = msg.data as unknown as RowingMetrics;
          const at = Date.now();
          const stroking = m.stroke_rate != null && m.stroke_rate > 0;
          const hasHr = m.heart_rate_bpm != null;
          setMetrics(m);
          setHistory((h) => ({
            strokeRate: stroking ? appendCapped(h.strokeRate, m.stroke_rate!) : h.strokeRate,
            heartRate: hasHr ? appendCapped(h.heartRate, m.heart_rate_bpm!) : h.heartRate,
            lastStroke: stroking ? { rate: m.stroke_rate!, at } : h.lastStroke,
            lastHrAt: hasHr ? at : h.lastHrAt,
          }));
          break;
        }
        case "stroke": {
          const signal: StrokeSignal = {
            phase: (msg.data as { phase: StrokePhase }).phase,
            at: performance.now(),
          };
          listeners.forEach((listener) => listener(signal));
          break;
        }
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
    };

    const connect = () => {
      if (!mounted) return;
      if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;
      if (ws) {
        ws.onclose = null;
        ws.close();
      }

      setConnectionStatus("connecting");
      const socket = new WebSocket(wsUrl);
      ws = socket;

      socket.onopen = () => {
        if (!mounted) return;
        setConnectionStatus("connected");
        backoff = INITIAL_BACKOFF_MS;
        // Sync workout state on every (re)connect so a reload or dropped
        // socket doesn't leave the client stuck in a stale state.
        fetch("/api/status")
          .then((r) => r.json())
          .then((s) => {
            if (mounted && s.workout_state) setWorkoutState(s.workout_state as WorkoutState);
          })
          .catch(() => {});
      };
      socket.onmessage = (event) => {
        if (mounted) handleMessage(event);
      };
      socket.onclose = () => {
        if (!mounted) return;
        setConnectionStatus("disconnected");
        const delay = backoff;
        backoff = Math.min(delay * 2, MAX_BACKOFF_MS);
        reconnectTimer = setTimeout(connect, delay);
      };
      // onclose fires after onerror, so errors are handled there.
    };

    // Reconnect promptly when the tab comes back (iOS suspends sockets).
    const handleVisibility = () => {
      if (document.visibilityState === "visible" && ws?.readyState !== WebSocket.OPEN) {
        backoff = INITIAL_BACKOFF_MS;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        connect();
      }
    };

    connect();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      mounted = false;
      document.removeEventListener("visibilitychange", handleVisibility);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [wsUrl]);

  const dismissSummary = useCallback(() => {
    setWorkoutState("IDLE");
    setMetrics(null);
  }, []);

  return { metrics, history, workoutState, connectionStatus, dismissSummary, subscribeStrokes };
}
