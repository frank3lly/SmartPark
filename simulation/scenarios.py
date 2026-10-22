import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger("parqueame.simulation.scenarios")

SUPPORTED_SCENARIOS = ("sequential", "lot_filling", "lot_emptying", "turnover_stress")


def parse_ground_truth_xml(xml_path: Union[str, Path]) -> Dict[str, bool]:
    """
    Parses a PKLot XML ground truth file.
    Returns mapping of normalized spot_id (e.g. 'spot_01' and '1') to bool (True if occupied, False if empty).
    """
    path_obj = Path(xml_path)
    if not path_obj.is_file():
        return {}

    occupancy_map: Dict[str, bool] = {}
    try:
        tree = ET.parse(path_obj)
        root = tree.getroot()
        for space in root.findall("space"):
            space_id = space.attrib.get("id")
            occ_str = space.attrib.get("occupied", "0")
            is_occupied = (occ_str.strip() == "1")

            if space_id is not None:
                clean_id = space_id.strip()
                occupancy_map[clean_id] = is_occupied
                # Also store canonical zero-padded ID matching camera configs (e.g. spot_01)
                try:
                    num = int(re.sub(r"[^0-9]", "", clean_id))
                    occupancy_map[f"spot_{num:02d}"] = is_occupied
                    occupancy_map[f"spot_{num}"] = is_occupied
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"Error parsing ground-truth XML '{xml_path}': {e}")
        return {}

    return occupancy_map


class ScenarioOrchestrator:
    """Manages, filters, and pairs image datasets with ground-truth XML annotations."""

    def __init__(self, samples_dir: Union[str, Path] = "test-samples") -> None:
        self.samples_dir = Path(samples_dir)

    def list_available_cameras(self) -> List[str]:
        """Discovers camera directories in the test-samples folder."""
        if not self.samples_dir.is_dir():
            return []

        cams = []
        for p in self.samples_dir.iterdir():
            if p.is_dir() and p.name.startswith("cam_"):
                cams.append(p.name)

        return sorted(cams) if cams else ["cam_01", "cam_02", "cam_03", "cam_04"]

    def _collect_raw_images(self, camera_id: str) -> List[Path]:
        """Gathers all valid JPEG images for a camera with fallback to root samples."""
        cam_dir = self.samples_dir / camera_id
        collected: List[Path] = []

        if cam_dir.is_dir():
            for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
                collected.extend(cam_dir.glob(ext))

        # Fallback to root test-samples if camera directory is empty or missing
        if not collected and self.samples_dir.is_dir():
            for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
                collected.extend(self.samples_dir.glob(ext))

        # Filter out symlinks or duplicates, sort naturally
        unique_paths = sorted(list(set(p.resolve() for p in collected if p.is_file())))
        return unique_paths

    def get_camera_images(
        self,
        camera_id: str,
        scenario: str = "sequential",
        max_frames: Optional[int] = None,
    ) -> List[Path]:
        """Returns ordered frame sequence according to the selected scenario strategy."""
        raw_images = self._collect_raw_images(camera_id)
        if not raw_images:
            logger.warning(f"No images discovered for camera '{camera_id}' in '{self.samples_dir}'.")
            return []

        scenario_lower = scenario.lower()
        if scenario_lower not in SUPPORTED_SCENARIOS:
            logger.warning(
                f"Unknown scenario '{scenario}'. Defaulting to 'sequential'. "
                f"Supported: {SUPPORTED_SCENARIOS}"
            )
            scenario_lower = "sequential"

        total = len(raw_images)

        if scenario_lower == "sequential":
            selected = list(raw_images)

        elif scenario_lower == "lot_filling":
            half_point = max(1, total // 2)
            selected = raw_images[:half_point]

        elif scenario_lower == "lot_emptying":
            half_point = max(1, total // 2)
            selected = list(reversed(raw_images[half_point:]))

        elif scenario_lower == "turnover_stress":
            step = 2 if total >= 4 else 1
            selected = raw_images[::step]

        if max_frames and max_frames > 0:
            selected = selected[:max_frames]

        return selected

    def get_ground_truth_path(self, image_path: Union[str, Path]) -> Optional[Path]:
        """Returns the corresponding .xml ground truth path if it exists."""
        p = Path(image_path)
        xml_path = p.with_suffix(".xml")
        return xml_path if xml_path.is_file() else None

    def load_ground_truth(self, xml_path: Union[str, Path]) -> Dict[str, bool]:
        """Loads and parses ground truth occupancy mapping from XML."""
        return parse_ground_truth_xml(xml_path)

    def validate_camera_datasets(self) -> Dict[str, Dict[str, int]]:
        """Produces a diagnostic report of available frames and XML ground truth files."""
        cams = self.list_available_cameras()
        manifest: Dict[str, Dict[str, int]] = {}
        for c in cams:
            imgs = self._collect_raw_images(c)
            xml_count = sum(1 for img in imgs if self.get_ground_truth_path(img) is not None)
            manifest[c] = {"frames": len(imgs), "ground_truth_xmls": xml_count}
        return manifest
