# Parqueame Test & Simulation Suite (`tests/` & `simulation/`)

Harness to evaluate end-to-end detection accuracy against PKLot ground truth, benchmark GPU VRAM leak stability under sustained concurrency, and simulate multi-camera hardware uploads.

---

## Command Examples

### 1. Run End-to-End Evaluation on Camera 01 (Default 10 Frames)
Ingests 10 sample frames into an isolated database, compares YOLO detections against PKLot XML ground truth, and outputs a visual dashboard to `test/reports/`:
```bash
.venv/bin/python tests/test_end_to_end.py -d test-samples/cam_01
```

### 2. Run Full Dataset Evaluation on Camera 01 (All 107 Frames)
Evaluates all 107 images in `test-samples/cam_01` across all 28 spots (2,996 spot evaluations):
```bash
.venv/bin/python tests/test_end_to_end.py -d test-samples/cam_01 -m 0
```

### 3. Run End-to-End Evaluation on Camera 02
Evaluates detection accuracy for Camera 02 (40 spots):
```bash
.venv/bin/python tests/test_end_to_end.py -d test-samples/cam_02 -m 10
```

### 4. Run End-to-End Evaluation on Camera 03 (100 Spots)
Evaluates detection accuracy for Camera 03 against a dense 100-spot configuration:
```bash
.venv/bin/python tests/test_end_to_end.py -d test-samples/cam_03 -m 10
```

### 5. Custom Accuracy Threshold and Report Destination
Overrides minimum required accuracy threshold and custom output report path:
```bash
.venv/bin/python tests/test_end_to_end.py -d test-samples/cam_01 -m 20 --min-accuracy 0.85 -r test/reports/cam01_custom.jpg
```

### 6. Rapid Smoke Test for GPU VRAM & Stress Benchmark
Runs 10 frames with 2 warmup frames to quickly verify CUDA VRAM tracking and latency stats:
```bash
.venv/bin/python tests/test_stress_benchmark.py --frames 10 --warmup 2
```

### 7. Standard 50-Frame Stress & VRAM Benchmark
Runs 50 sequential frames with baseline warmup, auditing GPU VRAM leak threshold ($\Delta \le 25\text{ MB}$), latency percentiles (min, mean, p50, p90, p95, max), and writing JSON report to `tests/output/`:
```bash
.venv/bin/python tests/test_stress_benchmark.py --frames 50
```

### 8. High-Concurrency Multi-Threaded Stress Test (4 Workers)
Dispatches 40 frames concurrently across 4 worker threads to stress-test SQLite WAL mode concurrency without table-lock collisions:
```bash
.venv/bin/python tests/test_stress_benchmark.py --frames 40 --concurrency 4
```

### 9. Stress Benchmark with Custom Scenario
Runs stress testing using the `turnover_stress` scenario (alternating frames to maximize occupancy transitions):
```bash
.venv/bin/python tests/test_stress_benchmark.py --frames 50 --scenario turnover_stress
```

### 10. Multi-Camera Hardware Simulator (Real-Time 30s Interval)
Simulates concurrent camera devices (`cam_01`, `cam_02`, `cam_03`, `cam_04`) posting photos and battery telemetry to a live server:
```bash
.venv/bin/python simulation/simulate_cameras.py --server-url http://localhost:8000 --interval 30.0 --loop
```

### 11. Multi-Camera Hardware Simulator (Rapid Test / Fast 2s Interval)
Runs fast camera simulation for quick verification:
```bash
.venv/bin/python simulation/simulate_cameras.py --server-url http://localhost:8000 --interval 2.0 --max-frames 5
```

### 12. Dataset & Scenario Discovery Diagnostic Test
Inspects available camera datasets and validates PKLot XML ground-truth pairings:
```bash
.venv/bin/python -c "from simulation.scenarios import ScenarioOrchestrator; orch = ScenarioOrchestrator(); print(orch.validate_camera_datasets())"
```

### 13. Central Server API Test Suite (Stage 300)
Runs full server ingestion, live stream image endpoints, and error handling verification:
```bash
.venv/bin/python tests/test_server_api.py
```

### 14. Storage & Flow Analytics Test Suite (Stage 400)
Runs SQLite schema, timeline aggregation, turnovers, and analytics route verification:
```bash
.venv/bin/python tests/test_storage_analytics.py
```
