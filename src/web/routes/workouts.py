"""Workout CRUD + control + upload routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.models import StravaUploadStatus, WorkoutState
from src.storage.queries import (
    delete_workout,
    get_incomplete_workout,
    get_strokes,
    get_workout,
    list_workouts,
    update_workout,
)
from src.workout.state import InvalidTransitionError

router = APIRouter()


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
    """Start a new workout. Returns 409 if not in IDLE state."""
    state = _get_state(request)
    sm = state.state_machine
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
    return {"state": new_state.value}


@router.post("/workout/reset")
async def reset_workout(request: Request):
    """Reset from SUMMARY back to IDLE. Call after dismissing the summary screen."""
    state = _get_state(request)
    sm = state.state_machine
    new_state = await sm.reset()
    return {"state": new_state.value}


# --- Upload / skip ---


@router.post("/workouts/{workout_id}/upload")
async def upload_workout_endpoint(request: Request, workout_id: str):
    """Trigger Strava upload for a workout. Returns 202 Accepted."""
    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})

    auth = state.strava_auth
    if auth is not None:
        from src.strava.upload import upload_workout

        import asyncio

        asyncio.create_task(upload_workout(workout_id, state.db, auth))

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
    await update_workout(
        state.db, workout_id, strava_upload_status=StravaUploadStatus.SKIPPED
    )
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
    from datetime import datetime, timezone

    state = _get_state(request)
    workout = await get_workout(state.db, workout_id)
    if workout is None:
        return JSONResponse(status_code=404, content={"detail": "Workout not found"})
    await update_workout(
        state.db,
        workout_id,
        ended_at=datetime.now(timezone.utc),
        strava_upload_status=StravaUploadStatus.SKIPPED,
    )
    return {"status": "discarded", "workout_id": workout_id}
