/**
 * API client for BuoyCast backend.
 */

import type {
  SystemStatus,
  StravaStatus,
  WorkoutRecord,
  StrokeRecord,
  AppSettings,
  ExportInfo,
} from "@/types";

const BASE = "/api";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

// --- System ---

export const getStatus = () => fetchJSON<SystemStatus>("/status");

// --- Workouts ---

export const listWorkouts = (limit = 20, offset = 0) =>
  fetchJSON<WorkoutRecord[]>(`/workouts?limit=${limit}&offset=${offset}`);

export const getWorkout = (id: string) =>
  fetchJSON<WorkoutRecord>(`/workouts/${id}`);

export const getStrokes = (id: string) =>
  fetchJSON<StrokeRecord[]>(`/workouts/${id}/strokes`);

export const deleteWorkout = (id: string) =>
  fetchJSON<{ status: string }>(`/workouts/${id}`, { method: "DELETE" });

// --- Workout control ---

export const startWorkout = () =>
  fetchJSON<{ state: string }>("/workout/start", { method: "POST" });

export const pauseWorkout = () =>
  fetchJSON<{ state: string }>("/workout/pause", { method: "POST" });

export const resumeWorkout = () =>
  fetchJSON<{ state: string }>("/workout/resume", { method: "POST" });

export const endWorkout = () =>
  fetchJSON<{ state: string }>("/workout/end", { method: "POST" });

export const resetWorkout = () =>
  fetchJSON<{ state: string }>("/workout/reset", { method: "POST" });

export const forceResetWorkout = () =>
  fetchJSON<{ state: string; previous_state: string }>("/workout/force-reset", {
    method: "POST",
  });

// --- Upload ---

export const uploadWorkout = (id: string, includeHr?: boolean) =>
  fetchJSON<{ status: string; workout_id: string }>(`/workouts/${id}/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: includeHr !== undefined ? JSON.stringify({ include_hr: includeHr }) : undefined,
  });

export const skipWorkout = (id: string) =>
  fetchJSON<{ status: string; workout_id: string }>(`/workouts/${id}/skip`, {
    method: "POST",
  });

// --- Boot-time recovery ---

export const getRecoveryWorkout = () =>
  fetchJSON<{ workout: WorkoutRecord | null }>("/recovery");

export const discardRecoveryWorkout = (id: string) =>
  fetchJSON<{ status: string; workout_id: string }>(
    `/recovery/${id}/discard`,
    { method: "POST" },
  );

// --- Strava ---

export const getStravaAuth = () =>
  fetchJSON<{ auth_url: string }>("/strava/auth");

export const getStravaStatus = () => fetchJSON<StravaStatus>("/strava/status");

export const disconnectStrava = () =>
  fetchJSON<{ connected: boolean }>("/strava/auth", { method: "DELETE" });

// --- HTTP export ---

export const getExportStatus = () => fetchJSON<ExportInfo>("/export/status");

export const exportWorkout = (id: string) =>
  fetchJSON<{ status: string; workout_id: string }>(`/workouts/${id}/export`, {
    method: "POST",
  });

// --- Settings ---

export const getSettings = () => fetchJSON<AppSettings>("/settings");
