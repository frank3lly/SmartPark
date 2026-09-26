from detection.detector import VehicleDetector, VehicleDetection
from detection.occupancy import (
    SpotResult,
    OccupancyResponse,
    calculate_ground_anchor,
    normalize_spot_polygon,
    is_point_in_polygon,
    evaluate_occupancy,
)
from detection.visualizer import draw_detection_overlay

__all__ = [
    "VehicleDetector",
    "VehicleDetection",
    "SpotResult",
    "OccupancyResponse",
    "calculate_ground_anchor",
    "normalize_spot_polygon",
    "is_point_in_polygon",
    "evaluate_occupancy",
    "draw_detection_overlay",
]
