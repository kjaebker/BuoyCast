/**
 * Labels and badge styles for the HTTP export status (src/models.py ExportStatus).
 */

import type { ExportStatus } from "@/types";

export const exportStatusLabel: Record<ExportStatus, string> = {
  PENDING: "Queued",
  SENDING: "Sending",
  SENT: "Sent",
  FAILED: "Retrying",
  REJECTED: "Rejected",
  SKIPPED: "Not sent",
};

export const exportStatusClassName: Record<ExportStatus, string> = {
  PENDING:
    "border-[color-mix(in_oklch,var(--color-primary)_36%,transparent)] bg-[color-mix(in_oklch,var(--color-primary)_12%,transparent)] text-primary",
  SENDING:
    "border-transparent bg-[color-mix(in_oklch,var(--color-secondary)_24%,transparent)] text-secondary-foreground",
  SENT: "border-transparent bg-[color-mix(in_oklch,var(--color-secondary)_34%,transparent)] text-secondary-foreground",
  FAILED:
    "border-transparent bg-[color-mix(in_oklch,var(--color-destructive)_20%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_84%,white)]",
  REJECTED:
    "border-transparent bg-[color-mix(in_oklch,var(--color-destructive)_20%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_84%,white)]",
  SKIPPED: "border-transparent bg-muted text-muted-foreground",
};

/** Statuses that are still changing on the backend. */
export const exportInFlight = (s: ExportStatus) => s === "PENDING" || s === "SENDING";
