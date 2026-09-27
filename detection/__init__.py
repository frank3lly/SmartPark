from detection.detector import VehicleDetector, VehicleDetection
from detection.occupancy import (
    SpotResult,
    OccupancyResponse,
    calculate_ground_anchor,
    calculate_box_center,
    normalize_spot_polygon,
    is_point_in_polygon,
    is_vehicle_in_spot,
    evaluate_occupancy,
)
from detection.visualizer import draw_detection_overlay
from detection.config_loader import (
    SpotConfig,
    CameraConfig,
    load_camera_config,
    load_camera_config_by_id,
    list_available_cameras,
)

__all__ = [
    "VehicleDetector",
    "VehicleDetection",
    "SpotResult",
    "OccupancyResponse",
    "calculate_ground_anchor",
    "calculate_box_center",
    "normalize_spot_polygon",
    "is_point_in_polygon",
    "is_vehicle_in_spot",
    "evaluate_occupancy",
    "draw_detection_overlay",
    "SpotConfig",
    "CameraConfig",
    "load_camera_config",
    "load_camera_config_by_id",
    "list_available_cameras",
]
