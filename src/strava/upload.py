"""Strava FIT file upload with status polling.

Uploads a workout's FIT file to Strava, polls for processing completion,
and updates the WorkoutRecord with the result.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from src.models import StravaUploadStatus
from src.storage.db import Database
from src.storage.queries import get_strokes, get_workout, update_workout
from src.strava.auth import StravaAuth
from src.workout.fit import generate_fit

logger = logging.getLogger(__name__)

STRAVA_UPLOAD_URL = "https://www.strava.com/api/v3/uploads"
STRAVA_UPLOAD_STATUS_URL = "https://www.strava.com/api/v3/uploads/{upload_id}"

# Polling config
POLL_INTERVAL_S = 2.0
MAX_POLLS = 30


async def upload_workout(
    workout_id: str,
    db: Database,
    auth: StravaAuth,
    fit_dir: str = "data/fit",
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Upload a workout's FIT file to Strava.

    Returns True on success, False on failure.

    Steps:
    1. Set status to UPLOADING
    2. Generate FIT file if needed
    3. POST to Strava uploads API
    4. Poll until activity_id available or error
    5. Update workout record with result
    """
    client = http_client or httpx.AsyncClient()
    owns_client = http_client is None

    try:
        # Get workout
        workout = await get_workout(db, workout_id)
        if workout is None:
            logger.error("Workout %s not found", workout_id)
            return False

        # Set uploading status
        await update_workout(
            db, workout_id, strava_upload_status=StravaUploadStatus.UPLOADING
        )

        # Get valid token
        tokens = await auth.get_valid_token()
        if tokens is None:
            await _set_failed(db, workout_id, "Not authenticated with Strava")
            return False

        # Generate FIT file if not already generated
        fit_path = workout.fit_file_path
        if fit_path is None or not Path(fit_path).exists():
            strokes = await get_strokes(db, workout_id)
            fit_path = str(generate_fit(workout, strokes, output_dir=fit_dir))
            await update_workout(db, workout_id, fit_file_path=fit_path)

        # Upload
        upload_id = await _upload_fit(
            client, tokens.access_token, Path(fit_path), workout.id
        )
        if upload_id is None:
            await _set_failed(db, workout_id, "Upload request failed")
            return False

        # Poll for completion
        activity_id = await _poll_upload_status(
            client, tokens.access_token, upload_id
        )

        if activity_id is not None:
            await update_workout(
                db,
                workout_id,
                strava_upload_status=StravaUploadStatus.UPLOADED,
                strava_activity_id=activity_id,
                strava_error=None,
            )
            logger.info(
                "Workout %s uploaded to Strava (activity %d)",
                workout_id,
                activity_id,
            )
            return True
        else:
            await _set_failed(db, workout_id, "Upload processing timed out")
            return False

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        await _set_failed(db, workout_id, error_msg)
        return False
    except Exception as e:
        await _set_failed(db, workout_id, str(e))
        return False
    finally:
        if owns_client:
            await client.aclose()


async def _upload_fit(
    client: httpx.AsyncClient,
    access_token: str,
    fit_path: Path,
    workout_id: str,
) -> int | None:
    """POST FIT file to Strava. Returns upload_id or None on failure."""
    with open(fit_path, "rb") as f:
        resp = await client.post(
            STRAVA_UPLOAD_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            files={"file": (fit_path.name, f, "application/octet-stream")},
            data={
                "sport_type": "Rowing",
                "data_type": "fit",
                "name": f"BuoyCast Workout {workout_id}",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return data.get("id")


async def _poll_upload_status(
    client: httpx.AsyncClient,
    access_token: str,
    upload_id: int,
    poll_interval: float = POLL_INTERVAL_S,
    max_polls: int = MAX_POLLS,
) -> int | None:
    """Poll Strava upload status until activity_id is available.

    Returns activity_id on success, None on timeout or error.
    """
    for _ in range(max_polls):
        resp = await client.get(
            STRAVA_UPLOAD_STATUS_URL.format(upload_id=upload_id),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        activity_id = data.get("activity_id")
        error = data.get("error")

        if activity_id is not None:
            return activity_id

        if error:
            raise Exception(f"Strava upload error: {error}")

        # Still processing
        await asyncio.sleep(poll_interval)

    return None


async def _set_failed(db: Database, workout_id: str, error: str) -> None:
    """Mark a workout upload as failed."""
    logger.error("Strava upload failed for %s: %s", workout_id, error)
    await update_workout(
        db,
        workout_id,
        strava_upload_status=StravaUploadStatus.FAILED,
        strava_error=error,
    )
