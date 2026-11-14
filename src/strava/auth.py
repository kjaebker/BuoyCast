"""Strava OAuth2 flow — auth URL, token exchange, refresh, revoke.

Tokens are stored in SQLite (strava_tokens table, single row).
Access tokens are auto-refreshed when within 5 minutes of expiry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from src.storage.db import Database

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"

# Refresh when token expires within this many seconds
REFRESH_MARGIN_S = 300


@dataclass
class StravaTokens:
    """Stored Strava OAuth tokens."""

    access_token: str
    refresh_token: str
    expires_at: int
    athlete_id: int | None = None
    athlete_name: str | None = None

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def needs_refresh(self) -> bool:
        return time.time() >= (self.expires_at - REFRESH_MARGIN_S)


class StravaAuth:
    """Manages Strava OAuth2 lifecycle.

    Usage:
        auth = StravaAuth(db, client_id, client_secret, redirect_uri)
        url = auth.build_auth_url()
        tokens = await auth.exchange_code(code)
        tokens = await auth.get_valid_token()  # auto-refreshes
        await auth.revoke()
    """

    def __init__(
        self,
        db: Database,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8080/api/strava/callback",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._db = db
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http_client or httpx.AsyncClient()
        self._owns_http = http_client is None

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def build_auth_url(self) -> str:
        """Build the Strava OAuth authorization URL."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": "activity:write,read",
        }
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> StravaTokens:
        """Exchange authorization code for tokens."""
        resp = await self._http.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        tokens = StravaTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            athlete_id=data.get("athlete", {}).get("id"),
            athlete_name=_extract_athlete_name(data),
        )

        await self._store_tokens(tokens)
        logger.info("Strava tokens stored for athlete %s", tokens.athlete_name)
        return tokens

    async def refresh_token(self, refresh_token: str) -> StravaTokens:
        """Refresh an expired access token."""
        resp = await self._http.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Load existing to preserve athlete info
        existing = await self.get_stored_tokens()

        tokens = StravaTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            athlete_id=existing.athlete_id if existing else None,
            athlete_name=existing.athlete_name if existing else None,
        )

        await self._store_tokens(tokens)
        logger.info("Strava token refreshed, expires at %d", tokens.expires_at)
        return tokens

    async def get_valid_token(self) -> StravaTokens | None:
        """Get a valid access token, auto-refreshing if needed.

        Returns None if no tokens are stored.
        """
        tokens = await self.get_stored_tokens()
        if tokens is None:
            return None

        if tokens.needs_refresh:
            tokens = await self.refresh_token(tokens.refresh_token)

        return tokens

    async def revoke(self) -> None:
        """Revoke tokens and clear from storage."""
        tokens = await self.get_stored_tokens()
        if tokens is not None:
            try:
                await self._http.post(
                    STRAVA_DEAUTH_URL,
                    data={"access_token": tokens.access_token},
                )
            except Exception:
                logger.warning("Failed to revoke token at Strava — clearing locally")

        await self._clear_tokens()
        logger.info("Strava tokens revoked and cleared")

    async def get_stored_tokens(self) -> StravaTokens | None:
        """Load tokens from SQLite."""
        row = await self._db.fetch_one("SELECT * FROM strava_tokens WHERE id = 1")
        if row is None:
            return None
        return StravaTokens(
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=row["expires_at"],
            athlete_id=row["athlete_id"],
            athlete_name=row["athlete_name"],
        )

    async def get_status(self) -> dict:
        """Get Strava connection status for the API."""
        tokens = await self.get_stored_tokens()
        if tokens is None:
            return {"connected": False}
        return {
            "connected": True,
            "athlete_id": tokens.athlete_id,
            "athlete_name": tokens.athlete_name,
            "token_expires_at": tokens.expires_at,
        }

    async def _store_tokens(self, tokens: StravaTokens) -> None:
        """Upsert tokens into SQLite (single-row table)."""
        await self._db.execute(
            """INSERT INTO strava_tokens
                (id, access_token, refresh_token, expires_at, athlete_id, athlete_name)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                athlete_id = excluded.athlete_id,
                athlete_name = excluded.athlete_name""",
            (
                tokens.access_token,
                tokens.refresh_token,
                tokens.expires_at,
                tokens.athlete_id,
                tokens.athlete_name,
            ),
        )

    async def _clear_tokens(self) -> None:
        """Delete all stored tokens."""
        await self._db.execute("DELETE FROM strava_tokens")


def _extract_athlete_name(data: dict) -> str | None:
    """Extract athlete name from Strava OAuth response."""
    athlete = data.get("athlete", {})
    first = athlete.get("firstname", "")
    last = athlete.get("lastname", "")
    name = f"{first} {last}".strip()
    return name or None
