"""FastAPI app factory with lifespan, CORS, WebSocket, and static file serving."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from src.events import EventBus, EventType
from src.models import RowingMetrics, StrokeEvent, WorkoutState
from src.updates import UPDATE_HELPER, UpdateInfo, check_for_update, current_version
from src.web.routes.export import router as export_router
from src.web.routes.settings import router as settings_router
from src.web.routes.strava import router as strava_router
from src.web.routes.workouts import router as workouts_router
from src.workout.state import InvalidTransitionError, WorkoutStateMachine

logger = logging.getLogger(__name__)


async def _run_cmd(*cmd: str, timeout_s: float = 30) -> tuple[int, str, str]:
    """Run a command without blocking the event loop. Returns (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def _run_after(delay_s: float, *cmd: str) -> None:
    """Run a system command after a delay (so the HTTP response is sent first)."""
    await asyncio.sleep(delay_s)
    try:
        rc, _, err = await _run_cmd(*cmd)
        if rc != 0:
            logger.error("%s failed (rc=%d): %s", " ".join(cmd), rc, err.strip())
    except Exception as e:
        logger.error("%s failed: %s", " ".join(cmd), e)


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
        self.exporter: Any = None
        self.ws_clients: set[WebSocket] = set()


def create_app(
    event_bus: EventBus | None = None,
    state_machine: WorkoutStateMachine | None = None,
    db: Any = None,
    strava_auth: Any = None,
    exporter: Any = None,
    update_repo: str = "kjaebker/BuoyCast",
    dist_dir: Path | None = None,
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
    app_state.exporter = exporter

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
        version=current_version(),
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
    app.include_router(export_router, prefix="/api")

    # Static file serving for the dashboard SPA
    _dist = (dist_dir or Path(__file__).parent.parent.parent / "dashboard" / "dist").resolve()
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
                app_state.last_metrics_ts.isoformat() if app_state.last_metrics_ts else None
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
    #
    # These run unprivileged. install.sh adds a polkit rule that lets the
    # buoycast user restart its own unit, start buoycast-update.service and
    # reboot — nothing else. (sudo cannot work here: the unit sets
    # NoNewPrivileges=true.)

    @app.post("/api/system/restart")
    async def restart_system():
        """Reboot the Raspberry Pi."""
        logger.warning("System reboot requested via API")
        asyncio.create_task(_run_after(3, "systemctl", "reboot"))
        return {"status": "reboot_scheduled", "delay_seconds": 3}

    @app.post("/api/system/restart-service")
    async def restart_service():
        """Restart the BuoyCast systemd service."""
        logger.warning("Service restart requested via API")
        asyncio.create_task(_run_after(2, "systemctl", "restart", "buoycast.service"))
        return {"status": "service_restart_scheduled", "delay_seconds": 2}

    # ── Software update endpoints ──────────────────────────────────────

    @app.get("/api/system/update/check", response_model=UpdateInfo)
    async def check_update():
        """Compare the running version with the latest GitHub Release."""
        return await check_for_update(update_repo)

    @app.post("/api/system/update", status_code=202)
    async def trigger_update():
        """Install the latest release and restart the service.

        Starts the separate buoycast-update.service unit. It must not run as
        our child: stopping/restarting buoycast.service kills every process
        in its cgroup, which would kill the updater halfway through.
        """
        if not UPDATE_HELPER.exists():
            return JSONResponse(
                status_code=503,
                content={"detail": "Self-update is only available on installs made by install.sh"},
            )

        logger.warning("Software update triggered via API")
        asyncio.create_task(
            _run_after(1, "systemctl", "start", "--no-block", "buoycast-update.service")
        )
        return {
            "status": "update_started",
            "message": "Installing the latest release. The service will restart automatically.",
        }

    @app.get("/api/logs")
    async def get_logs(lines: int = 100):
        """Get recent BuoyCast log lines from journald."""
        lines = max(1, min(lines, 2000))
        try:
            rc, out, err = await _run_cmd(
                "journalctl", "-u", "buoycast", "-n", str(lines), "--no-pager", timeout_s=5
            )
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": f"Log error: {e}"})
        if rc != 0:
            return JSONResponse(status_code=500, content={"detail": f"Log error: {err.strip()}"})
        return {"logs": out}

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
            # Resolve and confine to dist/ — the path param is percent-decoded,
            # so "..%2F" would otherwise escape and expose config.toml / the DB.
            file_path = (_dist / full_path).resolve()
            if file_path.is_relative_to(_dist) and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(_dist / "index.html")

    return app


def _json_dumps(obj: Any) -> str:
    """Fast JSON serialization for WS messages — skips Pydantic overhead."""
    return _json.dumps(obj, separators=(",", ":"))


async def _ws_broadcast_loop(app_state: AppState) -> None:
    """Subscribe to events and broadcast to all connected WebSocket clients.

    Uses a fan-in pattern: one lightweight forwarder task per source queue
    pushes events into a single output queue, avoiding the previous approach
    of creating/cancelling ~10 asyncio.Tasks per event (~50 tasks/sec).
    """
    bus = app_state.event_bus
    if bus is None:
        return

    # Subscribe to merged metrics and all workout state events
    event_types = [
        EventType.MERGED_METRICS,
        EventType.WORKOUT_STARTED,
        EventType.WORKOUT_PAUSED,
        EventType.WORKOUT_RESUMED,
        EventType.WORKOUT_ENDED,
        EventType.IDLE_WARNING,
        EventType.S4_CONNECTED,
        EventType.S4_DISCONNECTED,
        EventType.TICKR_CONNECTED,
        EventType.TICKR_DISCONNECTED,
        EventType.STROKE,
        EventType.EXPORT_STATUS,
    ]

    source_queues = [bus.subscribe(et) for et in event_types]
    fan_in: asyncio.Queue = asyncio.Queue()

    async def _forwarder(src: asyncio.Queue) -> None:
        """Forward events from a source queue to the shared fan-in queue."""
        while True:
            event = await src.get()
            await fan_in.put(event)

    # Start one forwarder per source — lightweight, long-lived tasks
    forwarders = [asyncio.create_task(_forwarder(q)) for q in source_queues]

    try:
        while True:
            event = await fan_in.get()

            # Update last metrics timestamp
            if event.type == EventType.MERGED_METRICS and isinstance(event.data, RowingMetrics):
                app_state.last_metrics_ts = event.data.timestamp

            # Track device connection state
            if event.type == EventType.S4_CONNECTED:
                app_state.s4_connected = True
            elif event.type == EventType.S4_DISCONNECTED:
                app_state.s4_connected = False
            elif event.type == EventType.TICKR_CONNECTED:
                app_state.tickr_connected = True
            elif event.type == EventType.TICKR_DISCONNECTED:
                app_state.tickr_connected = False

            # Build JSON message directly — avoids Pydantic WSMessage overhead
            if event.type == EventType.MERGED_METRICS and isinstance(event.data, RowingMetrics):
                msg_json = _json_dumps(
                    {
                        "type": "metrics_update",
                        "data": event.data.model_dump(mode="json"),
                    }
                )
            elif event.type in (EventType.S4_CONNECTED, EventType.S4_DISCONNECTED):
                reader = app_state.s4_reader
                msg_json = _json_dumps(
                    {
                        "type": "s4_status",
                        "data": {
                            "connected": event.type == EventType.S4_CONNECTED,
                            "paused": reader.paused if reader else False,
                        },
                    }
                )
            elif event.type == EventType.STROKE and isinstance(event.data, StrokeEvent):
                msg_json = _json_dumps(
                    {"type": "stroke", "data": event.data.model_dump(mode="json")}
                )
            elif event.type in (EventType.TICKR_CONNECTED, EventType.TICKR_DISCONNECTED):
                reader = app_state.tickr_reader
                msg_json = _json_dumps(
                    {
                        "type": "tickr_status",
                        "data": {
                            "connected": event.type == EventType.TICKR_CONNECTED,
                            "paused": reader.paused if reader else False,
                        },
                    }
                )
            else:
                msg_json = _json_dumps(
                    {
                        "type": event.type.value,
                        "data": event.data if isinstance(event.data, dict) else {},
                    }
                )

            # Broadcast to all clients
            disconnected = set()
            for ws in app_state.ws_clients:
                try:
                    await ws.send_text(msg_json)
                except Exception:
                    disconnected.add(ws)
            app_state.ws_clients -= disconnected
    finally:
        for t in forwarders:
            t.cancel()
        for et, q in zip(event_types, source_queues):
            bus.unsubscribe(et, q)
