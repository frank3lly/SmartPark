import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from storage.database import DEFAULT_DB_PATH, get_db_connection

logger = logging.getLogger("parqueame.storage.repository")


def record_detection_event(
    camera_id: str,
    timestamp: float,
    inference_time_ms: float,
    total_spots: int,
    occupied_spots: int,
    spots: List[Any],
    battery_percentage: Optional[float] = None,
    battery_voltage: Optional[float] = None,
    image_path: Optional[str] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> int:
    """Inserts a camera log row and its child spot records atomically."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Insert parent frame log
        cursor.execute(
            """
            INSERT INTO camera_logs (
                camera_id, timestamp, inference_time_ms, total_spots,
                occupied_spots, battery_percentage, battery_voltage, image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                camera_id,
                timestamp,
                inference_time_ms,
                total_spots,
                occupied_spots,
                battery_percentage,
                battery_voltage,
                image_path,
            ),
        )
        log_id = cursor.lastrowid

        # 2. Prepare child spot records
        spot_rows = []
        for s in spots:
            spot_id = getattr(s, "spot_id", None) or (
                s.get("spot_id") if isinstance(s, dict) else "unknown"
            )
            occupied_val = getattr(s, "occupied", None)
            if occupied_val is None and isinstance(s, dict):
                occupied_val = s.get("occupied", False)
            is_occ = 1 if occupied_val else 0

            conf_val = getattr(s, "confidence", None)
            if conf_val is None and isinstance(s, dict):
                conf_val = s.get("confidence", 0.0)
            confidence = float(conf_val or 0.0)

            spot_rows.append(
                (log_id, camera_id, spot_id, is_occ, confidence, timestamp)
            )

        # 3. Batch insert spots
        if spot_rows:
            cursor.executemany(
                """
                INSERT INTO spot_history (
                    log_id, camera_id, spot_id, is_occupied, confidence, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                spot_rows,
            )

        conn.commit()
        logger.debug(
            f"Recorded event log_id={log_id} for camera='{camera_id}' with {len(spot_rows)} spots."
        )
        return int(log_id)


def get_latest_camera_log(
    camera_id: str,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Retrieves the most recent log and spot states for a specific camera."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM camera_logs
            WHERE camera_id = ?
            ORDER BY timestamp DESC
            LIMIT 1;
            """,
            (camera_id,),
        ).fetchone()

        if not row:
            return None

        log_data = dict(row)
        spot_rows = conn.execute(
            """
            SELECT spot_id, is_occupied, confidence, timestamp
            FROM spot_history
            WHERE log_id = ?
            ORDER BY spot_id ASC;
            """,
            (log_data["id"],),
        ).fetchall()

        log_data["spots"] = [dict(sr) for sr in spot_rows]
        return log_data


def get_camera_logs_window(
    camera_id: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = 1000,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Queries camera logs within an optional time range and camera filter."""
    query = "SELECT * FROM camera_logs WHERE 1=1"
    params: List[Any] = []

    if camera_id:
        query += " AND camera_id = ?"
        params.append(camera_id)
    if start_time is not None:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time is not None:
        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp ASC LIMIT ?"
    params.append(limit)

    with get_db_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_spot_history_window(
    camera_id: str,
    spot_id: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = 5000,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieves chronological state events for spots to compute transitions."""
    query = "SELECT * FROM spot_history WHERE camera_id = ?"
    params: List[Any] = [camera_id]

    if spot_id:
        query += " AND spot_id = ?"
        params.append(spot_id)
    if start_time is not None:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time is not None:
        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp ASC LIMIT ?"
    params.append(limit)

    with get_db_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_system_summary_stats(
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Retrieves database-wide storage statistics."""
    with get_db_connection(db_path) as conn:
        log_count = conn.execute("SELECT COUNT(*) FROM camera_logs;").fetchone()[0]
        spot_count = conn.execute("SELECT COUNT(*) FROM spot_history;").fetchone()[0]
        time_stats = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM camera_logs;"
        ).fetchone()
        cams = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT camera_id FROM camera_logs ORDER BY camera_id;"
            ).fetchall()
        ]

        return {
            "total_logs": log_count,
            "total_spot_records": spot_count,
            "first_log_time": time_stats[0] if time_stats else None,
            "last_log_time": time_stats[1] if time_stats else None,
            "active_cameras": cams,
        }
