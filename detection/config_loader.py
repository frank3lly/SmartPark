import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class SpotConfig(BaseModel):
    """Schema and validation for an individual parking spot."""

    id: str = Field(..., min_length=1, description="Unique identifier for the parking spot")
    polygon: List[List[int]] = Field(..., description="Ordered 4-corner polygon coordinates [[x, y], ...]")

    @field_validator("polygon")
    @classmethod
    def validate_polygon_structure(cls, v: List[List[int]]) -> List[List[int]]:
        if len(v) != 4:
            raise ValueError(f"Spot polygon must have exactly 4 vertices, received {len(v)}")
        for i, pt in enumerate(v):
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValueError(f"Vertex {i} must be a 2-element [x, y] coordinate pair, got {pt}")
            x, y = pt
            if not isinstance(x, int) or not isinstance(y, int) or isinstance(x, bool) or isinstance(y, bool):
                raise ValueError(f"Vertex {i} coordinates must be integers, got [{type(x).__name__}, {type(y).__name__}]")
        return v

    def to_contour(self) -> np.ndarray:
        """Converts polygon vertices into an OpenCV integer contour array (4, 1, 2)."""
        return np.array(self.polygon, dtype=np.int32).reshape((-1, 1, 2))

    def compute_area(self) -> float:
        """Computes the polygon area in square pixels using Green's theorem via OpenCV."""
        return float(cv2.contourArea(self.to_contour()))


class CameraConfig(BaseModel):
    """Schema and validation for a camera's monitored parking layout."""

    camera_id: str = Field(..., min_length=1, description="Unique camera ID matching config filename")
    name: str = Field(..., min_length=1, description="Human-readable camera location")
    description: Optional[str] = Field(default="", description="Optional mounting/perspective notes")
    reference_resolution: List[int] = Field(..., description="[width, height] of the calibration frame")
    spots: List[SpotConfig] = Field(..., min_length=1, description="List of parking spots")

    @field_validator("reference_resolution")
    @classmethod
    def validate_resolution(cls, v: List[int]) -> List[int]:
        if len(v) != 2:
            raise ValueError(f"reference_resolution must have exactly 2 elements [width, height], got {v}")
        w, h = v
        if w <= 0 or h <= 0:
            raise ValueError(f"Resolution dimensions must be strictly positive, got [{w}, {h}]")
        return v

    @model_validator(mode="after")
    def validate_spots_and_geometry(self) -> "CameraConfig":
        w_max, h_max = self.reference_resolution
        seen_ids = set()

        for spot in self.spots:
            # 1. Unique Spot ID check
            if spot.id in seen_ids:
                raise ValueError(f"Duplicate spot ID '{spot.id}' detected in camera '{self.camera_id}'")
            seen_ids.add(spot.id)

            # 2. Coordinate boundary check
            for idx, (x, y) in enumerate(spot.polygon):
                if not (0 <= x <= w_max):
                    raise ValueError(
                        f"Spot '{spot.id}' vertex {idx} X={x} is out of bounds [0, {w_max}]"
                    )
                if not (0 <= y <= h_max):
                    raise ValueError(
                        f"Spot '{spot.id}' vertex {idx} Y={y} is out of bounds [0, {h_max}]"
                    )

            # 3. Non-degenerate polygon area check
            area = spot.compute_area()
            if area <= 50.0:
                raise ValueError(
                    f"Spot '{spot.id}' has degenerate area ({area:.1f} sq px <= 50.0). Vertices may be collinear or self-intersecting."
                )

        return self

    def to_detection_spots(self) -> List[Dict[str, Any]]:
        """Exports spots in the dictionary format consumed by detection.occupancy.evaluate_occupancy()."""
        return [{"id": s.id, "polygon": s.polygon} for s in self.spots]

    def get_spot_contours(self) -> Dict[str, np.ndarray]:
        """Returns a mapping of spot_id -> numpy OpenCV contour."""
        return {s.id: s.to_contour() for s in self.spots}


def load_camera_config(config_path: Union[str, Path]) -> CameraConfig:
    """Loads and validates a camera configuration from a JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Camera configuration file '{path}' not found")

    if path.suffix.lower() != ".json":
        raise ValueError(f"Expected a JSON file (.json), got '{path.name}'")

    with open(path, "r", encoding="utf-8") as f:
        try:
            raw_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON syntax in '{path}': {e}") from e

    if not isinstance(raw_dict, dict):
        raise ValueError(f"Expected a JSON dictionary at top level in '{path}', got {type(raw_dict).__name__}")

    return CameraConfig.model_validate(raw_dict)


def load_camera_config_by_id(
    camera_id: str,
    config_dir: Union[str, Path] = "config/cameras",
) -> CameraConfig:
    """Finds and loads a camera configuration JSON file by camera ID."""
    dir_path = Path(config_dir)
    target_json = dir_path / f"{camera_id}.json"
    if target_json.exists():
        return load_camera_config(target_json)

    raise FileNotFoundError(f"No configuration found for camera '{camera_id}' in directory '{config_dir}'")


def list_available_cameras(config_dir: Union[str, Path] = "config/cameras") -> List[str]:
    """Scans the configuration directory and returns a sorted list of registered camera IDs."""
    dir_path = Path(config_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    cams = []
    for file_path in dir_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() == ".json":
            cams.append(file_path.stem)

    return sorted(cams)
