"""Release-based software updates.

BuoyCast installs from tagged GitHub Releases. The update check compares the
running version against the repository's latest release; applying an update
runs the root-owned ``buoycast-update`` helper installed by ``install.sh``.
"""

from __future__ import annotations

import logging
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Installed by install.sh; the only command the service user may sudo for updates.
UPDATE_HELPER = Path("/usr/local/sbin/buoycast-update")

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(.+))?$")


def current_version() -> str:
    """Return the installed BuoyCast version (from package metadata)."""
    try:
        return _pkg_version("buoycast")
    except PackageNotFoundError:  # running from a bare checkout without install
        return "0.0.0+unknown"


def parse_version(tag: str) -> tuple[int, int, int, bool]:
    """Parse ``v1.2.3`` / ``1.2.3-rc1`` into a sortable tuple.

    The last element is True for final releases so that ``1.2.3`` sorts
    after ``1.2.3-rc1``. Raises ValueError for anything unparseable.
    """
    m = _VERSION_RE.match(tag.strip())
    if not m:
        raise ValueError(f"Unrecognised version: {tag!r}")
    major, minor, patch, pre = m.groups()
    # Local build metadata (e.g. "+unknown") is not a pre-release.
    is_final = pre is None or pre.startswith("+")
    return int(major), int(minor), int(patch), is_final


class UpdateInfo(BaseModel):
    """Response model for GET /api/system/update/check."""

    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_notes: str | None = None
    release_url: str | None = None
    can_self_update: bool = False
    error: str | None = None


async def check_for_update(
    repo: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_s: float = 10.0,
) -> UpdateInfo:
    """Compare the running version with the latest GitHub Release of ``repo``."""
    current = current_version()
    info = UpdateInfo(current_version=current, can_self_update=UPDATE_HELPER.exists())

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout_s) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
    except httpx.HTTPError as e:
        info.error = f"Could not reach GitHub: {e}"
        return info

    if resp.status_code == 404:
        info.error = "No releases published yet"
        return info
    if resp.status_code != 200:
        info.error = f"GitHub returned HTTP {resp.status_code}"
        return info

    data = resp.json()
    tag = str(data.get("tag_name") or "")
    info.latest_version = tag.removeprefix("v") or None
    info.release_notes = data.get("body") or None
    info.release_url = data.get("html_url") or None

    try:
        info.update_available = parse_version(tag) > parse_version(current)
    except ValueError as e:
        info.error = str(e)
    return info
