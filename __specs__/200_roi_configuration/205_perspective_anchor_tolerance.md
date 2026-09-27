# Sub-Spec 205: Perspective Anchor Tolerance & Dual Geometric Occupancy Evaluation

## 1. Objective and Deliverable
You are tasked with enhancing the spatial occupancy engine (`detection/occupancy.py`) to handle perspective foreshortening and vehicle bumper overhangs on angled camera views.
On real-world CCTV cameras mounted at elevated oblique angles, vehicle front bumpers and chassis physically overhang past asphalt stall lines, causing the ground-tire anchor point to occasionally land just outside tight stall polygons even when the vehicle is genuinely parked.

This sub-spec introduces dual-point spatial evaluation (Ground Anchor + Bounding Box Center) and a configurable boundary proximity tolerance (`boundary_tolerance_px`), boosting occupancy evaluation recall while maintaining high precision.

**Target Files to Modify:**
- `/home/thegxnster/parqueame/detection/occupancy.py`
- `/home/thegxnster/parqueame/detection/__init__.py`

---

## 2. Strict Technical Constraints and Rules
- **No Diagram Rule:** This sub-spec contains zero diagrams per project constraints.
- **Backward Compatibility:**
  Existing exported functions (`calculate_ground_anchor`, `is_point_in_polygon`, `evaluate_occupancy`) must retain identical signatures and return types.
- **Dual-Point Evaluation Logic:**
  A detection is determined to occupy a spot polygon if ANY of the following geometric conditions are met:
  1. **Primary (Ground Anchor):** The tire ground-contact anchor `(cx, y2 - 0.05h)` is inside or on the boundary of the polygon (`cv2.pointPolygonTest >= 0`).
  2. **Secondary (Center Fallback):** The bounding box 2D center `((x1 + x2)/2, (y1 + y2)/2)` is inside or on the boundary of the polygon (`cv2.pointPolygonTest >= 0`).
  3. **Tertiary (Boundary Tolerance):** The ground anchor is within `boundary_tolerance_px` of the spot perimeter (`cv2.pointPolygonTest(measureDist=True) >= -boundary_tolerance_px`).
- **Configurable Parameter:**
  `evaluate_occupancy()` must accept an optional `boundary_tolerance_px: float = 10.0` parameter.

---

## 3. Mathematical Formulation

Given a vehicle bounding box $B = (x_1, y_1, x_2, y_2)$ and a spot polygon contour $P$:

1. **Center Point:**
   $$C = \left(\frac{x_1 + x_2}{2}, \frac{y_1 + y_2}{2}\right)$$

2. **Ground Contact Anchor:**
   $$A = \left(\frac{x_1 + x_2}{2}, y_2 - 0.05 \cdot (y_2 - y_1)\right)$$

3. **Inclusion Function:**
   $$\text{occupied}(B, P) = \left[\text{dist}(P, A) \ge -\tau\right] \lor \left[\text{dist}(P, C) \ge 0\right]$$
   where $\text{dist}(P, pt)$ is the signed distance from $pt$ to contour $P$ computed via `cv2.pointPolygonTest(P, pt, True)`, and $\tau = \text{boundary\_tolerance\_px} \ge 0$.

---

## 4. Implementation Requirements in `detection/occupancy.py`

1. Define `calculate_box_center(box: Tuple[float, float, float, float]) -> Tuple[float, float]`:
   Computes geometric 2D center `((x1 + x2) / 2.0, (y1 + y2) / 2.0)`.

2. Define `is_vehicle_in_spot(box: Tuple[float, float, float, float], polygon_contour: np.ndarray, boundary_tolerance_px: float = 10.0) -> Tuple[bool, Tuple[float, float]]`:
   Evaluates anchor, center, and tolerance rules, returning `(is_inside, anchor)`.

3. Update `evaluate_occupancy`:
   Signature:
   ```python
   def evaluate_occupancy(
       spots: List[Dict[str, Any]],
       detections: List[Any],
       camera_id: str,
       inference_time_ms: float = 0.0,
       timestamp: Optional[float] = None,
       boundary_tolerance_px: float = 10.0,
   ) -> OccupancyResponse:
   ```
   Uses `is_vehicle_in_spot` for matching detections to spots.

---

