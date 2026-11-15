/**
 * TypeScript types mirroring backend Pydantic models.
 * Keep in sync with src/models.py.
 */

// --- Enums (as const objects for erasableSyntaxOnly) ---

export const WorkoutState = {
  IDLE: "IDLE",
  ACTIVE: "ACTIVE",
  PAUSED: "PAUSED",
  SUMMARY: "SUMMARY",
} as const;

export type WorkoutState = (typeof WorkoutState)[keyof typeof WorkoutState];

export const StravaUploadStatus = {
  PENDING: "PENDING",
  UPLOADING: "UPLOADING",
  UPLOADED: "UPLOADED",
  FAILED: "FAILED",
  SKIPPED: "SKIPPED",
} as const;

export type StravaUploadStatus =
  (typeof StravaUploadStatus)[keyof typeof StravaUploadStatus];

export const ExportStatus = {
  PENDING: "PENDING",
  SENDING: "SENDING",
  SENT: "SENT",
  FAILED: "FAILED",
  REJECTED: "REJECTED",
  SKIPPED: "SKIPPED",
} as const;

export type ExportStatus = (typeof ExportStatus)[keyof typeof ExportStatus];

// --- Real-time data ---

export type RowingMetrics = {
  timestamp: string;
  // S4 data
  stroke_rate: number | null;
  stroke_count: number | null;
  distance_m: number | null;
  pace_s_per_500m: number | null;
  power_watts: number | null;
  calories: number | null;
  elapsed_seconds: number | null;
  drive_length_cm: number | null;
  // TICKR data
  heart_rate_bpm: number | null;
  rr_intervals_ms: number[] | null;
};

// --- Workout record ---

/** Mirrors src/models.py StrokePhase / StrokeEvent. */
export const StrokePhase = {
  DRIVE: "drive",
  RECOVERY: "recovery",
} as const;
export type StrokePhase = (typeof StrokePhase)[keyof typeof StrokePhase];

export type StrokeEvent = {
  phase: StrokePhase;
  timestamp: string;
};

export type WorkoutRecord = {
  id: string;
  started_at: string;
  ended_at: string | null;
  total_distance_m: number;
  total_strokes: number;
  elapsed_seconds: number;
  avg_pace_s_per_500m: number | null;
  avg_stroke_rate: number | null;
  avg_power_watts: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  calories: number;
  strava_upload_status: StravaUploadStatus;
  strava_activity_id: number | null;
  strava_error: string | null;
  fit_file_path: string | null;
  export_status: ExportStatus;
  export_error: string | null;
  export_attempts: number;
  exported_at: string | null;
};

// --- Stroke record ---

export type StrokeRecord = {
  workout_id: string;
  ts: string;
  distance_m: number;
  stroke_rate: number;
  power_watts: number | null;
  pace_s_per_500m: number | null;
  heart_rate_bpm: number | null;
  rr_intervals_ms: number[] | null;
};

// --- WebSocket ---

export type WSMessage = {
  type: string;
  data: Record<string, unknown>;
};

export type MetricsMessage = WSMessage & {
  type: "metrics_update";
  data: RowingMetrics;
};

// --- API status ---

export type SystemStatus = {
  s4_connected: boolean;
  s4_paused: boolean;
  tickr_connected: boolean;
  tickr_paused: boolean;
  workout_state: WorkoutState;
  uptime_seconds: number;
  last_metrics_ts: string | null;
};

export type StravaStatus = {
  connected: boolean;
  athlete_id?: number;
  athlete_name?: string;
  token_expires_at?: number;
  reason?: string;
};

/** Mirrors src/web/routes/export.py ExportInfo. The token is never sent. */
export type ExportInfo = {
  configured: boolean;
  target_host: string;
  format: string;
  auto_send: boolean;
  include_hr: boolean;
  counts: Partial<Record<ExportStatus, number>>;
};

export type AppSettings = {
  include_hr_in_strava_upload: boolean;
  updated_at: string;
};

export type UpdateInfo = {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_notes: string | null;
  release_url: string | null;
  can_self_update: boolean;
  error: string | null;
};
