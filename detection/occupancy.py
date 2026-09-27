import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np


@dataclass(frozen=True)
class SpotResult:
    spot_id: str
    occupied: bool
    confidence: float
    matched_vehicle_class: Optional[str] = None
    matched_vehicle_box: Optional[Tuple[float, float, float, float]] = None
    anchor_point: Optional[Tuple[float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spot_id": self.spot_id,
            "occupied": self.occupied,
            "confidence": round(self.confidence, 4),
        }

    def to_detailed_dict(self) -> Dict[str, Any]:
        return {
            "spot_id": self.spot_id,
            "occupied": self.occupied,
            "confidence": round(self.confidence, 4),
            "matched_vehicle_class": self.matched_vehicle_class,
            "matched_vehicle_box": (
                [round(c, 2) for c in self.matched_vehicle_box]
                if self.matched_vehicle_box
                else None
            ),
            "anchor_point": (
                [round(c, 2) for c in self.anchor_point]
                if self.anchor_point
                else None
            ),
        }


@dataclass
class OccupancyResponse:
    camera_id: str
    timestamp: float
    inference_time_ms: float
    spots: List[SpotResult] = field(default_factory=list)

    @property
    def total_spots(self) -> int:
        return len(self.spots)

    @property
    def occupied_count(self) -> int:
        return sum(1 for s in self.spots if s.occupied)

    @property
    def free_count(self) -> int:
        return sum(1 for s in self.spots if not s.occupied)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "timestamp": round(self.timestamp, 3),
            "inference_time_ms": round(self.inference_time_ms, 2),
            "spots": [s.to_dict() for s in self.spots],
        }


def normalize_spot_polygon(raw_geometry: Union[Sequence, np.ndarray]) -> np.ndarray:
    if isinstance(raw_geometry, np.ndarray):
        if len(raw_geometry) < 3:
            raise ValueError(f"Spot polygon must have at least 3 points, got {len(raw_geometry)}")
        if raw_geometry.ndim == 2 and raw_geometry.shape[1] == 2:
            return raw_geometry.astype(np.int32).reshape((-1, 1, 2))
        return raw_geometry.astype(np.int32)

    if len(raw_geometry) == 4 and not isinstance(raw_geometry[0], (list, tuple, np.ndarray)):
        x1, y1, x2, y2 = raw_geometry
        points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    else:
        points = list(raw_geometry)

    if len(points) < 3:
        raise ValueError(f"Spot polygon must have at least 3 points, got {len(points)}")

    return np.array(points, dtype=np.int32).reshape((-1, 1, 2))


def calculate_ground_anchor(
    box: Tuple[float, float, float, float],
    vertical_offset_ratio: float = 0.05,
) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    h = y2 - y1
    anchor_y = y2 - (vertical_offset_ratio * h)
    return float(cx), float(anchor_y)


def calculate_box_center(
    box: Tuple[float, float, float, float],
) -> Tuple[float, float]:
    """Calculates the 2D geometric center (cx, cy) of a bounding box."""
    x1, y1, x2, y2 = box
    return float((x1 + x2) / 2.0), float((y1 + y2) / 2.0)


def is_point_in_polygon(point: Tuple[float, float], polygon_contour: np.ndarray) -> bool:
    dist = cv2.pointPolygonTest(
        polygon_contour,
        (float(point[0]), float(point[1])),
        measureDist=False,
    )
    return dist >= 0


