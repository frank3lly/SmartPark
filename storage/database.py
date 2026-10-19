import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union

logger = logging.getLogger("parqueame.storage.database")

DEFAULT_DB_PATH = Path("storage/parqueame.db")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS camera_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    inference_time_ms REAL NOT NULL,
    total_spots INTEGER NOT NULL,
    occupied_spots INTEGER NOT NULL,
    battery_percentage REAL,
    battery_voltage REAL,
    image_path TEXT
);

CREATE TABLE IF NOT EXISTS spot_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL REFERENCES camera_logs(id) ON DELETE CASCADE,
    camera_id TEXT NOT NULL,
    spot_id TEXT NOT NULL,
    is_occupied INTEGER NOT NULL CHECK (is_occupied IN (0, 1)),
    confidence REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_camera_logs_cam_time ON camera_logs(camera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_spot_time ON spot_history(camera_id, spot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_spot_history_log ON spot_history(log_id);
"""


def init_db(db_path: Union[str, Path] = DEFAULT_DB_PATH) -> None:
    """Creates the SQLite database file and tables if they do not exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing SQLite database at: {path}")
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialized successfully with WAL mode and indexes.")
    finally:
        conn.close()


@contextmanager
def get_db_connection(
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing a managed SQLite connection with Row factory and foreign keys."""
    path = Path(db_path)
    if not path.exists():
        init_db(path)

    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        conn.close()
