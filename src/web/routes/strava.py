"""Strava OAuth + upload routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def _get_state(request: Request):
    """Get AppState from the request."""
    return request.app.state.app_state


@router.get("/strava/auth")
async def strava_auth(request: Request):
    """Return the Strava OAuth authorization URL."""
    state = _get_state(request)
    auth = state.strava_auth
    if auth is None:
        return JSONResponse(status_code=503, content={"detail": "Strava not configured"})
    url = auth.build_auth_url()
    return {"auth_url": url}


@router.get("/strava/callback")
async def strava_callback(request: Request, code: str):
    """Handle OAuth callback — exchange code for tokens."""
    state = _get_state(request)
    auth = state.strava_auth
    if auth is None:
        return JSONResponse(status_code=503, content={"detail": "Strava not configured"})
    tokens = await auth.exchange_code(code)
    return {
        "connected": True,
        "athlete_id": tokens.athlete_id,
        "athlete_name": tokens.athlete_name,
    }


@router.get("/strava/status")
async def strava_status(request: Request):
    """Return Strava connection status."""
    state = _get_state(request)
    auth = state.strava_auth
    if auth is None:
        return {"connected": False, "reason": "not_configured"}
    return await auth.get_status()


@router.delete("/strava/auth")
async def strava_disconnect(request: Request):
    """Revoke Strava tokens and disconnect."""
    state = _get_state(request)
    auth = state.strava_auth
    if auth is None:
        return JSONResponse(status_code=503, content={"detail": "Strava not configured"})
    await auth.revoke()
    return {"connected": False}
