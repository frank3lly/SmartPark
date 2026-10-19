import os
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app
from storage.analytics import (
    compute_camera_flow_summary,
    compute_spot_flow_metrics,
    compute_timeline_series,
)
from storage.database import get_db_connection, init_db
from storage.repository import (
    get_camera_logs_window,
    get_latest_camera_log,
    get_spot_history_window,
    get_system_summary_stats,
    record_detection_event,
)


def run_tests() -> int:
    print("=" * 60)
    print("Stage 400: Storage & Flow Analytics Test Suite")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_stage400.db"

        # ---------------------------------------------------------
        # Phase 1: Database Schema & Integrity
        # ---------------------------------------------------------
        print("\n[Phase 1] Testing Database Initialization & Schema...")
        init_db(test_db)
        assert test_db.exists(), "Test database was not created"

        with get_db_connection(test_db) as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert fk == 1, "Foreign keys not active"

            # Test cascade deletion
            cur = conn.execute(
                "INSERT INTO camera_logs (camera_id, timestamp, inference_time_ms, total_spots, occupied_spots) VALUES ('c1', 100, 5, 1, 1)"
            )
            lid = cur.lastrowid
            conn.execute(
                "INSERT INTO spot_history (log_id, camera_id, spot_id, is_occupied, confidence, timestamp) VALUES (?, 'c1', 's1', 1, 0.9, 100)",
                (lid,),
            )
            conn.commit()
            conn.execute("DELETE FROM camera_logs WHERE id = ?", (lid,))
            conn.commit()
            rem = conn.execute(
                "SELECT COUNT(*) FROM spot_history WHERE log_id = ?", (lid,)
            ).fetchone()[0]
            assert rem == 0, "Cascade deletion failed"
        print("  [✓] Schema, WAL mode, foreign keys, and cascade deletion verified.")

        # ---------------------------------------------------------
        # Phase 2: Repository Operations
        # ---------------------------------------------------------
        print("\n[Phase 2] Testing Repository Data Operations...")
        now = time.time()
        log_id = record_detection_event(
            camera_id="cam_01",
            timestamp=now,
            inference_time_ms=12.4,
            total_spots=2,
            occupied_spots=1,
            spots=[
                {"spot_id": "spot_A1", "occupied": True, "confidence": 0.94},
                {"spot_id": "spot_A2", "occupied": False, "confidence": 0.0},
            ],
            battery_percentage=88.5,
            battery_voltage=4.02,
            db_path=test_db,
        )
        assert log_id > 0, "Insert returned invalid log_id"

        latest = get_latest_camera_log("cam_01", db_path=test_db)
        assert latest is not None
        assert latest["battery_percentage"] == 88.5
        assert len(latest["spots"]) == 2
        print("  [✓] Repository event persistence verified.")

        # ---------------------------------------------------------
        # Phase 3: Flow Analytics Mathematical Verification
        # ---------------------------------------------------------
        print("\n[Phase 3] Testing Flow Analytics Math against Ground Truth...")
        t_base = time.time() - 3600.0  # 1 hour ago
        # Simulate:
        # Step 0 (0s): S1=0, S2=0
        # Step 1 (600s): S1=1, S2=0  (Arrival 1 for S1)
        # Step 2 (1500s): S1=0, S2=0 (Departure 1 for S1: stay 900s = 15m)
        # Step 3 (2100s): S1=1, S2=1 (Arrival 2 for S1, Arrival 1 for S2)
        # Step 4 (3600s): S1=0, S2=1 (Departure 2 for S1: stay 1500s = 25m)
        timeline_steps = [
            (0, 0, 0),
            (600, 1, 0),
            (1500, 0, 0),
            (2100, 1, 1),
            (3600, 0, 1),
        ]
        for sec, s1_occ, s2_occ in timeline_steps:
            t = t_base + sec
            record_detection_event(
                camera_id="cam_sim",
                timestamp=t,
                inference_time_ms=9.0,
                total_spots=2,
                occupied_spots=(s1_occ + s2_occ),
                spots=[
                    {
                        "spot_id": "spot_01",
                        "occupied": bool(s1_occ),
                        "confidence": 0.9 if s1_occ else 0.0,
                    },
                    {
                        "spot_id": "spot_02",
                        "occupied": bool(s2_occ),
                        "confidence": 0.9 if s2_occ else 0.0,
                    },
                ],
                db_path=test_db,
            )

        # Evaluate Spot 1
        m1 = compute_spot_flow_metrics("cam_sim", "spot_01", db_path=test_db)
        assert (
            m1["turnover_count"] == 2
        ), f"Expected 2 turnovers, got {m1['turnover_count']}"
        assert (
            m1["total_sessions_recorded"] == 2
        ), f"Expected 2 sessions, got {m1['total_sessions_recorded']}"
        assert (
            19.5 <= m1["average_duration_minutes"] <= 20.5
        ), f"Expected 20.0m avg duration, got {m1['average_duration_minutes']}"
        print(
            f"  [✓] Spot 1 flow metrics accurate: turnovers={m1['turnover_count']}, avg_duration={m1['average_duration_minutes']} min."
        )

        # Evaluate Camera Summary
        cam_summary = compute_camera_flow_summary(
            "cam_sim", hours=2.0, db_path=test_db
        )
        assert (
            cam_summary["peak_occupied_spots"] == 2
        ), f"Expected peak 2, got {cam_summary['peak_occupied_spots']}"
        assert (
            cam_summary["total_turnovers"] == 3
        ), f"Expected total 3 turnovers, got {cam_summary['total_turnovers']}"
        print(
            f"  [✓] Camera flow summary accurate: peak_occupied={cam_summary['peak_occupied_spots']}, total_turnovers={cam_summary['total_turnovers']}."
        )

        # ---------------------------------------------------------
        # Phase 4: Timeline Aggregation
        # ---------------------------------------------------------
        print("\n[Phase 4] Testing Timeline Series Bucketing...")
        series = compute_timeline_series(
            "cam_sim", hours=2.0, bucket_minutes=15, db_path=test_db
        )
        assert len(series) > 0, "Expected non-empty timeline series"
        assert "time_label" in series[0] and "occupied_avg" in series[0]
        print(f"  [✓] Generated {len(series)} timeline bucket intervals.")

    # ---------------------------------------------------------
    # Phase 5: REST API Endpoints Verification
    # ---------------------------------------------------------
    print("\n[Phase 5] Testing FastAPI Analytics Routes...")
    with TestClient(app) as client:
        r_storage = client.get("/api/v1/analytics/storage")
        assert r_storage.status_code == 200
        print("  [✓] GET /api/v1/analytics/storage online.")

        r_cam = client.get("/api/v1/analytics/cameras/cam_01?hours=24")
        assert r_cam.status_code == 200
        assert "total_turnovers" in r_cam.json()
        print("  [✓] GET /api/v1/analytics/cameras/cam_01 valid.")

        r_time = client.get("/api/v1/analytics/timeline?hours=24&bucket_minutes=15")
        assert r_time.status_code == 200
        print("  [✓] GET /api/v1/analytics/timeline valid.")

        r_bad = client.get("/api/v1/analytics/cameras/ghost_camera")
        assert r_bad.status_code == 404
        print("  [✓] Non-existent camera correctly rejected with 404.")

    print("\n" + "=" * 60)
    print("[✓] ALL STAGE 400 STORAGE & ANALYTICS TESTS PASSED.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_tests())
    except Exception as e:
        print(f"\n[✗] TEST FAILURE: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
