import os
import sys
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app
from server.state import server_state


def run_tests() -> int:
    print("=" * 60)
    print("Stage 300: Central Server API Test Suite")
    print("=" * 60)

    sample_img_path = "test-samples/vga_sample_campus_01.jpg"
    assert os.path.exists(sample_img_path), f"Missing test image '{sample_img_path}'"

    with open(sample_img_path, "rb") as f:
        sample_img_bytes = f.read()

    with TestClient(app) as client:
        # ---------------------------------------------------------
        # Phase 1: Root & Health Verification
        # ---------------------------------------------------------
        print("\n[Phase 1] Testing Root & Health Endpoints...")
        r_root = client.get("/")
        assert r_root.status_code == 200, f"Root failed: {r_root.text}"
        assert r_root.json().get("status") == "online"
        print("  [✓] Root endpoint online.")

        r_health = client.get("/api/v1/health")
        assert r_health.status_code == 200, f"Health failed: {r_health.text}"
        h_data = r_health.json()
        assert h_data.get("status") == "healthy"
        assert h_data.get("registered_cameras", 0) >= 1
        print(f"  [✓] Health check OK: Uptime={h_data['uptime_seconds']}s, CUDA={h_data['cuda_available']}")

        # ---------------------------------------------------------
        # Phase 2: Pre-Upload Default State
        # ---------------------------------------------------------
        print("\n[Phase 2] Testing Pre-Upload Initial States...")
        r_init_status = client.get("/api/v1/status")
        assert r_init_status.status_code == 200
        init_data = r_init_status.json()
        assert "cam_01" in init_data.get("cameras", {})
        print(f"  [✓] Pre-upload overall status OK: {init_data['total_spots']} total spots.")

        r_init_cam = client.get("/api/v1/cameras/cam_01/status")
        assert r_init_cam.status_code == 200
        cam_init = r_init_cam.json()
        assert cam_init["occupied_spots"] == 0
        assert cam_init["last_processed_at"] is None
        print("  [✓] Pre-upload camera status OK (all spots vacant).")

        r_init_img = client.get("/api/v1/cameras/cam_01/image")
        assert r_init_img.status_code == 404
        print("  [✓] Pre-upload image returned 404 as expected.")

        # ---------------------------------------------------------
        # Phase 3: Frame Ingestion & Inference Pipeline
        # ---------------------------------------------------------
        print("\n[Phase 3] Testing Image Upload Ingestion & Inference...")
        r_upload = client.post(
            "/api/v1/upload/cam_01?battery=85.5&voltage=3.95",
            files={"file": ("vga_campus.jpg", sample_img_bytes, "image/jpeg")},
        )
        assert r_upload.status_code == 200, f"Upload failed: {r_upload.text}"
        up_data = r_upload.json()
        assert up_data["status"] == "success"
        assert up_data["camera_id"] == "cam_01"
        expected_spots = len(server_state.camera_configs["cam_01"].spots)
        assert up_data["total_spots"] == expected_spots
        assert up_data["occupied_spots"] + up_data["free_spots"] == expected_spots
        assert up_data["inference_time_ms"] > 0
        print(
            f"  [✓] Upload processed in {up_data['inference_time_ms']:.1f}ms: "
            f"{up_data['occupied_spots']} occupied, {up_data['free_spots']} free."
        )

        # Microcontroller alias endpoint test
        r_alias = client.post(
            "/upload/cam_01?battery=85.5&voltage=3.95",
            files={"file": ("vga_campus.jpg", sample_img_bytes, "image/jpeg")},
        )
        assert r_alias.status_code == 200, f"Alias upload failed: {r_alias.text}"
        assert r_alias.json()["status"] == "success"
        print("  [✓] Microcontroller upload alias (/upload/{camera_id}) verified.")

        # ---------------------------------------------------------
        # Phase 4: Post-Upload Cached State Verification & Battery
        # ---------------------------------------------------------
        print("\n[Phase 4] Testing In-Memory State Updates & Battery Telemetry...")
        r_post_cam = client.get("/api/v1/cameras/cam_01/status")
        assert r_post_cam.status_code == 200
        post_cam_data = r_post_cam.json()
        assert post_cam_data["last_processed_at"] is not None
        assert post_cam_data["occupied_spots"] == up_data["occupied_spots"]
        assert post_cam_data["free_spots"] == up_data["free_spots"]
        assert post_cam_data["battery_percentage"] == 85.5
        assert post_cam_data["battery_voltage"] == 3.95
        print(f"  [✓] Camera status updated in cache: {post_cam_data['occupied_spots']} occupied, Battery={post_cam_data['battery_percentage']}%.")

        # Test dedicated standalone battery endpoint
        r_bat = client.post(
            "/api/v1/cameras/cam_01/battery",
            json={"battery_percentage": 92.0, "battery_voltage": 4.10},
        )
        assert r_bat.status_code == 200
        assert r_bat.json()["battery_percentage"] == 92.0
        r_post_cam2 = client.get("/api/v1/cameras/cam_01/status")
        assert r_post_cam2.json()["battery_percentage"] == 92.0
        print("  [✓] Dedicated battery telemetry endpoint verified.")

        r_post_overall = client.get("/api/v1/status")
        assert r_post_overall.status_code == 200
        post_overall_data = r_post_overall.json()
        assert post_overall_data["total_occupied"] == up_data["occupied_spots"]
        print("  [✓] Overall status aggregate tally updated.")

        # ---------------------------------------------------------
        # Phase 5: Live Annotated Image Endpoint
        # ---------------------------------------------------------
        print("\n[Phase 5] Testing Live Annotated Image Serving...")
        r_img = client.get("/api/v1/cameras/cam_01/image")
        assert r_img.status_code == 200
        assert "image/jpeg" in r_img.headers.get("content-type", "")
        img_size_kb = len(r_img.content) / 1024.0
        assert img_size_kb > 5.0, f"Image payload too small: {img_size_kb} KB"
        print(f"  [✓] Annotated JPEG served successfully ({img_size_kb:.1f} KB).")

        # ---------------------------------------------------------
        # Phase 6: Error Handling & Rejection
        # ---------------------------------------------------------
        print("\n[Phase 6] Testing Error Rejection...")
        # Unknown camera upload
        r_bad_cam = client.post(
            "/api/v1/upload/non_existent_camera",
            files={"file": ("vga.jpg", sample_img_bytes, "image/jpeg")},
        )
        assert r_bad_cam.status_code == 404
        print("  [✓] Unknown camera upload rejected with 404.")

        # Empty file upload
        r_empty = client.post(
            "/api/v1/upload/cam_01",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )
        assert r_empty.status_code == 400
        print("  [✓] Empty file upload rejected with 400.")

        # Query non-existent camera status
        r_query_bad = client.get("/api/v1/cameras/ghost_camera/status")
        assert r_query_bad.status_code == 404
        print("  [✓] Unknown camera status query rejected with 404.")

        # Query non-existent camera image
        r_img_bad = client.get("/api/v1/cameras/ghost_camera/image")
        assert r_img_bad.status_code == 404
        print("  [✓] Unknown camera image query rejected with 404.")

    print("\n" + "=" * 60)
    print("[✓] ALL STAGE 300 SERVER API TESTS PASSED.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_tests())
    except Exception as e:
        print(f"\n[✗] TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
