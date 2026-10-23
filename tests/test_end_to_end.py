import argparse
import json
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage.analytics as analytics_mod
import storage.database as db_mod
import storage.repository as repo_mod
from server.main import app
from server.state import server_state
from storage.database import get_db_connection, init_db


def parse_ground_truth_xml(xml_path: Path) -> Dict[str, bool]:
    """Parses a PKLot XML ground truth file, mapping spot IDs to occupancy booleans."""
    if not xml_path.is_file():
        return {}
    occupancy_map: Dict[str, bool] = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for space in root.findall("space"):
            space_id = space.attrib.get("id")
            occ_str = space.attrib.get("occupied", "0")
            is_occupied = (occ_str.strip() == "1")
            if space_id is not None:
                clean_id = space_id.strip()
                occupancy_map[clean_id] = is_occupied
                try:
                    num = int(re.sub(r"[^0-9]", "", clean_id))
                    occupancy_map[f"spot_{num:02d}"] = is_occupied
                    occupancy_map[f"spot_{num}"] = is_occupied
                except ValueError:
                    pass
    except Exception as e:
        print(f"[WARNING] Error reading XML '{xml_path}': {e}")
    return occupancy_map


def generate_graphic_report(
    report_paths: List[Path],
    camera_id: str,
    total_frames: int,
    tp: int,
    tn: int,
    fp: int,
    fn: int,
    accuracies: List[float],
    gt_occupied_counts: List[int],
    det_occupied_counts: List[int],
    inference_latencies: List[float],
    sample_img_rgb: Optional[np.ndarray] = None,
) -> None:
    """Generates a professional 4-panel visual graphic dashboard and saves to disk."""
    total_spots = tp + tn + fp + fn
    accuracy = (tp + tn) / total_spots if total_spots > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    mean_latency = float(np.mean(inference_latencies)) if inference_latencies else 0.0

    fig = plt.figure(figsize=(18, 13), facecolor="#0b1120")
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.26, left=0.07, right=0.95, top=0.865, bottom=0.075)

    # Header with spacious title and subtitle
    fig.text(
        0.50, 0.958,
        "PARQUEAME  •  AUTOMATED DETECTION ACCURACY REPORT",
        fontsize=18,
        fontweight="bold",
        color="#f8fafc",
        ha="center",
        va="center",
    )
    fig.text(
        0.50, 0.922,
        f"Camera Target: {camera_id.upper()}   |   Evaluated Frames: {total_frames}   |   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        fontsize=12,
        color="#94a3b8",
        ha="center",
        va="center",
    )

    # -------------------------------------------------------------
    # Panel 1: KPI Summary Cards (Top-Left)
    # -------------------------------------------------------------
    ax_kpi = fig.add_subplot(gs[0, 0])
    ax_kpi.set_facecolor("#1e293b")
    for spine in ax_kpi.spines.values():
        spine.set_color("#334155")
        spine.set_linewidth(1.5)
    ax_kpi.set_xticks([])
    ax_kpi.set_yticks([])
    ax_kpi.set_title("SYSTEM PERFORMANCE METRICS", fontsize=13, color="#38bdf8", pad=20, fontweight="bold")

    verdict_pass = (accuracy >= 0.70)
    verdict_color = "#10b981" if verdict_pass else "#ef4444"
    verdict_text = "PASSED" if verdict_pass else "FAILED"

    ax_kpi.text(0.08, 0.80, f"{accuracy * 100:.1f}%", fontsize=36, fontweight="bold", color=verdict_color, va="center")
    ax_kpi.text(0.08, 0.65, "OVERALL DETECTION ACCURACY", fontsize=10, fontweight="bold", color="#94a3b8", va="center")

    ax_kpi.text(
        0.72, 0.80, f"  {verdict_text}  ",
        fontsize=14, fontweight="bold", color="#ffffff", va="center", ha="center",
        bbox=dict(boxstyle="round,pad=0.5", facecolor=verdict_color, edgecolor="none", alpha=0.9),
    )
    ax_kpi.text(0.72, 0.65, "Min. Req: >= 70.0%", fontsize=10, color="#94a3b8", va="center", ha="center")

    ax_kpi.axhline(0.55, xmin=0.06, xmax=0.94, color="#334155", linewidth=1.2)

    metrics = [
        ("Precision Rate", f"{precision * 100:.1f}%", 0.08, 0.40),
        ("Recall (Sensitivity)", f"{recall * 100:.1f}%", 0.54, 0.40),
        ("F1 Harmonic Score", f"{f1 * 100:.1f}%", 0.08, 0.20),
        ("Mean YOLO Latency", f"{mean_latency:.1f} ms", 0.54, 0.20),
    ]
    for label, val, x, y in metrics:
        ax_kpi.text(x, y + 0.06, val, fontsize=16, fontweight="bold", color="#f1f5f9", va="center")
        ax_kpi.text(x, y - 0.04, label, fontsize=10, color="#94a3b8", va="center")

    ax_kpi.text(0.08, 0.06, f"Total Spots Evaluated: {total_spots}   |   Total Frames Processed: {total_frames}", fontsize=9.5, color="#64748b", va="center")

    # -------------------------------------------------------------
    # Panel 2: Confusion Matrix Heatmap (Top-Right)
    # -------------------------------------------------------------
    ax_cm = fig.add_subplot(gs[0, 1])
    ax_cm.set_facecolor("#1e293b")
    for spine in ax_cm.spines.values():
        spine.set_color("#334155")
        spine.set_linewidth(1.5)
    ax_cm.set_title("DETECTION CONFUSION MATRIX", fontsize=13, color="#38bdf8", pad=20, fontweight="bold")

    matrix = np.array([[tn, fp], [fn, tp]])
    im = ax_cm.imshow(matrix, cmap="Blues", interpolation="nearest", aspect="auto")

    ax_cm.set_xticks([0, 1])
    ax_cm.set_yticks([0, 1])
    ax_cm.set_xticklabels(["Predicted: Vacant", "Predicted: Occupied"], color="#cbd5e1", fontsize=11, fontweight="bold")
    ax_cm.set_yticklabels(["GT: Vacant", "GT: Occupied"], color="#cbd5e1", fontsize=11, fontweight="bold")
    ax_cm.tick_params(colors="#94a3b8", pad=8)
    ax_cm.set_xlabel("System Prediction", color="#94a3b8", fontsize=11, labelpad=12)
    ax_cm.set_ylabel("Ground Truth Annotation", color="#94a3b8", fontsize=11, labelpad=12)

    labels = [
        [f"TRUE NEGATIVE\n{tn} spots\n({(tn/total_spots*100) if total_spots else 0:.1f}%)",
         f"FALSE POSITIVE\n{fp} spots\n({(fp/total_spots*100) if total_spots else 0:.1f}%)"],
        [f"FALSE NEGATIVE\n{fn} spots\n({(fn/total_spots*100) if total_spots else 0:.1f}%)",
         f"TRUE POSITIVE\n{tp} spots\n({(tp/total_spots*100) if total_spots else 0:.1f}%)"],
    ]
    for i in range(2):
        for j in range(2):
            cell_color = "#10b981" if (i == j) else "#ef4444"
            ax_cm.text(j, i, labels[i][j], ha="center", va="center", color=cell_color, fontsize=11, fontweight="bold")

    # -------------------------------------------------------------
    # Panel 3: Occupancy Trend per Frame (Bottom-Left)
    # -------------------------------------------------------------
    ax_trend = fig.add_subplot(gs[1, 0])
    ax_trend.set_facecolor("#1e293b")
    for spine in ax_trend.spines.values():
        spine.set_color("#334155")
        spine.set_linewidth(1.5)
    ax_trend.set_title("GROUND TRUTH VS SYSTEM DETECTED OCCUPANCY", fontsize=13, color="#38bdf8", pad=20, fontweight="bold")

    indices = list(range(1, len(gt_occupied_counts) + 1))
    total_pts = len(indices)
    width = 0.38 if total_pts <= 30 else 0.45
    bar_gt = ax_trend.bar([i - width/2 for i in indices], gt_occupied_counts, width, label="Ground Truth", color="#38bdf8", edgecolor="#0284c7" if total_pts <= 30 else "none", linewidth=0.8)
    bar_det = ax_trend.bar([i + width/2 for i in indices], det_occupied_counts, width, label="YOLO Detected", color="#10b981", edgecolor="#059669" if total_pts <= 30 else "none", linewidth=0.8)

    ax_trend.set_xlabel("Frame Evaluation Sequence", color="#cbd5e1", fontsize=11, labelpad=12)
    ax_trend.set_ylabel("Occupied Spots Count", color="#cbd5e1", fontsize=11, labelpad=12)
    ax_trend.tick_params(colors="#cbd5e1", pad=6)

    if total_pts <= 25:
        ax_trend.set_xticks(indices)
    else:
        step = max(1, round(total_pts / 10))
        tick_indices = [1] + [i for i in indices if i % step == 0]
        if indices[-1] not in tick_indices:
            tick_indices.append(indices[-1])
        ax_trend.set_xticks(sorted(list(set(tick_indices))))

    ax_trend.set_xlim(0, total_pts + 1)
    ax_trend.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax_trend.legend(facecolor="#0f172a", edgecolor="#334155", labelcolor="#f8fafc", fontsize=10, loc="upper right")
    ax_trend.grid(True, linestyle="--", alpha=0.25, color="#94a3b8")

    # -------------------------------------------------------------
    # Panel 4: Sample Visual Detection Overlay (Bottom-Right)
    # -------------------------------------------------------------
    ax_img = fig.add_subplot(gs[1, 1])
    ax_img.set_facecolor("#1e293b")
    for spine in ax_img.spines.values():
        spine.set_color("#334155")
        spine.set_linewidth(1.5)
    ax_img.set_title("LATEST CAMERA SNAPSHOT & DETECTION OVERLAYS", fontsize=13, color="#38bdf8", pad=20, fontweight="bold")
    ax_img.axis("off")

    if sample_img_rgb is not None:
        ax_img.imshow(sample_img_rgb)
    else:
        ax_img.text(0.5, 0.5, "Visual Frame Sample\nNot Available", ha="center", va="center", color="#94a3b8", fontsize=12)

    # Save to all requested report destinations
    for p in report_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(p, format="jpeg", dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
        print(f"  [✓] Visual graphic report generated: {p.resolve()}")

    plt.close(fig)


def generate_json_report(
    report_paths: List[Path],
    camera_id: str,
    dataset_path: Path,
    image_files: List[Path],
    tp: int,
    tn: int,
    fp: int,
    fn: int,
    frame_accuracies: List[float],
    gt_occupied_counts: List[int],
    det_occupied_counts: List[int],
    inference_latencies: List[float],
    min_accuracy: float,
) -> None:
    """Generates structured JSON evaluation reports and saves to disk."""
    total_spots = tp + tn + fp + fn
    accuracy = (tp + tn) / total_spots if total_spots > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    inf_arr = np.array(inference_latencies) if inference_latencies else np.array([0.0])

    payload: Dict[str, Any] = {
        "report_type": "end_to_end_accuracy_evaluation",
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timestamp_epoch": time.time(),
        "camera_id": camera_id,
        "dataset": {
            "directory": str(dataset_path.resolve()),
            "total_frames_evaluated": len(image_files),
            "total_spots_evaluated": total_spots,
        },
        "summary": {
            "accuracy": round(accuracy, 4),
            "accuracy_percent": round(accuracy * 100, 2),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "verdict": "PASSED" if accuracy >= min_accuracy else "FAILED",
            "min_accuracy_threshold": min_accuracy,
        },
        "confusion_matrix": {
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
        },
        "latency_inference_ms": {
            "mean": round(float(np.mean(inf_arr)), 2),
            "p50": round(float(np.percentile(inf_arr, 50)), 2),
            "p90": round(float(np.percentile(inf_arr, 90)), 2),
            "p95": round(float(np.percentile(inf_arr, 95)), 2),
            "min": round(float(np.min(inf_arr)), 2),
            "max": round(float(np.max(inf_arr)), 2),
        },
        "time_series": {
            "frame_filenames": [p.name for p in image_files],
            "frame_accuracies": [round(a, 4) for a in frame_accuracies],
            "ground_truth_occupied": gt_occupied_counts,
            "detected_occupied": det_occupied_counts,
            "inference_latencies_ms": [round(lat, 2) for lat in inference_latencies],
        },
    }

    raw_json = json.dumps(payload, indent=2)
    for p in report_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(raw_json, encoding="utf-8")
        print(f"  [✓] Structured JSON report generated: {p.resolve()}")


def run_end_to_end(
    dataset_dir: str = "test-samples/cam_01",
    camera_id_override: Optional[str] = None,
    max_frames: int = 10,
    report_dest: str = "tests/reports/report.jpg",
    min_accuracy: float = 0.70,
) -> int:
    print("=" * 70)
    print("PARQUEAME END-TO-END SUITE & GROUND-TRUTH EVALUATOR (STAGE 503)")
    print("=" * 70)

    dataset_path = Path(dataset_dir)
    if not dataset_path.is_dir():
        print(f"[ERROR] Specified dataset directory does not exist: {dataset_path}")
        return 1

    # Detect camera ID
    if camera_id_override:
        camera_id = camera_id_override
    else:
        camera_id = dataset_path.name if dataset_path.name.startswith("cam_") else "cam_01"

    print(f"Target Camera ID:     {camera_id}")
    print(f"Dataset Directory:    {dataset_path.resolve()}")
    print(f"Max Frames to Test:   {max_frames if max_frames > 0 else 'All'}")

    # Gather image files
    image_files = sorted(dataset_path.glob("*.jpg"))
    if not image_files:
        image_files = sorted(dataset_path.glob("*.jpeg"))
    if not image_files:
        print(f"[ERROR] No JPEG images found in {dataset_path}")
        return 1

    if max_frames > 0:
        image_files = image_files[:max_frames]

    print(f"Loaded {len(image_files)} test frames for evaluation.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_path = Path(tmp_dir) / "test_parqueame_e2e.db"
        
        orig_db = db_mod.DEFAULT_DB_PATH
        db_mod.DEFAULT_DB_PATH = test_db_path
        repo_mod.DEFAULT_DB_PATH = test_db_path
        analytics_mod.DEFAULT_DB_PATH = test_db_path

        try:
            # ---------------------------------------------------------
            # Phase 1: Environment & Database Init
            # ---------------------------------------------------------
            print("\n[Phase 1] Initializing isolated SQLite database...")
            init_db(test_db_path)
            with get_db_connection(test_db_path) as conn:
                mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
                assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"
                fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
                assert fk == 1, "Foreign keys not active"
            print("  [✓] Database ready in WAL mode.")

            with TestClient(app) as client:
                # -----------------------------------------------------
                # Phase 2: Baseline Health Verification
                # -----------------------------------------------------
                print("\n[Phase 2] Verifying Server Baseline...")
                r_root = client.get("/")
                assert r_root.status_code == 200 and r_root.json().get("status") == "online"
                r_health = client.get("/api/v1/health")
                assert r_health.status_code == 200 and r_health.json().get("status") == "healthy"
                print("  [✓] Server root and health endpoints online.")

                # -----------------------------------------------------
                # Phase 3: Frame Ingestion & Ground-Truth Evaluation
                # -----------------------------------------------------
                print("\n[Phase 3] Ingesting Frames & Evaluating Detection Success...")
                tp = tn = fp = fn = 0
                frame_accuracies: List[float] = []
                gt_occupied_counts: List[int] = []
                det_occupied_counts: List[int] = []
                inference_latencies: List[float] = []
                last_annotated_rgb: Optional[np.ndarray] = None

                for idx, img_path in enumerate(image_files):
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()

                    xml_path = img_path.with_suffix(".xml")
                    gt_map = parse_ground_truth_xml(xml_path) if xml_path.is_file() else {}

                    battery = max(10.0, 100.0 - (idx * 0.2))
                    voltage = 3.30 + (0.90 * battery / 100.0)

                    t0 = time.time()
                    resp = client.post(
                        f"/api/v1/upload/{camera_id}?battery={battery:.1f}&voltage={voltage:.2f}",
                        files={"file": (img_path.name, img_bytes, "image/jpeg")},
                    )
                    latency_ms = (time.time() - t0) * 1000.0
                    assert resp.status_code == 200, f"Upload failed for {img_path.name}: {resp.text}"
                    up_data = resp.json()

                    inference_latencies.append(up_data.get("inference_time_ms", 0.0))
                    det_occupied_counts.append(up_data.get("occupied_spots", 0))

                    # Retrieve spot details
                    st_resp = client.get(f"/api/v1/cameras/{camera_id}/status")
                    assert st_resp.status_code == 200
                    spots_status = st_resp.json().get("spots", [])

                    # Ground-truth comparison
                    frame_tp = frame_tn = frame_fp = frame_fn = 0
                    gt_occ_for_frame = 0

                    if gt_map:
                        for sp in spots_status:
                            sp_id = sp["spot_id"]
                            det_occ = sp["occupied"]
                            gt_occ = gt_map.get(sp_id)
                            if gt_occ is None:
                                # Try numeric fallback
                                num = re.sub(r"[^0-9]", "", sp_id)
                                gt_occ = gt_map.get(num)

                            if gt_occ is not None:
                                if gt_occ:
                                    gt_occ_for_frame += 1
                                if gt_occ and det_occ:
                                    frame_tp += 1
                                elif not gt_occ and not det_occ:
                                    frame_tn += 1
                                elif not gt_occ and det_occ:
                                    frame_fp += 1
                                elif gt_occ and not det_occ:
                                    frame_fn += 1

                        tp += frame_tp
                        tn += frame_tn
                        fp += frame_fp
                        fn += frame_fn

                        f_total = frame_tp + frame_tn + frame_fp + frame_fn
                        f_acc = (frame_tp + frame_tn) / f_total if f_total > 0 else 0.0
                        frame_accuracies.append(f_acc)
                        gt_occupied_counts.append(gt_occ_for_frame)

                        print(
                            f"  Frame {idx+1}/{len(image_files)}: {img_path.name} -> "
                            f"Acc: {f_acc*100:.1f}% | Detected: {up_data['occupied_spots']} | GT: {gt_occ_for_frame} "
                            f"(Inference: {up_data['inference_time_ms']:.1f}ms)"
                        )
                    else:
                        gt_occupied_counts.append(0)
                        print(f"  Frame {idx+1}/{len(image_files)}: {img_path.name} -> (No XML Ground Truth)")

                # -----------------------------------------------------
                # Phase 4: Retrieve Visual Annotated Image
                # -----------------------------------------------------
                print("\n[Phase 4] Verifying Visual Annotated Stream...")
                img_res = client.get(f"/api/v1/cameras/{camera_id}/image")
                if img_res.status_code == 200 and len(img_res.content) > 100:
                    nparr = np.frombuffer(img_res.content, np.uint8)
                    decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if decoded is not None:
                        last_annotated_rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
                    print(f"  [✓] Rolling visual JPEG frame retrieved ({len(img_res.content)} bytes).")

                # -----------------------------------------------------
                # Phase 5: SQLite Database Persistence Check
                # -----------------------------------------------------
                print("\n[Phase 5] Verifying SQLite Persistence...")
                with get_db_connection(test_db_path) as conn:
                    saved_logs = conn.execute("SELECT COUNT(*) FROM camera_logs WHERE camera_id = ?", (camera_id,)).fetchone()[0]
                    saved_spots = conn.execute("SELECT COUNT(*) FROM spot_history WHERE camera_id = ?", (camera_id,)).fetchone()[0]
                    assert saved_logs == len(image_files), f"Expected {len(image_files)} logs, found {saved_logs}"
                    assert saved_spots > 0, "No spot history rows recorded"
                    print(f"  [✓] Verified {saved_logs} camera_logs and {saved_spots} spot_history rows.")

                # -----------------------------------------------------
                # Phase 6: Flow Analytics API Verification
                # -----------------------------------------------------
                print("\n[Phase 6] Verifying Flow Analytics Integration...")
                an_res = client.get(f"/api/v1/analytics/cameras/{camera_id}/summary")
                if an_res.status_code == 404:
                    an_res = client.get(f"/api/v1/analytics/cameras/{camera_id}")
                assert an_res.status_code == 200
                an_data = an_res.json()
                total_obs = an_data.get("total_observations")
                if total_obs is None:
                    with get_db_connection(test_db_path) as conn:
                        total_obs = conn.execute("SELECT COUNT(*) FROM camera_logs WHERE camera_id = ?", (camera_id,)).fetchone()[0]
                assert total_obs == len(image_files)
                print(f"  [✓] Analytics summary verified: {total_obs} observations recorded.")

                # -----------------------------------------------------
                # Phase 7: Generate Visual Graphic & JSON Performance Reports
                # -----------------------------------------------------
                print("\n[Phase 7] Generating Visual Graphic & JSON Performance Reports...")
                timestamp_str = time.strftime("%Y%m%d_%H%M%S")
                reports_dir = Path("tests/reports")
                reports_dir.mkdir(parents=True, exist_ok=True)

                informative_name = f"report_{camera_id}_{timestamp_str}"
                latest_name = f"report_{camera_id}_latest"
                generic_name = "report"

                jpg_dest_list = [
                    reports_dir / f"{informative_name}.jpg",
                    reports_dir / f"{latest_name}.jpg",
                    reports_dir / f"{generic_name}.jpg",
                ]

                json_dest_list = [
                    reports_dir / f"{informative_name}.json",
                    reports_dir / f"{latest_name}.json",
                    reports_dir / f"{generic_name}.json",
                ]

                if report_dest:
                    custom_dest = Path(report_dest)
                    if custom_dest.suffix.lower() == ".json":
                        if custom_dest not in json_dest_list:
                            json_dest_list.append(custom_dest)
                        companion_jpg = custom_dest.with_suffix(".jpg")
                        if companion_jpg not in jpg_dest_list:
                            jpg_dest_list.append(companion_jpg)
                    else:
                        if custom_dest not in jpg_dest_list:
                            jpg_dest_list.append(custom_dest)
                        companion_json = custom_dest.with_suffix(".json")
                        if companion_json not in json_dest_list:
                            json_dest_list.append(companion_json)

                generate_graphic_report(
                    report_paths=jpg_dest_list,
                    camera_id=camera_id,
                    total_frames=len(image_files),
                    tp=tp,
                    tn=tn,
                    fp=fp,
                    fn=fn,
                    accuracies=frame_accuracies,
                    gt_occupied_counts=gt_occupied_counts,
                    det_occupied_counts=det_occupied_counts,
                    inference_latencies=inference_latencies,
                    sample_img_rgb=last_annotated_rgb,
                )

                generate_json_report(
                    report_paths=json_dest_list,
                    camera_id=camera_id,
                    dataset_path=dataset_path,
                    image_files=image_files,
                    tp=tp,
                    tn=tn,
                    fp=fp,
                    fn=fn,
                    frame_accuracies=frame_accuracies,
                    gt_occupied_counts=gt_occupied_counts,
                    det_occupied_counts=det_occupied_counts,
                    inference_latencies=inference_latencies,
                    min_accuracy=min_accuracy,
                )

                # Overall classification score
                total_evaluated = tp + tn + fp + fn
                overall_accuracy = (tp + tn) / total_evaluated if total_evaluated > 0 else 0.0
                print("\n" + "=" * 70)
                print(f"EVALUATION SUMMARY: Accuracy: {overall_accuracy*100:.2f}% (Threshold: {min_accuracy*100:.1f}%)")
                print("=" * 70)

                if total_evaluated > 0 and overall_accuracy < min_accuracy:
                    print(f"[FAIL] Detection accuracy {overall_accuracy*100:.2f}% is below acceptable threshold {min_accuracy*100:.1f}%.")
                    return 1

                print("[SUCCESS] ALL END-TO-END AND DETECTION ACCURACY TESTS PASSED.")
                return 0

        finally:
            db_mod.DEFAULT_DB_PATH = orig_db
            repo_mod.DEFAULT_DB_PATH = orig_db
            analytics_mod.DEFAULT_DB_PATH = orig_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Parqueame End-to-End Test and Detection Accuracy Evaluator")
    parser.add_argument("-d", "--dataset-dir", type=str, default="test-samples/cam_01", help="Path to sample images directory (default: test-samples/cam_01)")
    parser.add_argument("-c", "--camera-id", type=str, default=None, help="Camera ID (default: auto-detected from folder name)")
    parser.add_argument("-m", "--max-frames", type=int, default=10, help="Max frames to test (default: 10, set 0 for all)")
    parser.add_argument("-r", "--report-path", type=str, default="tests/reports/report.jpg", help="Report output destination (default: tests/reports/report.jpg)")
    parser.add_argument("--min-accuracy", type=float, default=0.70, help="Minimum accuracy required to pass (default: 0.70)")

    args = parser.parse_args()

    code = run_end_to_end(
        dataset_dir=args.dataset_dir,
        camera_id_override=args.camera_id,
        max_frames=args.max_frames,
        report_dest=args.report_path,
        min_accuracy=args.min_accuracy,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
