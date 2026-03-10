/** Format elapsed seconds as M:SS or H:MM:SS */
export function formatTime(seconds: number | null): string {
  if (seconds == null || !isFinite(seconds)) return "--:--";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Format pace in seconds-per-500m as M:SS */
export function formatPace(secsP500: number | null): string {
  if (secsP500 == null || !isFinite(secsP500) || secsP500 <= 0) return "--:--";
  const s = Math.floor(secsP500);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Format a distance in metres, rounded to the nearest integer */
export function formatDistance(meters: number | null): string {
  if (meters == null || !isFinite(meters)) return "--";
  return String(Math.round(meters));
}

/** Format a generic number, defaulting to 0 decimal places */
export function formatNum(value: number | null, decimals = 0): string {
  if (value == null || !isFinite(value)) return "--";
  return value.toFixed(decimals);
}
