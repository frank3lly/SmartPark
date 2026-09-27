# Sub-Spec 206: Confidence Threshold Tuning

## Objective
Optimize the YOLO confidence threshold to improve recall on distant/small vehicles
without significantly degrading precision.

## Root Cause Analysis

False negative breakdown (166 total FN at threshold 0.35):
- **106 FN**: YOLO cannot detect the car at all (even at conf 0.20) — distant/tiny vehicles
- **60 FN**: Car IS detected by YOLO but below the 0.35 threshold — recoverable
- **0 FN**: Spatial matching missed — no geometry issues (fixed in Sub-Spec 205)

## Threshold Sweep Results (107 frames × 28 spots)

| Threshold | Accuracy | Precision | Recall | F1     | FP  |
|-----------|----------|-----------|--------|--------|-----|
| 0.35      | 93.36%   | 90.43%    | 65.27% | 75.82% | 33  |
| 0.30      | 93.62%   | 89.53%    | 67.99% | 77.29% | 38  |
| **0.25**  | **94.09%** | **88.69%** | **72.18%** | **79.58%** | **44** |
| 0.20      | 94.63%   | 87.12%    | 77.82% | 82.21% | 55  |
| 0.15      | 95.26%   | 86.68%    | 83.05% | 84.83% | 61  |

## Decision
Selected **0.25** as the new default:
- Accuracy ↑ 0.73% (93.36 → 94.09)
- Recall ↑ 6.91% (65.27 → 72.18)
- F1 ↑ 3.76% (75.82 → 79.58)
- Precision ↓ 1.74% (90.43 → 88.69) — acceptable tradeoff
- Only +11 additional false positives across all 2,996 evaluations

## Changes
- `detection/detector.py`: Default `conf_threshold` parameter changed from `0.35` to `0.25`

## Regression
- `tests/test_detection.py` — PASSED
- `tests/test_roi_config.py` — PASSED
