"""
Sub-Spec 504: Stress & GPU VRAM Benchmark Suite for Parqueame.
Executes sustained image ingestion cycles against the FastAPI application and
YOLOv8 detection engine, measuring GPU VRAM memory stability, multi-threaded
SQLite WAL concurrency, latency percentiles, and throughput (FPS).
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage.analytics as analytics_mod
import storage.database as db_mod
import storage.repository as repo_mod
from server.main import app
from simulation.scenarios import ScenarioOrchestrator
from storage.database import get_db_connection, init_db

# Suppress verbose HTTP access logs during high-volume benchmarks
logging.basicConfig(level=logging.WARNING)
logging.getLogger("parqueame").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def measure_gpu_memory_mb() -> Tuple[float, float]:
    """Returns (currently_allocated_mb, max_allocated_mb)."""
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / (1024 * 1024)
        peak = torch.cuda.max_memory_allocated() / (1024 * 1024)
        return round(float(allocated), 2), round(float(peak), 2)
    return 0.0, 0.0


def run_benchmark(
    total_frames: int = 50,
    warmup_frames: int = 5,
    camera_id: str = "cam_01",
    concurrency: int = 1,
    scenario_name: str = "sequential",
    report_path: str = "tests/output/stress_benchmark_report.json",
    max_vram_leak_mb: float = 25.0,
) -> int:
    """
    Executes the sustained stress and VRAM benchmark suite.
    Returns 0 if all tests pass, 1 if any failure or memory leak is detected.
    """
    print("=" * 70)
    print("PARQUEAME STRESS & VRAM BENCHMARK SUITE (STAGE 504)")
    print("=" * 70)

    # 1. Hardware Inspection
    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (Fallback)"
    print(f"Hardware Compute Device: {device_name}")
    print(
        f"Benchmark Config: {total_frames} frames, {concurrency} worker(s), "
        f"camera '{camera_id}', scenario '{scenario_name}'"
    )

    # 2. Gather Test Images
    orchestrator = ScenarioOrchestrator(samples_dir="test-samples")
    image_paths = orchestrator.get_camera_images(camera_id, scenario=scenario_name)
    if not image_paths:
        print(f"[ERROR] No sample images found for camera '{camera_id}'.")
        return 1

    print(f"Loaded {len(image_paths)} distinct frames from scenario '{scenario_name}'.")

    # Pre-cache images in memory to eliminate disk I/O bottlenecks
    cached_images: List[Tuple[str, bytes]] = []
    for p in image_paths:
        with open(p, "rb") as f:
            cached_images.append((p.name, f.read()))

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_path = Path(tmp_dir) / "benchmark_temp.db"

        # Monkeypatch DB paths to ensure complete isolation
        orig_db = db_mod.DEFAULT_DB_PATH
        orig_repo_db = repo_mod.DEFAULT_DB_PATH
        orig_analytics_db = analytics_mod.DEFAULT_DB_PATH

        db_mod.DEFAULT_DB_PATH = test_db_path
        repo_mod.DEFAULT_DB_PATH = test_db_path
        analytics_mod.DEFAULT_DB_PATH = test_db_path

        try:
            init_db(test_db_path)

            with TestClient(app) as client:
                # -------------------------------------------------------------
                # Step 1: Warm-Up Phase
                # -------------------------------------------------------------
                print(f"\n[Step 1] Running {warmup_frames} warm-up iterations...")
                for i in range(warmup_frames):
                    fname, fbytes = cached_images[i % len(cached_images)]
                    res = client.post(
                        f"/api/v1/upload/{camera_id}?battery=100.0&voltage=4.20",
                        files={"file": (fname, fbytes, "image/jpeg")},
                    )
                    assert res.status_code == 200, f"Warmup request {i} failed: {res.text}"

                if cuda_available:
                    torch.cuda.reset_peak_memory_stats()
                warmup_vram, _ = measure_gpu_memory_mb()
                print(f"  [✓] Warm-up complete. Baseline VRAM: {warmup_vram:.2f} MB")

                # -------------------------------------------------------------
                # Step 2: High-Load Execution Phase
                # -------------------------------------------------------------
                print(f"\n[Step 2] Executing {total_frames} stress frames (concurrency={concurrency})...")
                turnaround_latencies: List[float] = []
                inference_latencies: List[float] = []
                failed_requests = 0

                def worker_task(idx: int) -> Optional[Tuple[float, float]]:
                    fname, fbytes = cached_images[idx % len(cached_images)]
                    battery_val = max(10.0, 100.0 - (idx * 0.1))
                    t0 = time.time()
                    try:
                        resp = client.post(
                            f"/api/v1/upload/{camera_id}?battery={battery_val:.1f}&voltage=3.90",
                            files={"file": (fname, fbytes, "image/jpeg")},
                        )
                        t_latency = (time.time() - t0) * 1000.0
                        if resp.status_code == 200:
                            data = resp.json()
                            inf_time = data.get("inference_time_ms", 0.0)
                            return t_latency, inf_time
                        return None
                    except Exception:
                        return None

                benchmark_start = time.time()

                if concurrency <= 1:
                    for i in range(total_frames):
                        res = worker_task(i)
                        if res is not None:
                            turnaround_latencies.append(res[0])
                            inference_latencies.append(res[1])
                        else:
                            failed_requests += 1
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                        futures = [executor.submit(worker_task, i) for i in range(total_frames)]
                        for fut in concurrent.futures.as_completed(futures):
                            res = fut.result()
                            if res is not None:
                                turnaround_latencies.append(res[0])
                                inference_latencies.append(res[1])
                            else:
                                failed_requests += 1

                total_time = time.time() - benchmark_start
                successful_frames = len(turnaround_latencies)
                fps = successful_frames / total_time if total_time > 0 else 0.0

                # -------------------------------------------------------------
                # Step 3: VRAM Audit & Statistical Aggregation
                # -------------------------------------------------------------
                print("\n[Step 3] Analyzing Metrics & VRAM Stability...")
                final_vram, peak_vram = measure_gpu_memory_mb()
                vram_delta = round(final_vram - warmup_vram, 2)
                leak_detected = (vram_delta > max_vram_leak_mb) if cuda_available else False

                t_arr = np.array(turnaround_latencies) if turnaround_latencies else np.array([0.0])
                inf_arr = np.array(inference_latencies) if inference_latencies else np.array([0.0])

                p50 = float(np.percentile(t_arr, 50))
                p90 = float(np.percentile(t_arr, 90))
                p95 = float(np.percentile(t_arr, 95))
                min_lat = float(np.min(t_arr))
                max_lat = float(np.max(t_arr))
                mean_lat = float(np.mean(t_arr))

                # Database check
                with get_db_connection(test_db_path) as conn:
                    saved_logs_count = conn.execute("SELECT COUNT(*) FROM camera_logs").fetchone()[0]

                # -------------------------------------------------------------
                # Step 4: Display Summary Results
                # -------------------------------------------------------------
                print("\n" + "-" * 70)
                print(f"Total Processed Frames: {successful_frames}/{total_frames} (Failed: {failed_requests})")
                print(f"Total Test Duration:    {total_time:.2f} seconds")
                print(f"Overall Throughput:     {fps:.2f} FPS")
                print("-" * 70)
                print(
                    f"Turnaround Latency:     Min: {min_lat:.1f}ms | Mean: {mean_lat:.1f}ms | "
                    f"p50: {p50:.1f}ms | p90: {p90:.1f}ms | p95: {p95:.1f}ms | Max: {max_lat:.1f}ms"
                )
                print(
                    f"YOLO Inference Latency: Mean: {np.mean(inf_arr):.1f}ms | "
                    f"p50: {np.percentile(inf_arr, 50):.1f}ms | p95: {np.percentile(inf_arr, 95):.1f}ms"
                )
                print("-" * 70)
                print(f"VRAM Baseline (Warmup): {warmup_vram:.2f} MB")
                print(f"VRAM Final:             {final_vram:.2f} MB")
                print(f"VRAM Peak:              {peak_vram:.2f} MB")
                print(f"VRAM Delta:             {vram_delta:+.2f} MB (Threshold: <= {max_vram_leak_mb:.1f} MB)")
                print(f"Database Writes:        {saved_logs_count} log entries verified in SQLite.")
                print("-" * 70)

                # Step 5: Save JSON Report
                report_file = Path(report_path)
                report_file.parent.mkdir(parents=True, exist_ok=True)

                report_payload: Dict[str, Any] = {
                    "timestamp": time.time(),
                    "hardware": {
                        "cuda_available": cuda_available,
                        "device_name": device_name,
                    },
                    "config": {
                        "total_frames": total_frames,
                        "warmup_frames": warmup_frames,
                        "concurrency": concurrency,
                        "camera_id": camera_id,
                        "scenario": scenario_name,
                    },
                    "performance": {
                        "total_time_seconds": round(total_time, 2),
                        "successful_frames": successful_frames,
                        "failed_frames": failed_requests,
                        "fps": round(fps, 2),
                        "latency_turnaround_ms": {
                            "min": round(min_lat, 2),
                            "mean": round(mean_lat, 2),
                            "p50": round(p50, 2),
                            "p90": round(p90, 2),
                            "p95": round(p95, 2),
                            "max": round(max_lat, 2),
                        },
                        "latency_inference_ms": {
                            "mean": round(float(np.mean(inf_arr)), 2),
                            "p50": round(float(np.percentile(inf_arr, 50)), 2),
                            "p95": round(float(np.percentile(inf_arr, 95)), 2),
                        },
                    },
                    "memory": {
                        "vram_warmup_mb": warmup_vram,
                        "vram_final_mb": final_vram,
                        "vram_peak_mb": peak_vram,
                        "vram_delta_mb": vram_delta,
                        "leak_detected": leak_detected,
                    },
                    "database_records_committed": saved_logs_count,
                    "passed": (failed_requests == 0) and (not leak_detected),
                }

                report_file.write_text(json.dumps(report_payload, indent=2))
                print(f"Benchmark report saved to: {report_file.resolve()}")

                if leak_detected:
                    print("\n[FAIL] GPU VRAM MEMORY LEAK DETECTED!")
                    return 1

                if failed_requests > 0:
                    print(f"\n[FAIL] {failed_requests} requests failed during stress test!")
                    return 1

                print("\n[SUCCESS] ALL BENCHMARK & MEMORY LEAK CHECKS PASSED.")
                return 0

        finally:
            db_mod.DEFAULT_DB_PATH = orig_db
            repo_mod.DEFAULT_DB_PATH = orig_repo_db
            analytics_mod.DEFAULT_DB_PATH = orig_analytics_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Parqueame Stress & VRAM Benchmark")
    parser.add_argument("--frames", type=int, default=50, help="Total frames to benchmark (default: 50)")
    parser.add_argument("--warmup", type=int, default=5, help="Warm-up frames (default: 5)")
    parser.add_argument("--camera-id", type=str, default="cam_01", help="Camera ID to test (default: cam_01)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent worker threads (default: 1)")
    parser.add_argument("--scenario", type=str, default="sequential", help="Scenario name (default: sequential)")
    parser.add_argument(
        "--report",
        type=str,
        default="tests/output/stress_benchmark_report.json",
        help="Path to JSON report output (default: tests/output/stress_benchmark_report.json)",
    )
    parser.add_argument(
        "--max-vram-leak-mb",
        type=float,
        default=25.0,
        help="Max allowable VRAM leak in MB (default: 25.0)",
    )

    args = parser.parse_args()

    exit_code = run_benchmark(
        total_frames=args.frames,
        warmup_frames=args.warmup,
        camera_id=args.camera_id,
        concurrency=args.concurrency,
        scenario_name=args.scenario,
        report_path=args.report,
        max_vram_leak_mb=args.max_vram_leak_mb,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
