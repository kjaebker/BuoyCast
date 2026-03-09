/**
 * TypeScript types mirroring backend Pydantic models.
 * Keep in sync with src/models.py.
 */

export const WorkoutState = {
  IDLE: "IDLE",
  ACTIVE: "ACTIVE",
  PAUSED: "PAUSED",
  SUMMARY: "SUMMARY",
} as const;

export type WorkoutState = (typeof WorkoutState)[keyof typeof WorkoutState];
