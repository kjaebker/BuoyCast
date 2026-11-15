"""HTTP export status and manual send (see docs/export.md)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.export.http import ExportNotConfiguredError
from src.storage.queries import count_workouts_by_export_status, get_workout

logger = logging.getLogger(__name__)

router = APIRouter()


class ExportInfo(BaseModel):
    """What the dashboard may know about the export target. Never the token."""

    configured: bool
    target_host: str
    format: str
    auto_send: bool
    include_hr: bool
    counts: dict[str, int]


@router.get("/export/status", response_model=ExportInfo)
async def export_status(request: Request) -> ExportInfo:
    state = request.app.state.app_state
    exporter = state.exporter
    counts = await count_workouts_by_export_status(state.db)
    if exporter is None or not exporter.configured:
        return ExportInfo(
            configured=False,
            target_host="",
            format="json",
            auto_send=False,
            include_hr=False,
            counts=counts,
        )
    s = exporter.settings
    return ExportInfo(
        configured=True,
        target_host=exporter.target_host,
        format=s.format,
        auto_send=s.auto_send,
        include_hr=s.include_hr,
        counts=counts,
    )


@router.post("/workouts/{workout_id}/export")
async def export_workout(request: Request, workout_id: str):
    """Send one workout now. Returns 202; progress arrives as export_status over WS."""
    state = request.app.state.app_state
    exporter = state.exporter
    if exporter is None or not exporter.configured:
        return JSONResponse(status_code=503, content={"detail": "Export not configured"})
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    if workout.ended_at is None:
        return JSONResponse(status_code=409, content={"detail": "Workout has not ended"})

    async def _run() -> None:
        try:
            await exporter.send(workout_id)
        except (ExportNotConfiguredError, LookupError) as exc:
            logger.warning("Manual export of %s: %s", workout_id, exc)
        except Exception:
            logger.exception("Manual export of %s crashed", workout_id)

    asyncio.create_task(_run())
    return JSONResponse(
        status_code=202, content={"status": "export_queued", "workout_id": workout_id}
    )