def is_vehicle_in_spot(
    box: Tuple[float, float, float, float],
    polygon_contour: np.ndarray,
    boundary_tolerance_px: float = 10.0,
) -> Tuple[bool, Tuple[float, float]]:
    """Evaluates whether a vehicle bounding box occupies a spot polygon contour.

    Handles perspective distortions and bumper overhangs:
    1. Primary: Tire ground-contact anchor inside or on polygon boundary.
    2. Secondary: Bounding box center inside polygon boundary.
    3. Tertiary: Ground anchor within boundary_tolerance_px distance of polygon perimeter.

    Returns:
        (is_inside: bool, representative_anchor_point: Tuple[float, float])
    """
    anchor = calculate_ground_anchor(box)
    center = calculate_box_center(box)

    # 1. Primary: Tire ground anchor strictly inside or on boundary
    if cv2.pointPolygonTest(polygon_contour, (anchor[0], anchor[1]), False) >= 0:
        return True, anchor

    # 2. Secondary: Bounding box center inside polygon (handles perspective bumper overhang)
    if cv2.pointPolygonTest(polygon_contour, (center[0], center[1]), False) >= 0:
        return True, anchor

    # 3. Tertiary: Tire anchor within boundary tolerance
    if boundary_tolerance_px > 0.0:
        dist = cv2.pointPolygonTest(polygon_contour, (anchor[0], anchor[1]), True)
        if dist >= -boundary_tolerance_px:
            return True, anchor

    return False, anchor


def evaluate_occupancy(
    spots: List[Dict[str, Any]],
    detections: List[Any],
    camera_id: str,
    inference_time_ms: float = 0.0,
    timestamp: Optional[float] = None,
    boundary_tolerance_px: float = 10.0,
) -> OccupancyResponse:
    ts = timestamp if timestamp is not None else time.time()

    if not spots:
        return OccupancyResponse(
            camera_id=camera_id,
            timestamp=ts,
            inference_time_ms=inference_time_ms,
            spots=[],
        )

    # Pre-extract boxes and anchors for all vehicle detections
    processed_detections: List[Tuple[Any, Tuple[float, float, float, float], Tuple[float, float]]] = []
    for det in detections:
        box = getattr(det, "box", None)
        if box is None and isinstance(det, dict):
            box = det.get("box")
        if box is not None:
            box_tuple = tuple(box)
            anchor = calculate_ground_anchor(box_tuple)
            processed_detections.append((det, box_tuple, anchor))

    results_list: List[SpotResult] = []

    for spot_dict in spots:
        spot_id = spot_dict.get("id")
        if spot_id is None:
            spot_id = spot_dict.get("spot_id")
        if spot_id is None:
            spot_id = f"spot_{len(results_list) + 1}"
        spot_id = str(spot_id)

        raw_poly = (
            spot_dict.get("polygon")
            or spot_dict.get("roi")
            or spot_dict.get("box")
        )
        if raw_poly is None:
            raise ValueError(f"Spot '{spot_id}' is missing geometry definition ('polygon', 'roi', or 'box')")

        contour = normalize_spot_polygon(raw_poly)

        is_occupied = False
        best_conf = 0.0
        best_det: Optional[Any] = None
        best_anchor: Optional[Tuple[float, float]] = None

        for det, box_t, default_anchor in processed_detections:
            in_spot, rep_anchor = is_vehicle_in_spot(
                box=box_t,
                polygon_contour=contour,
                boundary_tolerance_px=boundary_tolerance_px,
            )
            if in_spot:
                is_occupied = True
                conf = getattr(det, "confidence", 0.0)
                if isinstance(det, dict):
                    conf = det.get("confidence", 0.0)

                if conf >= best_conf:
                    best_conf = float(conf)
                    best_det = det
                    best_anchor = rep_anchor

        matched_class = None
        matched_box = None
        if best_det is not None:
            matched_class = getattr(best_det, "class_name", None) or (
                best_det.get("class_name") if isinstance(best_det, dict) else None
            )
            raw_box = getattr(best_det, "box", None) or (
                best_det.get("box") if isinstance(best_det, dict) else None
            )
            matched_box = tuple(raw_box) if raw_box else None

        results_list.append(
            SpotResult(
                spot_id=spot_id,
                occupied=is_occupied,
                confidence=round(best_conf, 4) if is_occupied else 0.0,
                matched_vehicle_class=matched_class,
                matched_vehicle_box=matched_box,
                anchor_point=best_anchor,
            )
        )

    return OccupancyResponse(
        camera_id=camera_id,
        timestamp=ts,
        inference_time_ms=inference_time_ms,
        spots=results_list,
    )
