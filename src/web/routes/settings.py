"""Settings API endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.storage.queries import get_app_settings, update_app_settings

router = APIRouter()


class SettingsUpdateRequest(BaseModel):
    """Request body for partial settings updates."""

    include_hr_in_strava_upload: bool | None = None


@router.get("/settings")
async def get_settings(request: Request):
    """Get current app settings."""
    state = request.app.state.app_state
    settings = await get_app_settings(state.db)
    return settings.model_dump(mode="json")


@router.put("/settings")
async def update_settings(request: Request, body: SettingsUpdateRequest):
    """Update app settings (partial update)."""
    state = request.app.state.app_state
    update_fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if update_fields:
        await update_app_settings(state.db, **update_fields)
    settings = await get_app_settings(state.db)
    return settings.model_dump(mode="json")
