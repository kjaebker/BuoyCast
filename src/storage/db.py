"""Async SQLite database wrapper with schema migrations.

Provides a single Database class wrapping aiosqlite with:
- Versioned, idempotent schema migrations
- In-memory mode for tests (":memory:")
- get_db() FastAPI dependency
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Schema migrations — each entry is (version, description, sql).
# Migrations are applied in order, skipping already-applied versions.
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "initial schema",
        """
        CREATE TABLE IF NOT EXISTS workouts (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            total_distance_m REAL NOT NULL DEFAULT 0,
            total_strokes INTEGER NOT NULL DEFAULT 0,
            elapsed_seconds INTEGER NOT NULL DEFAULT 0,
            avg_pace_s_per_500m REAL,
            avg_stroke_rate REAL,
            avg_power_watts REAL,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            calories INTEGER NOT NULL DEFAULT 0,
            strava_upload_status TEXT NOT NULL DEFAULT 'PENDING',
            strava_activity_id INTEGER,
            strava_error TEXT,
            fit_file_path TEXT
        );

        CREATE TABLE IF NOT EXISTS strokes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
            ts TEXT NOT NULL,
            distance_m REAL NOT NULL,
            stroke_rate REAL NOT NULL,
            power_watts REAL,
            pace_s_per_500m REAL,
            heart_rate_bpm INTEGER,
            rr_intervals_ms TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_strokes_workout ON strokes(workout_id);

        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        """,
    ),
    (
        2,
        "strava token storage",
        """
        CREATE TABLE IF NOT EXISTS strava_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            athlete_id INTEGER,
            athlete_name TEXT
        );
        """,
    ),
]


class Database:
    """Async SQLite wrapper with migration support.

    Usage:
        db = Database("path/to/db.sqlite")
        await db.connect()
        # ... use db.execute(), db.fetch_one(), db.fetch_all() ...
        await db.close()
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    async def connect(self) -> None:
        """Open connection and run pending migrations."""
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a single SQL statement."""
        assert self._conn is not None, "Database not connected"
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a SQL statement for each set of params."""
        assert self._conn is not None, "Database not connected"
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict, or None."""
        assert self._conn is not None, "Database not connected"
        self._conn.row_factory = aiosqlite.Row
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as dicts."""
        assert self._conn is not None, "Database not connected"
        self._conn.row_factory = aiosqlite.Row
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def _migrate(self) -> None:
        """Run pending schema migrations."""
        assert self._conn is not None
        # Ensure schema_version table exists (bootstrap)
        await self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        await self._conn.commit()

        cursor = await self._conn.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        current = row[0] if row and row[0] is not None else 0

        for version, description, sql in MIGRATIONS:
            if version <= current:
                continue
            logger.info("Applying migration %d: %s", version, description)
            await self._conn.executescript(sql)
            await self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            await self._conn.commit()
            logger.info("Migration %d applied", version)


# Singleton for FastAPI dependency injection
_db_instance: Database | None = None


async def get_db() -> Database:
    """FastAPI dependency — returns the shared Database instance."""
    assert _db_instance is not None, "Database not initialized"
    return _db_instance


def set_db(db: Database) -> None:
    """Set the global database instance (called at startup)."""
    global _db_instance
    _db_instance = db
