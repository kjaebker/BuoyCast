"""Workout CRUD + control + upload routes."""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.models import StravaUploadStatus, WorkoutState
from src.storage.queries import (
    delete_workout,
    get_app_settings,
    get_incomplete_workout,
    get_strokes,
    get_workout,
    list_workouts,
    update_workout,
)

router = APIRouter()


class UploadRequest(BaseModel):
    """Request body for workout upload with optional HR override."""

    include_hr: bool | None = None


def _get_state(request: Request):
    """Get AppState from the request."""
    return request.app.state.app_state


# --- Workout CRUD ---


@router.get("/workouts")
async def list_workouts_endpoint(request: Request, limit: int = 20, offset: int = 0):
    """List all workouts (newest first, paginated)."""
    state = _get_state(request)
    workouts = await list_workouts(state.db, limit=limit, offset=offset)
    return [w.model_dump(mode="json") for w in workouts]


@router.get("/workouts/{workout_id}")
async def get_workout_endpoint(request: Request, workout_id: str):
    """Get a single workout by ID."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    return workout.model_dump(mode="json")


@router.get("/workouts/{workout_id}/strokes")
async def get_strokes_endpoint(request: Request, workout_id: str):
    """Get all stroke records for a workout."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    strokes = await get_strokes(state.db, workout_id)
    return [s.model_dump(mode="json") for s in strokes]


@router.delete("/workouts/{workout_id}")
async def delete_workout_endpoint(request: Request, workout_id: str):
    """Delete a workout and its strokes."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    await delete_workout(state.db, workout_id)
    return {"status": "deleted"}


# --- Workout control ---


@router.post("/workout/start")
async def start_workout(request: Request):
    """Start a new workout.

    If the state machine is stuck in SUMMARY (e.g. the reset call was lost),
    auto-resets to IDLE first.  Returns 409 only for genuinely invalid states.
    """
    state = _get_state(request)
    sm = state.state_machine
    if sm.state == WorkoutState.SUMMARY:
        await sm.reset()
    new_state = await sm.start()
    return {"state": new_state.value}


@router.post("/workout/pause")
async def pause_workout(request: Request):
    """Pause the current workout. Returns 409 if not ACTIVE."""
    state = _get_state(request)
    sm = state.state_machine
    new_state = await sm.pause()
    return {"state": new_state.value}


@router.post("/workout/resume")
async def resume_workout(request: Request):
    """Resume a paused workout. Returns 409 if not PAUSED."""
    state = _get_state(request)
    sm = state.state_machine
    new_state = await sm.resume()
    return {"state": new_state.value}


@router.post("/workout/end")
async def end_workout(request: Request):
    """End the current workout. Returns 409 if not ACTIVE or PAUSED."""
    state = _get_state(request)
    sm = state.state_machine
    new_state = await sm.end()

    # Reset S4 counters so the monitor shows zeros for the next session
    reader = state.s4_reader
    if reader is not None:
        import asyncio

        asyncio.create_task(reader.send_reset())

    return {"state": new_state.value}


@router.post("/workout/reset")
async def reset_workout(request: Request):
    """Reset from SUMMARY back to IDLE. Call after dismissing the summary screen."""
    state = _get_state(request)
    sm = state.state_machine
    new_state = await sm.reset()
    return {"state": new_state.value}


@router.post("/workout/force-reset")
async def force_reset_workout(request: Request):
    """Force the state machine back to IDLE from any state.

    If ACTIVE or PAUSED, the workout is ended first (data is flushed).
    Use this when the state gets stuck and normal transitions fail.
    """
    state = _get_state(request)
    sm = state.state_machine
    old_state = sm.state.value
    new_state = await sm.force_reset()
    return {"state": new_state.value, "previous_state": old_state}


# --- Upload / skip ---


@router.post("/workouts/{workout_id}/upload")
async def upload_workout_endpoint(
    request: Request, workout_id: str, body: UploadRequest | None = None
):
    """Trigger Strava upload for a workout. Returns 202 Accepted."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})

    auth = state.strava_auth
    if auth is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Strava not configured"},
        )

    # Determine include_hr from request or settings default
    if body is not None and body.include_hr is not None:
        include_hr = body.include_hr
    else:
        app_settings = await get_app_settings(state.db)
        include_hr = app_settings.include_hr_in_strava_upload

    import asyncio
    import logging

    from src.strava.upload import upload_workout

    _logger = logging.getLogger(__name__)

    async def _run_upload():
        ok = await upload_workout(workout_id, state.db, auth, include_hr=include_hr)
        if ok:
            _logger.info("Strava upload task completed for workout %s", workout_id)
        else:
            _logger.warning("Strava upload task failed for workout %s", workout_id)

    asyncio.create_task(_run_upload())

    return JSONResponse(
        status_code=202,
        content={"status": "upload_queued", "workout_id": workout_id},
    )


@router.post("/workouts/{workout_id}/skip")
async def skip_workout(request: Request, workout_id: str):
    """Mark a workout as SKIPPED (won't prompt for upload again)."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    await update_workout(state.db, workout_id, strava_upload_status=StravaUploadStatus.SKIPPED)
    return {"status": "skipped", "workout_id": workout_id}


# --- Boot-time recovery ---


@router.get("/recovery")
async def get_recovery_workout(request: Request):
    """Return any incomplete workout (started but never ended) for recovery prompt."""
    state = _get_state(request)
    workout = await get_incomplete_workout(state.db)
    return {"workout": workout.model_dump(mode="json") if workout else None}


@router.post("/recovery/{workout_id}/discard")
async def discard_recovery_workout(request: Request, workout_id: str):
    """Discard an incomplete workout — sets ended_at and marks SKIPPED."""
    from datetime import datetime

    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    await update_workout(
        state.db,
        workout_id,
        ended_at=datetime.now(UTC),
        strava_upload_status=StravaUploadStatus.SKIPPED,
    )
    return {"status": "discarded", "workout_id": workout_id}
