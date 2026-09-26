import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)

TARGET_VEHICLE_CLASSES: Dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass(frozen=True)
class VehicleDetection:
    """Represents a single detected vehicle bounding box."""

    box: Tuple[float, float, float, float]
    class_id: int
    class_name: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert detection to standard dictionary."""
        return {
            "box": [round(coord, 2) for coord in self.box],
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
        }


class VehicleDetector:
    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        device: Optional[str] = None,
        conf_threshold: float = 0.35,
    ) -> None:
        if device is not None:
            self.device = device
        else:
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"

        self.conf_threshold = conf_threshold
        logger.info(
            f"Initializing VehicleDetector on device '{self.device}' with model '{model_name}'"
        )

        self.model = YOLO(model_name)
        self.model.to(self.device)

        # Warmup forward pass
        warmup_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(
            source=warmup_frame,
            device=self.device,
            classes=list(TARGET_VEHICLE_CLASSES.keys()),
            conf=self.conf_threshold,
            verbose=False,
        )
        logger.info("VehicleDetector warmup completed successfully.")

    def _prepare_image(self, image: np.ndarray) -> np.ndarray:
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("Input image must be a non-empty numpy.ndarray")

        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.ndim == 3:
            channels = image.shape[2]
            if channels == 1:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            elif channels == 3:
                return image
            elif channels == 4:
                return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        raise ValueError(f"Unsupported image shape for detection: {image.shape}")

    def detect(
        self,
        image: np.ndarray,
        conf_threshold: Optional[float] = None,
    ) -> Tuple[List[VehicleDetection], float]:
        prepared_img = self._prepare_image(image)
        threshold = conf_threshold if conf_threshold is not None else self.conf_threshold

        start_time = time.perf_counter()
        results = self.model.predict(
            source=prepared_img,
            device=self.device,
            classes=list(TARGET_VEHICLE_CLASSES.keys()),
            conf=threshold,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        detections: List[VehicleDetection] = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            h, w = prepared_img.shape[:2]
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].tolist()
                x1 = max(0.0, min(float(xyxy[0]), float(w)))
                y1 = max(0.0, min(float(xyxy[1]), float(h)))
                x2 = max(0.0, min(float(xyxy[2]), float(w)))
                y2 = max(0.0, min(float(xyxy[3]), float(h)))

                cls_id = int(boxes.cls[i].item())
                conf = float(boxes.conf[i].item())
                cls_name = TARGET_VEHICLE_CLASSES.get(cls_id, "vehicle")

                detections.append(
                    VehicleDetection(
                        box=(x1, y1, x2, y2),
                        class_id=cls_id,
                        class_name=cls_name,
                        confidence=conf,
                    )
                )

        return detections, round(elapsed_ms, 2)