## 5. Verification Gate
1. Regression tests (`tests/test_detection.py` and `tests/test_roi_config.py`) must pass 100%.
2. Full dataset benchmark (`test-samples/cam_01`, 107 frames, 28 spots) must achieve $\ge 93\%$ spot-level accuracy.

---

## 6. Benchmark Results (Post Sub-Spec 205 + 206)

### False Negative Root Cause Analysis (166 FN at conf 0.35)

| Category | Count | Fixable? |
|----------|-------|----------|
| YOLO cannot detect the car at all (even at conf 0.20) — distant/tiny vehicles | 106 | Requires bigger model or image tiling |
| Car IS detected by YOLO but below the 0.35 confidence threshold | 60 | ✅ Fixed by lowering threshold (Sub-Spec 206) |
| Spatial matching missed (geometry issues) | 0 | ✅ Already fixed by this sub-spec |

### Confidence Threshold Sweep (107 frames × 28 spots = 2,996 evaluations)

| Threshold | Accuracy | Precision | Recall | F1     | FP  |
|-----------|----------|-----------|--------|--------|-----|
| 0.35      | 93.36%   | 90.43%    | 65.27% | 75.82% | 33  |
| 0.30      | 93.62%   | 89.53%    | 67.99% | 77.29% | 38  |
| **0.25**  | **94.09%** | **88.69%** | **72.18%** | **79.58%** | **44** |
| 0.20      | 94.63%   | 87.12%    | 77.82% | 82.21% | 55  |
| 0.15      | 95.26%   | 86.68%    | 83.05% | 84.83% | 61  |

**Selected threshold: 0.25** (best accuracy/precision balance with significant recall gain).

### Combined Improvement (Sub-Spec 205 + 206)

| Metric    | Before (205 + 206) | After  | Delta   |
|-----------|--------------------|--------|---------|
| Accuracy  | 93.36%             | 94.09% | +0.73%  |
| Precision | 90.43%             | 88.69% | −1.74%  |
| Recall    | 65.27%             | 72.18% | +6.91%  |
| F1        | 75.82%             | 79.58% | +3.76%  |

---

## 7. Future Improvement: Larger YOLO Model Support

The remaining **106 unrecoverable false negatives** are cars too small or distant for YOLOv8n to detect at any confidence level. These are concentrated in the far rows of the parking lot (spots 17–28), where vehicles appear at ~40–60px resolution.

### Option A: Swap to a Larger YOLO Model
The `VehicleDetector` in `detection/detector.py` already accepts a `model_name` parameter, making model swapping trivial:

```python
# Current (nano — fastest, lowest accuracy)
detector = VehicleDetector(model_name="yolov8n.pt")

# Medium (recommended upgrade — better small-object detection)
detector = VehicleDetector(model_name="yolov8m.pt")

# Large (highest accuracy, ~4× slower inference)
detector = VehicleDetector(model_name="yolov8l.pt")
```

| Model     | Params | COCO mAP50-95 | Est. Inference (RTX 4050) | VRAM   |
|-----------|--------|---------------|---------------------------|--------|
| YOLOv8n   | 3.2M   | 37.3          | ~25ms                     | ~1 GB  |
| YOLOv8s   | 11.2M  | 44.9          | ~35ms                     | ~2 GB  |
| YOLOv8m   | 25.9M  | 50.2          | ~60ms                     | ~3 GB  |
| YOLOv8l   | 43.7M  | 52.9          | ~100ms                    | ~5 GB  |

**Recommendation:** YOLOv8m offers the best tradeoff for our RTX 4050 (6GB VRAM). It should recover a significant portion of the 106 missed small vehicles while keeping inference under 100ms — well within our 30-second capture interval.

### Option B: Image Tiling (SAHI-Style)
Run detection on overlapping crops of the image at higher resolution, then merge results. This boosts small-object detection without changing the model but increases inference time proportionally to the number of tiles. Libraries like [SAHI](https://github.com/obss/sahi) integrate directly with Ultralytics YOLO.

### Option C: Per-Camera Model Configuration
Add an optional `model_name` field to the camera config schema (`config/cameras/cam_XX.json`) so each camera can use a different YOLO variant based on its viewing angle and distance:

```json
{
  "camera_id": "cam_01",
  "model_name": "yolov8m.pt",
  "resolution": { "width": 1280, "height": 720 },
  "spots": [ ... ]
}
```

These options can be implemented independently in a future sub-spec without modifying the core occupancy engine.

