import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import cv2
from pydantic import ValidationError

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from detection.config_loader import (
    CameraConfig,
    SpotConfig,
    list_available_cameras,
    load_camera_config,
    load_camera_config_by_id,
)
from detection.detector import VehicleDetector
from detection.occupancy import evaluate_occupancy


def test_phase_1_valid_config() -> None:
    print("\n[Phase 1] Testing Valid Configuration Loading...")
    config_path = "config/cameras/cam_01.json"
    assert os.path.exists(config_path), f"Missing reference file '{config_path}'"

    config = load_camera_config(config_path)
    assert config.camera_id == "cam_01", f"Expected cam_01, got {config.camera_id}"
    assert len(config.reference_resolution) == 2, f"Expected [width, height], got {config.reference_resolution}"
    num_spots = len(config.spots)
    assert num_spots >= 5, f"Expected at least 5 spots, got {num_spots}"

    # Test export to Stage 100 spots format
    stage100_spots = config.to_detection_spots()
    assert len(stage100_spots) == num_spots
    for s in stage100_spots:
        assert "id" in s and "polygon" in s
        assert len(s["polygon"]) == 4

    # Test contour extraction
    contours = config.get_spot_contours()
    assert len(contours) == num_spots
    assert contours["spot_01"].shape == (4, 1, 2)

    # Test load by ID
    config_by_id = load_camera_config_by_id("cam_01", config_dir="config/cameras")
    assert config_by_id.camera_id == "cam_01"

    # Test camera list
    cams = list_available_cameras("config/cameras")
    assert "cam_01" in cams
    print("  [✓] Phase 1: Valid configuration loaded and verified successfully.")


def test_phase_2_rejection_rules() -> None:
    print("\n[Phase 2] Testing Schema Validation and Error Rejection...")

    # 1. Out-of-bounds coordinate (X = 700 on 640 width)
    bad_bounds_payload = {
        "camera_id": "test_bad",
        "name": "Bad Bounds",
        "reference_resolution": [640, 480],
        "spots": [
            {"id": "s1", "polygon": [[700, 100], [750, 100], [750, 200], [700, 200]]}
        ]
    }
    try:
        CameraConfig.model_validate(bad_bounds_payload)
        assert False, "Expected ValidationError on out-of-bounds coordinates"
    except (ValidationError, ValueError):
        print("  [✓] Successfully caught out-of-bounds coordinate.")

    # 2. Invalid vertex count (3 points instead of 4)
    triangle_payload = {
        "camera_id": "test_tri",
        "name": "Triangle Spot",
        "reference_resolution": [640, 480],
        "spots": [
            {"id": "s1", "polygon": [[100, 100], [200, 100], [150, 200]]}
        ]
    }
    try:
        CameraConfig.model_validate(triangle_payload)
        assert False, "Expected ValidationError on non-4-point polygon"
    except (ValidationError, ValueError):
        print("  [✓] Successfully caught non-4-point polygon.")

    # 3. Degenerate collinear points (area <= 50)
    collinear_payload = {
        "camera_id": "test_flat",
        "name": "Flat Spot",
        "reference_resolution": [640, 480],
        "spots": [
            {"id": "s1", "polygon": [[100, 100], [150, 100], [200, 100], [250, 100]]}
        ]
    }
    try:
        CameraConfig.model_validate(collinear_payload)
        assert False, "Expected ValidationError on zero-area polygon"
    except (ValidationError, ValueError):
        print("  [✓] Successfully caught degenerate zero-area polygon.")

    # 4. Duplicate Spot IDs
    duplicate_id_payload = {
        "camera_id": "test_dup",
        "name": "Duplicate IDs",
        "reference_resolution": [640, 480],
        "spots": [
            {"id": "spot_A", "polygon": [[10, 10], [50, 10], [50, 50], [10, 50]]},
            {"id": "spot_A", "polygon": [[60, 10], [90, 10], [90, 50], [60, 50]]},
        ]
    }
    try:
        CameraConfig.model_validate(duplicate_id_payload)
        assert False, "Expected ValidationError on duplicate spot IDs"
    except (ValidationError, ValueError):
        print("  [✓] Successfully caught duplicate spot IDs.")

    # 5. Non-existent file
    try:
        load_camera_config("config/cameras/non_existent_cam.json")
        assert False, "Expected FileNotFoundError on missing file"
    except FileNotFoundError:
        print("  [✓] Successfully caught missing configuration file.")

    # 6. Non-JSON extension
    try:
        load_camera_config("config/cameras/cam_01.txt")
        assert False, "Expected ValueError on non-json extension"
    except (ValueError, FileNotFoundError):
        print("  [✓] Successfully caught non-json extension.")

    print("  [✓] Phase 2: All validation rejection rules verified.")


def test_phase_3_json_roundtrip() -> None:
    print("\n[Phase 3] Testing JSON Serialization Roundtrip...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / "cam_roundtrip.json"
        sample_data = {
            "camera_id": "cam_roundtrip",
            "name": "Temporary Roundtrip Camera",
            "description": "Roundtrip validation test",
            "reference_resolution": [640, 480],
            "spots": [
                {"id": "spot_01", "polygon": [[50, 50], [150, 50], [150, 150], [50, 150]]},
                {"id": "spot_02", "polygon": [[200, 50], [300, 50], [300, 150], [200, 150]]}
            ]
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2)

        loaded = load_camera_config(tmp_file)
        assert loaded.camera_id == "cam_roundtrip"
        assert len(loaded.spots) == 2
        assert loaded.spots[0].id == "spot_01"
        assert loaded.spots[1].id == "spot_02"

    print("  [✓] Phase 3: Round-trip JSON serialization verified.")


def test_phase_4_stage100_integration() -> None:
    print("\n[Phase 4] Testing End-to-End Integration with Stage 100...")
    img_path = "test-samples/vga_sample_campus_01.jpg"
    assert os.path.exists(img_path), f"Missing test image: '{img_path}'"

    img = cv2.imread(img_path)
    assert img is not None, f"Failed to read image: '{img_path}'"

    # 1. Load spots from JSON configuration
    config = load_camera_config("config/cameras/cam_01.json")
    spots = config.to_detection_spots()

    # 2. Run vehicle detector
    detector = VehicleDetector()
    detections, latency_ms = detector.detect(img)

    # 3. Evaluate occupancy using JSON spots
    resp = evaluate_occupancy(
        spots=spots,
        detections=detections,
        camera_id=config.camera_id,
        inference_time_ms=latency_ms,
    )

    print(f"  - Camera ID: {resp.camera_id}")
    print(f"  - Total spots evaluated: {resp.total_spots}")
    print(f"  - Occupied count: {resp.occupied_count}")
    print(f"  - Free count: {resp.free_count}")
    print(f"  - Inference latency: {resp.inference_time_ms:.2f} ms")

    assert resp.camera_id == "cam_01"
    assert resp.total_spots == len(spots)
    assert resp.occupied_count + resp.free_count == len(spots)
    assert resp.inference_time_ms > 0.0

    print("  [✓] Phase 4: Stage 100 + Stage 200 integration verified successfully.")


def main() -> int:
    print("=" * 60)
    print("Stage 200: ROI Configuration & Integration Test Suite")
    print("=" * 60)

    try:
        test_phase_1_valid_config()
        test_phase_2_rejection_rules()
        test_phase_3_json_roundtrip()
        test_phase_4_stage100_integration()
        print("\n" + "=" * 60)
        print("[✓] ALL STAGE 200 TESTS AND INTEGRATION CHECKS PASSED.")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n[✗] TEST FAILURE: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
