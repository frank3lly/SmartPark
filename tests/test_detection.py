import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from detection.detector import VehicleDetector
from detection.occupancy import evaluate_occupancy
from detection.visualizer import draw_detection_overlay

DEFAULT_VGA_SPOTS: List[Dict[str, Any]] = [
    {
        "id": "spot_01",
        "polygon": [[45, 290], [160, 280], [130, 420], [10, 430]],
    },
    {
        "id": "spot_02",
        "polygon": [[165, 280], [280, 275], [260, 415], [135, 420]],
    },
    {
        "id": "spot_03",
        "polygon": [[285, 275], [405, 270], [395, 410], [265, 415]],
    },
    {
        "id": "spot_04",
        "polygon": [[410, 270], [530, 265], [530, 405], [400, 410]],
    },
    {
        "id": "spot_05",
        "polygon": [[535, 265], [635, 260], [635, 400], [535, 405]],
    },
]


def make_fallback_spots(width: int, height: int) -> List[Dict[str, Any]]:
    """Synthesizes a 4-spot grid across the bottom half of the frame."""
    spots = []
    y1 = int(height * 0.55)
    y2 = int(height * 0.92)
    step_w = width // 4
    for i in range(4):
        x1 = i * step_w + 10
        x2 = (i + 1) * step_w - 10
        spots.append(
            {
                "id": f"spot_{i+1:02d}",
                "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            }
        )
    return spots


def run_verification(args: argparse.Namespace) -> int:
    print("=" * 60)
    print("Stage 100: Detection Engine & Spatial Math Verification")
    print("=" * 60)

    if not os.path.exists(args.image):
        print(f"[✗] Error: Test image '{args.image}' not found.")
        return 1

    img = cv2.imread(args.image)
    if img is None:
        print(f"[✗] Error: Failed to decode image '{args.image}'.")
        return 1

    h, w = img.shape[:2]
    print(f"[✓] Loaded input image: '{args.image}' ({w}x{h}, {img.shape[2]} channels)")

    # 1. Initialize detector
    print(f"[i] Initializing VehicleDetector (device override: {args.device})...")
    detector = VehicleDetector(device=args.device, conf_threshold=args.conf)
    print(f"[✓] Detector ready on device: {detector.device}")

    # 2. Select spots
    if w == 640 and h == 480:
        spots = DEFAULT_VGA_SPOTS
        print(f"[✓] Selected calibrated VGA 640x480 parking spot geometry ({len(spots)} spots)")
    else:
        spots = make_fallback_spots(w, h)
        print(f"[✓] Generated synthetic spot geometry for {w}x{h} ({len(spots)} spots)")

    # 3. Run vehicle detection
    detections, latency_ms = detector.detect(img, conf_threshold=args.conf)
    print(f"[✓] Detection completed in {latency_ms:.2f} ms")
    print(f"    - Vehicles detected: {len(detections)}")
    for i, det in enumerate(detections):
        print(f"      [{i+1}] {det.class_name.upper()} (conf: {det.confidence:.2f}) at box: {det.box}")

    # 4. Evaluate spatial occupancy
    occupancy_resp = evaluate_occupancy(
        spots=spots,
        detections=detections,
        camera_id="cam_01",
        inference_time_ms=latency_ms,
    )
    result_dict = occupancy_resp.to_dict()

    print("\n--- Structured JSON Output ---")
    print(json.dumps(result_dict, indent=2))
    print("------------------------------\n")

    print(f"[✓] Occupancy Summary:")
    print(f"    - Total Spots:    {occupancy_resp.total_spots}")
    print(f"    - Occupied Spots: {occupancy_resp.occupied_count}")
    print(f"    - Free Spots:     {occupancy_resp.free_count}")

    # 5. Render diagnostic overlay
    annotated = draw_detection_overlay(
        image=img,
        occupancy_response=occupancy_resp,
        spots=spots,
        detections=detections,
        draw_anchors=True,
        draw_hud=True,
    )

    os.makedirs(args.output_dir, exist_ok=True)
    out_filename = f"verified_{os.path.basename(args.image)}"
    out_path = os.path.join(args.output_dir, out_filename)
    cv2.imwrite(out_path, annotated)

    assert os.path.exists(out_path), f"Output image was not saved at {out_path}"
    file_size_kb = os.path.getsize(out_path) / 1024.0
    print(f"[✓] Saved visual verification image: {out_path} ({file_size_kb:.1f} KB)")

    # Optional GUI display
    if getattr(args, "gui", False):
        if not os.environ.get("DISPLAY"):
            print("[!] Warning: No DISPLAY environment variable detected. Skipping GUI display.")
        else:
            try:
                cv2.imshow("Parqueame - Detection Verification", annotated)
                print("[i] GUI window opened. Press any key in the window to continue...")
                cv2.waitKey(0)
                cv2.destroyAllWindows()
            except Exception as e:
                print(f"[!] Warning: Could not open GUI window ({e}). Continuing headless.")

    # 6. Benchmark mode (optional)
    if args.benchmark:
        print("\n[i] Running benchmark mode (20 iterations)...")
        latencies = []
        for _ in range(20):
            _, iter_ms = detector.detect(img, conf_threshold=args.conf)
            latencies.append(iter_ms)
        avg_ms = float(np.mean(latencies))
        p95_ms = float(np.percentile(latencies, 95))
        fps = 1000.0 / avg_ms if avg_ms > 0 else 0
        print(f"[✓] Benchmark Results:")
        print(f"    - Min Latency: {min(latencies):.2f} ms")
        print(f"    - Avg Latency: {avg_ms:.2f} ms ({fps:.1f} FPS)")
        print(f"    - 95th Percentile: {p95_ms:.2f} ms")
        print(f"    - Max Latency: {max(latencies):.2f} ms")

    # 7. Quality gate assertions
    assert latency_ms > 0.0, "Latency must be strictly positive"
    assert occupancy_resp.total_spots == len(spots), "Mismatch in spot count"
    assert (
        occupancy_resp.occupied_count + occupancy_resp.free_count
        == occupancy_resp.total_spots
    ), "Spot count tally mismatch"
    assert "spots" in result_dict, "Result missing 'spots' key"
    assert "inference_time_ms" in result_dict, "Result missing 'inference_time_ms'"

    print("=" * 60)
    print("[✓] ALL STAGE 100 VERIFICATION CHECKS PASSED.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify Parqueame Stage 100 Detection Engine"
    )
    parser.add_argument(
        "--image",
        type=str,
        default="test-samples/vga_sample_campus_01.jpg",
        help="Path to input JPEG image",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Confidence threshold (default: 0.35)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device override ('cuda:0' or 'cpu')",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tests/output",
        help="Directory to save annotated images",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run 20 iterations for latency and FPS benchmarking",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Display annotated image in a GUI window (press any key to close)",
    )

    cli_args = parser.parse_args()
    sys.exit(run_verification(cli_args))
