"""HTTP export: POST each finished workout to a user-configured endpoint.

Strava needs an API subscription; this is the do-it-yourself alternative.
The receiver can be anything that accepts an HTTP POST: a self-hosted
training log, an automation tool, a small script. The request format is a
public contract documented in docs/export.md.

Delivery is at-least-once. Every finished workout starts PENDING in SQLite;
the exporter sends it when the recorder publishes WORKOUT_SAVED, and
re-sends FAILED ones every ``retry_interval_s``, so a workout recorded while
the Wi-Fi or the server is down still arrives later. Receivers must
de-duplicate on the workout ID (sent as the Idempotency-Key header).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.config import ExportSettings
from src.events import EventBus, EventType
from src.export.payload import build_payload
from src.models import ExportStatus, WorkoutRecord
from src.storage.db import Database
from src.storage.queries import (
    get_strokes,
    get_workout,
    list_workouts_to_export,
    reset_stuck_exports,
    update_workout,
)
from src.updates import current_version
from src.workout.fit import generate_fit

logger = logging.getLogger(__name__)

FIT_CONTENT_TYPE = "application/vnd.ant.fit"
_RETRYABLE_STATUS = {408, 425, 429}
_SWEEP_BATCH = 10


class ExportNotConfiguredError(RuntimeError):
    """Raised by a manual send when no export URL is set."""


class WorkoutExporter:
    """Sends finished workouts to ``settings.url``.

    Subscribes to WORKOUT_SAVED and publishes EXPORT_STATUS. Does nothing
    when no URL is configured: workouts stay PENDING and go out once one is.
    """

    def __init__(
        self,
        event_bus: EventBus,
        db: Database,
        settings: ExportSettings,
        fit_dir: str | Path = "data/fit",
        min_distance_m: float = 0.0,
        http_client: httpx.AsyncClient | None = None,
        version: str | None = None,
    ) -> None:
        self._bus = event_bus
        self._db = db
        self._settings = settings
        self._fit_dir = Path(fit_dir) / "export"
        self._min_distance_m = min_distance_m
        self._client = http_client
        self._owns_client = http_client is None
        self._version = version or current_version()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._saved_queue: asyncio.Queue | None = None

    @property
    def settings(self) -> ExportSettings:
        return self._settings

    @property
    def configured(self) -> bool:
        return self._settings.enabled

    async def start(self) -> None:
        if not self.configured:
            logger.info("HTTP export off (no [export] url set)")
            return
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.timeout_s)
        await reset_stuck_exports(self._db)
        self._saved_queue = self._bus.subscribe(EventType.WORKOUT_SAVED)
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "HTTP export on: %s (format=%s, auto_send=%s)",
            self.target_host,
            self._settings.format,
            self._settings.auto_send,
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._saved_queue is not None:
            self._bus.unsubscribe(EventType.WORKOUT_SAVED, self._saved_queue)
            self._saved_queue = None
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def target_host(self) -> str:
        """The endpoint's host, safe to show in the dashboard (no path or query)."""
        return httpx.URL(self._settings.url).host if self.configured else ""

    async def _run_loop(self) -> None:
        assert self._saved_queue is not None
        while True:
            await self.sweep()
            try:
                await asyncio.wait_for(
                    self._saved_queue.get(), timeout=self._settings.retry_interval_s
                )
            except TimeoutError:
                pass

    async def sweep(self) -> None:
        """Send every PENDING workout and retry every FAILED one."""
        if not self.configured or not self._settings.auto_send:
            return
        while True:
            batch = await list_workouts_to_export(
                self._db, (ExportStatus.PENDING, ExportStatus.FAILED), limit=_SWEEP_BATCH
            )
            if not batch:
                return
            made_progress = False
            for workout in batch:
                status = await self._send_one(workout, manual=False)
                made_progress |= status in (ExportStatus.SENT, ExportStatus.SKIPPED)
            # Stop when the endpoint is failing; the next sweep retries.
            if not made_progress or len(batch) < _SWEEP_BATCH:
                return

    async def send(self, workout_id: str) -> ExportStatus:
        """Send one workout now, whatever its status (the dashboard's Send button)."""
        if not self.configured:
            raise ExportNotConfiguredError("No export URL configured")
        workout = await get_workout(self._db, workout_id)
        if workout is None or workout.ended_at is None:
            raise LookupError(f"No finished workout {workout_id}")
        return await self._send_one(workout, manual=True)

    async def _send_one(self, workout: WorkoutRecord, manual: bool) -> ExportStatus:
        async with self._lock:
            # Re-read under the lock: a concurrent send may have just finished it.
            current = await get_workout(self._db, workout.id)
            if current is None:
                return ExportStatus.SKIPPED
            if not manual and current.export_status not in (
                ExportStatus.PENDING,
                ExportStatus.FAILED,
            ):
                return current.export_status

            if not manual and current.total_distance_m < self._min_distance_m:
                error = f"Shorter than {self._min_distance_m:.0f} m"
                await self._set_status(current.id, ExportStatus.SKIPPED, error=error)
                return ExportStatus.SKIPPED

            await self._set_status(current.id, ExportStatus.SENDING)
            status, error = await self._post(current)
            fields: dict[str, object] = {"export_attempts": current.export_attempts + 1}
            if status == ExportStatus.SENT:
                fields["exported_at"] = datetime.now(UTC)
            await self._set_status(current.id, status, error=error, **fields)
            return status

    async def _post(self, workout: WorkoutRecord) -> tuple[ExportStatus, str | None]:
        assert self._client is not None
        try:
            body, content_type = await self._build_body(workout)
        except Exception as exc:
            logger.exception("Export: could not build body for %s", workout.id)
            return ExportStatus.REJECTED, f"Could not build export: {exc}"

        headers = {
            "Content-Type": content_type,
            "Idempotency-Key": workout.id,
            "User-Agent": f"BuoyCast/{self._version}",
            "X-BuoyCast-Workout-Id": workout.id,
            "X-BuoyCast-Started-At": workout.started_at.isoformat(),
        }
        if self._settings.token:
            headers["Authorization"] = f"Bearer {self._settings.token}"

        try:
            resp = await self._client.post(
                self._settings.url,
                content=body,
                headers=headers,
                timeout=self._settings.timeout_s,
            )
        except httpx.HTTPError as exc:
            logger.warning("Export of %s failed: %s", workout.id, exc)
            return ExportStatus.FAILED, f"{type(exc).__name__}: {exc}"[:300]

        if resp.is_success:
            logger.info(
                "Exported workout %s to %s (HTTP %d)",
                workout.id,
                self.target_host,
                resp.status_code,
            )
            return ExportStatus.SENT, None

        error = f"HTTP {resp.status_code}: {resp.text[:200]}".strip()
        retryable = resp.status_code >= 500 or resp.status_code in _RETRYABLE_STATUS
        logger.warning(
            "Export of %s %s: %s", workout.id, "failed" if retryable else "rejected", error
        )
        return (ExportStatus.FAILED if retryable else ExportStatus.REJECTED), error

    async def _build_body(self, workout: WorkoutRecord) -> tuple[bytes, str]:
        strokes = await get_strokes(self._db, workout.id)
        include_hr = self._settings.include_hr
        if self._settings.format == "fit":
            path = await asyncio.to_thread(
                generate_fit, workout, strokes, output_dir=self._fit_dir, include_hr=include_hr
            )
            return await asyncio.to_thread(path.read_bytes), FIT_CONTENT_TYPE
        payload = build_payload(workout, strokes, self._version, include_hr=include_hr)
        return payload.model_dump_json().encode(), "application/json"

    async def _set_status(
        self, workout_id: str, status: ExportStatus, error: str | None = None, **fields: object
    ) -> None:
        await update_workout(
            self._db, workout_id, export_status=status, export_error=error, **fields
        )
        await self._bus.emit(
            EventType.EXPORT_STATUS,
            {"workout_id": workout_id, "export_status": status.value, "export_error": error},
        )
