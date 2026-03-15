"""FastAPI app factory with lifespan, CORS, WebSocket, and static file serving."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from src.events import EventBus, EventType
from src.models import RowingMetrics, WorkoutState, WSMessage
from src.web.routes.settings import router as settings_router
from src.web.routes.strava import router as strava_router
from src.web.routes.workouts import router as workouts_router
from src.workout.state import InvalidTransitionError, WorkoutStateMachine

logger = logging.getLogger(__name__)

INSTALL_DIR = Path("/opt/buoycast")


async def check_git_updates() -> dict:
    """Fetch from origin and compare local HEAD vs remote. Returns update info dict."""
    import subprocess

    project_root = Path(__file__).parent.parent.parent

    # Find the git repo — either /opt/buoycast or the source dir recorded during install
    git_dir: Path | None = None
    if (INSTALL_DIR / ".git").exists():
        git_dir = INSTALL_DIR
    elif (INSTALL_DIR / ".source_dir").exists():
        source = INSTALL_DIR.joinpath(".source_dir").read_text().strip()
        if Path(source, ".git").exists():
            git_dir = Path(source)
    # Fallback for dev: use the project root
    if git_dir is None and (project_root / ".git").exists():
        git_dir = project_root

    if git_dir is None:
        return {
            "current_sha": None,
            "remote_sha": None,
            "update_available": False,
            "commits_behind": 0,
            "latest_commit_message": None,
            "error": "No git repository found",
        }

    try:
        # Run git commands as the pi user to avoid permission issues
        # (the service runs as pi, but .git may have mixed ownership)
        git_cmd = ["sudo", "-u", "pi", "git", "-C", str(git_dir)]

        # Fetch latest from origin (non-blocking via asyncio)
        proc = await asyncio.create_subprocess_exec(
            *git_cmd, "fetch", "origin", "main", "--quiet",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return {
                "current_sha": None,
                "remote_sha": None,
                "update_available": False,
                "commits_behind": 0,
                "latest_commit_message": None,
                "error": f"git fetch failed: {stderr.decode().strip()}",
            }

        # Get local and remote HEAD
        local = subprocess.run(
            [*git_cmd, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        remote = subprocess.run(
            [*git_cmd, "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        # Count commits behind
        behind_output = subprocess.run(
            [*git_cmd, "rev-list", "--count", f"HEAD..origin/main"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        commits_behind = int(behind_output) if behind_output.isdigit() else 0

        # Get latest remote commit message
        latest_msg = subprocess.run(
            [*git_cmd, "log", "origin/main", "-1", "--format=%s"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        return {
            "current_sha": local[:8],
            "remote_sha": remote[:8],
            "update_available": local != remote,
            "commits_behind": commits_behind,
            "latest_commit_message": latest_msg if local != remote else None,
            "error": None,
        }
    except asyncio.TimeoutError:
        return {
            "current_sha": None,
            "remote_sha": None,
            "update_available": False,
            "commits_behind": 0,
            "latest_commit_message": None,
            "error": "git fetch timed out",
        }
    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return {
            "current_sha": None,
            "remote_sha": None,
            "update_available": False,
            "commits_behind": 0,
            "latest_commit_message": None,
            "error": f"Failed to check: {e}",
        }


class AppState:
    """Shared application state — injected into routes via app.state."""

    def __init__(self) -> None:
        self.event_bus: EventBus | None = None
        self.state_machine: WorkoutStateMachine | None = None
        self.db: Any = None
        self.s4_reader: Any = None
        self.tickr_reader: Any = None
        self.s4_connected: bool = False
        self.tickr_connected: bool = False
        self.start_time: float = time.monotonic()
        self.last_metrics_ts: datetime | None = None
        self.strava_auth: Any = None
        self.ws_clients: set[WebSocket] = set()


def create_app(
    event_bus: EventBus | None = None,
    state_machine: WorkoutStateMachine | None = None,
    db: Any = None,
    strava_auth: Any = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        event_bus: Shared event bus (None for testing without events).
        state_machine: Workout state machine instance.
        db: Database instance.
    """
    app_state = AppState()
    app_state.event_bus = event_bus
    app_state.state_machine = state_machine
    app_state.db = db
    app_state.strava_auth = strava_auth

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Start WebSocket broadcast task if event bus is available
        ws_task = None
        if app_state.event_bus is not None:
            ws_task = asyncio.create_task(_ws_broadcast_loop(app_state))
        yield
        if ws_task is not None:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="BuoyCast",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store state on the app
    app.state.app_state = app_state

    # CORS for development (dashboard on different port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler for InvalidTransitionError -> 409
    @app.exception_handler(InvalidTransitionError)
    async def transition_error_handler(request: Request, exc: InvalidTransitionError):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    # Include routers
    app.include_router(workouts_router, prefix="/api")
    app.include_router(strava_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    # Static file serving for the dashboard SPA
    _dist = Path(__file__).parent.parent.parent / "dashboard" / "dist"
    if _dist.exists():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    # Status endpoint
    @app.get("/api/status")
    async def get_status():
        sm = app_state.state_machine
        s4_reader = app_state.s4_reader
        tickr_reader = app_state.tickr_reader
        return {
            "s4_connected": app_state.s4_connected,
            "s4_paused": s4_reader.paused if s4_reader else False,
            "tickr_connected": app_state.tickr_connected,
            "tickr_paused": tickr_reader.paused if tickr_reader else False,
            "workout_state": sm.state.value if sm else WorkoutState.IDLE.value,
            "uptime_seconds": int(time.monotonic() - app_state.start_time),
            "last_metrics_ts": (
                app_state.last_metrics_ts.isoformat()
                if app_state.last_metrics_ts
                else None
            ),
        }

    # S4 polling control
    @app.post("/api/s4/connect")
    async def s4_connect():
        reader = app_state.s4_reader
        if reader is None:
            return JSONResponse(status_code=503, content={"detail": "S4 reader not available"})
        reader.resume_polling()
        logger.info("S4 polling resumed via API")
        return {"s4_paused": False}

    @app.post("/api/s4/disconnect")
    async def s4_disconnect():
        reader = app_state.s4_reader
        if reader is None:
            return JSONResponse(status_code=503, content={"detail": "S4 reader not available"})
        await reader.disconnect_and_pause()
        logger.info("S4 polling paused via API")
        return {"s4_paused": True}

    @app.post("/api/s4/reset")
    async def s4_reset():
        """Send USB_RESET command to S4 to clear workout counters."""
        reader = app_state.s4_reader
        if reader is None:
            return JSONResponse(status_code=503, content={"detail": "S4 not available"})
        await reader.send_reset()
        logger.info("S4 reset via API")
        return {"status": "reset_sent"}

    # HR control
    @app.post("/api/hr/disconnect")
    async def hr_disconnect():
        """Pause TICKR reading (disconnect, no auto-reconnect)."""
        reader = app_state.tickr_reader
        if reader is None:
            return JSONResponse(status_code=503, content={"detail": "TICKR not available"})
        await reader.pause_reading()
        return {"tickr_paused": True}

    @app.post("/api/hr/connect")
    async def hr_connect():
        """Resume TICKR reading (allow reconnection)."""
        reader = app_state.tickr_reader
        if reader is None:
            return JSONResponse(status_code=503, content={"detail": "TICKR not available"})
        await reader.resume_reading()
        return {"tickr_paused": False}

    # System control
    @app.post("/api/system/restart")
    async def restart_system():
        """Restart Raspberry Pi (requires passwordless sudo for reboot)."""
        import subprocess

        logger.warning("System restart requested via API")
        asyncio.create_task(_delayed_reboot())
        return {"status": "reboot_scheduled", "delay_seconds": 3}

    async def _delayed_reboot():
        """Delay before reboot to allow response to be sent."""
        await asyncio.sleep(3)
        try:
            subprocess.run(["sudo", "reboot"], check=True)
        except Exception as e:
            logger.error("Restart failed: %s", e)

    @app.post("/api/system/restart-service")
    async def restart_service():
        """Restart BuoyCast systemd service (requires passwordless sudo)."""
        import subprocess

        logger.warning("Service restart requested via API")
        asyncio.create_task(_delayed_service_restart())
        return {"status": "service_restart_scheduled", "delay_seconds": 2}

    async def _delayed_service_restart():
        """Delay before service restart to allow response to be sent."""
        await asyncio.sleep(2)
        try:
            subprocess.run(["sudo", "systemctl", "restart", "waterrower"], check=True)
        except Exception as e:
            logger.error("Service restart failed: %s", e)

    # ── Software update endpoints ──────────────────────────────────────

    @app.get("/api/system/update/check")
    async def check_for_update():
        """Check if new commits are available on origin/main.

        Runs git fetch and compares local HEAD vs remote HEAD.
        """
        return await check_git_updates()

    @app.post("/api/system/update")
    async def trigger_update():
        """Pull latest code and restart the service.

        Runs update.sh in the background. The service will restart
        automatically after the update completes, so the dashboard will
        briefly disconnect and reconnect.
        """
        # Check that update.sh exists
        update_script = INSTALL_DIR / "update.sh"
        if not update_script.exists():
            update_script = Path(__file__).parent.parent.parent / "update.sh"
        if not update_script.exists():
            return JSONResponse(
                status_code=503,
                content={"detail": "update.sh not found"},
            )

        logger.warning("Software update triggered via API")

        # Run update in background — it will restart the service at the end
        asyncio.create_task(_run_update(str(update_script)))
        return {
            "status": "update_started",
            "message": "Pulling latest code and restarting. The service will restart automatically.",
        }

    async def _run_update(script_path: str):
        """Run update.sh in a subprocess after a short delay."""
        await asyncio.sleep(1)  # Let the response be sent first
        try:
            subprocess.Popen(
                ["sudo", "bash", script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from our process group
            )
        except Exception as e:
            logger.error("Update failed to start: %s", e)

    @app.get("/api/logs")
    async def get_logs(lines: int = 100):
        """Get recent logs from journald."""
        import subprocess

        try:
            result = subprocess.run(
                ["journalctl", "-u", "buoycast", "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return {"logs": result.stdout}
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Log error: {e}"})

    # WebSocket endpoint
    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        await websocket.accept()
        app_state.ws_clients.add(websocket)
        logger.info("WebSocket client connected (%d total)", len(app_state.ws_clients))
        try:
            while True:
                # Keep connection alive — wait for client messages (ping/close)
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            app_state.ws_clients.discard(websocket)
            logger.info(
                "WebSocket client disconnected (%d remaining)",
                len(app_state.ws_clients),
            )

    # SPA catch-all: serve index.html for any non-API, non-asset path
    if _dist.exists():

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = _dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(_dist / "index.html")

    return app


async def _ws_broadcast_loop(app_state: AppState) -> None:
    """Subscribe to events and broadcast to all connected WebSocket clients."""
    bus = app_state.event_bus
    if bus is None:
        return

    # Subscribe to merged metrics and all workout state events
    metrics_q = bus.subscribe(EventType.MERGED_METRICS)
    started_q = bus.subscribe(EventType.WORKOUT_STARTED)
    paused_q = bus.subscribe(EventType.WORKOUT_PAUSED)
    resumed_q = bus.subscribe(EventType.WORKOUT_RESUMED)
    ended_q = bus.subscribe(EventType.WORKOUT_ENDED)
    idle_q = bus.subscribe(EventType.IDLE_WARNING)
    s4_conn_q = bus.subscribe(EventType.S4_CONNECTED)
    s4_disc_q = bus.subscribe(EventType.S4_DISCONNECTED)

    queues = [metrics_q, started_q, paused_q, resumed_q, ended_q, idle_q, s4_conn_q, s4_disc_q]

    while True:
        # Wait for any event from any queue
        done, _ = await asyncio.wait(
            [asyncio.create_task(q.get()) for q in queues],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            try:
                event = task.result()
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

            # Update last metrics timestamp
            if event.type == EventType.MERGED_METRICS and isinstance(
                event.data, RowingMetrics
            ):
                app_state.last_metrics_ts = event.data.timestamp

            # Track S4 connection state
            if event.type == EventType.S4_CONNECTED:
                app_state.s4_connected = True
            elif event.type == EventType.S4_DISCONNECTED:
                app_state.s4_connected = False

            # Build WSMessage
            if event.type == EventType.MERGED_METRICS and isinstance(
                event.data, RowingMetrics
            ):
                msg = WSMessage(
                    type="metrics_update",
                    data=event.data.model_dump(mode="json"),
                )
            elif event.type in (EventType.S4_CONNECTED, EventType.S4_DISCONNECTED):
                reader = app_state.s4_reader
                msg = WSMessage(
                    type="s4_status",
                    data={
                        "connected": event.type == EventType.S4_CONNECTED,
                        "paused": reader.paused if reader else False,
                    },
                )
            else:
                msg = WSMessage(
                    type=event.type.value,
                    data=event.data if isinstance(event.data, dict) else {},
                )

            # Broadcast to all clients
            msg_json = msg.model_dump_json()
            disconnected = set()
            for ws in app_state.ws_clients:
                try:
                    await ws.send_text(msg_json)
                except Exception:
                    disconnected.add(ws)
            app_state.ws_clients -= disconnected

        # Cancel remaining pending tasks
        for task in _ if _ else set():
            task.cancel()
