import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from storage.database import DEFAULT_DB_PATH, get_db_connection
from storage.repository import (
    get_camera_logs_window,
    get_spot_history_window,
)

logger = logging.getLogger("parqueame.storage.analytics")


def compute_spot_flow_metrics(
    camera_id: str,
    spot_id: str,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Computes turnover count, average stay duration, and occupancy rate for one spot."""
    events = get_spot_history_window(
        camera_id=camera_id,
        spot_id=spot_id,
        start_time=start_time,
        end_time=end_time,
        db_path=db_path,
    )

    if not events:
        return {
            "spot_id": spot_id,
            "turnover_count": 0,
            "average_duration_minutes": 0.0,
            "occupancy_percentage": 0.0,
            "total_sessions_recorded": 0,
            "currently_occupied": False,
        }

    turnovers = 0
    completed_durations_sec: List[float] = []
    current_session_start: Optional[float] = None
    total_occupied_sec: float = 0.0

    # Handle first sample
    if events[0]["is_occupied"] == 1:
        current_session_start = events[0]["timestamp"]

    for i in range(1, len(events)):
        prev_occ = events[i - 1]["is_occupied"]
        curr_occ = events[i]["is_occupied"]
        t_prev = events[i - 1]["timestamp"]
        t_curr = events[i]["timestamp"]
        dt = t_curr - t_prev

        if prev_occ == 1:
            total_occupied_sec += dt

        # Arrival: 0 -> 1
        if prev_occ == 0 and curr_occ == 1:
            turnovers += 1
            current_session_start = t_curr

        # Departure: 1 -> 0
        elif prev_occ == 1 and curr_occ == 0:
            if current_session_start is not None:
                duration = t_curr - current_session_start
                if duration > 0:
                    completed_durations_sec.append(duration)
                current_session_start = None

    total_window_sec = events[-1]["timestamp"] - events[0]["timestamp"]
    if total_window_sec <= 0:
        total_window_sec = 1.0

    occ_pct = (total_occupied_sec / total_window_sec) * 100.0
    occ_pct = max(0.0, min(100.0, occ_pct))

    avg_duration_min = (
        (sum(completed_durations_sec) / len(completed_durations_sec)) / 60.0
        if completed_durations_sec
        else 0.0
    )

    return {
        "spot_id": spot_id,
        "turnover_count": turnovers,
        "average_duration_minutes": round(avg_duration_min, 1),
        "occupancy_percentage": round(occ_pct, 1),
        "total_sessions_recorded": len(completed_durations_sec),
        "currently_occupied": bool(events[-1]["is_occupied"]),
    }


def compute_camera_flow_summary(
    camera_id: str,
    hours: float = 2.0,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Computes aggregate flow metrics, turnover rates, and peak usage for a camera."""
    now = time.time()
    start_time = now - (hours * 3600.0)

    logs = get_camera_logs_window(
        camera_id=camera_id,
        start_time=start_time,
        end_time=now,
        db_path=db_path,
    )

    if not logs:
        return {
            "camera_id": camera_id,
            "time_window_hours": hours,
            "total_stalls": 0,
            "total_turnovers": 0,
            "turnover_rate_per_stall": 0.0,
            "average_duration_minutes": 0.0,
            "average_occupancy_percentage": 0.0,
            "peak_occupied_spots": 0,
            "peak_timestamp": None,
            "spots_breakdown": {},
        }

    total_stalls = logs[-1]["total_spots"]

    # Peak calculation
    peak_occ = max(log["occupied_spots"] for log in logs)
    peak_log = next(log for log in logs if log["occupied_spots"] == peak_occ)

    # Average occupancy rate
    avg_occ_spots = sum(log["occupied_spots"] for log in logs) / len(logs)
    avg_occ_pct = (avg_occ_spots / total_stalls * 100.0) if total_stalls > 0 else 0.0

    # Granular spot breakdown
    with get_db_connection(db_path) as conn:
        spot_ids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT spot_id FROM spot_history WHERE camera_id = ? ORDER BY spot_id;",
                (camera_id,),
            ).fetchall()
        ]

    spots_metrics = {}
    total_turnovers = 0
    all_durations = []

    for sid in spot_ids:
        sm = compute_spot_flow_metrics(
            camera_id=camera_id,
            spot_id=sid,
            start_time=start_time,
            end_time=now,
            db_path=db_path,
        )
        spots_metrics[sid] = sm
        total_turnovers += sm["turnover_count"]
        if sm["average_duration_minutes"] > 0:
            all_durations.append(sm["average_duration_minutes"])

    turnover_rate = (
        round(total_turnovers / total_stalls, 2) if total_stalls > 0 else 0.0
    )
    overall_avg_duration = (
        round(sum(all_durations) / len(all_durations), 1)
        if all_durations
        else 0.0
    )

    return {
        "camera_id": camera_id,
        "time_window_hours": hours,
        "total_stalls": total_stalls,
        "total_turnovers": total_turnovers,
        "turnover_rate_per_stall": turnover_rate,
        "average_duration_minutes": overall_avg_duration,
        "average_occupancy_percentage": round(avg_occ_pct, 1),
        "peak_occupied_spots": peak_occ,
        "peak_timestamp": peak_log["timestamp"],
        "spots_breakdown": spots_metrics,
    }


def compute_timeline_series(
    camera_id: Optional[str] = None,
    hours: float = 2.0,
    bucket_minutes: int = 15,
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Bins detection logs into time intervals for frontend charts."""
    now = time.time()
    start_time = now - (hours * 3600.0)

    logs = get_camera_logs_window(
        camera_id=camera_id,
        start_time=start_time,
        end_time=now,
        limit=10000,
        db_path=db_path,
    )

    if not logs:
        return []

    bucket_sec = bucket_minutes * 60
    buckets: Dict[int, List[Dict[str, Any]]] = {}

    for log in logs:
        b_key = int(log["timestamp"] // bucket_sec) * bucket_sec
        if b_key not in buckets:
            buckets[b_key] = []
        buckets[b_key].append(log)

    series = []
    for b_ts in sorted(buckets.keys()):
        b_logs = buckets[b_ts]
        avg_occ = sum(l["occupied_spots"] for l in b_logs) / len(b_logs)
        avg_free = max(
            0.0,
            sum(l["total_spots"] - l["occupied_spots"] for l in b_logs)
            / len(b_logs),
        )
        time_label = datetime.fromtimestamp(b_ts).strftime("%H:%M")

        series.append(
            {
                "timestamp": b_ts,
                "time_label": time_label,
                "occupied_avg": round(avg_occ, 1),
                "free_avg": round(avg_free, 1),
                "sample_count": len(b_logs),
            }
        )

    return series
