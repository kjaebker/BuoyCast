/**
 * Whether optional integrations are set up, so the UI can hide the ones
 * that aren't. Strava and the HTTP export are both configured in config.toml.
 */

import type { ExportInfo, StravaStatus } from "@/types";

/** Strava credentials are in config.toml (the account may not be connected yet). */
export const stravaConfigured = (s: StravaStatus | null | undefined): boolean =>
  s != null && s.reason !== "not_configured";

/** Strava is configured and an account is connected, so uploads will work. */
export const stravaReady = (s: StravaStatus | null | undefined): boolean => Boolean(s?.connected);

export const exportConfigured = (e: ExportInfo | null | undefined): boolean =>
  Boolean(e?.configured);
