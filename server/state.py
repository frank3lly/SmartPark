import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import torch

from detection.config_loader import CameraConfig, load_camera_config
from detection.detector import VehicleDetector
from detection.occupancy import OccupancyResponse
from server.schemas import (
    CameraStatusResponse,
    HealthResponse,
    OverallStatusResponse,
    SpotStatusItem,
)

logger = logging.getLogger("parqueame.server.state")


class ServerState:
    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.detector: Optional[VehicleDetector] = None
        self.camera_configs: Dict[str, CameraConfig] = {}
        self.latest_occupancy: Dict[str, OccupancyResponse] = {}
        self.latest_images: Dict[str, bytes] = {}
        self.latest_battery: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def initialize(self, config_dir: str = "config/cameras") -> None:
        logger.info("Initializing ServerState: Preloading AI detector and camera configs...")
        # 1. Initialize YOLOv8 Detector in GPU VRAM
        self.detector = VehicleDetector()

        # 2. Preload Camera Configurations
        cfg_path = Path(config_dir)
        with self.lock:
            self.camera_configs.clear()

        if cfg_path.exists():
            for p in sorted(cfg_path.glob("*.json")):
                try:
                    cfg = load_camera_config(p)
                    with self.lock:
                        self.camera_configs[cfg.camera_id] = cfg
                    logger.info(f"Loaded configuration for camera '{cfg.camera_id}' ({len(cfg.spots)} spots)")
                except Exception as e:
                    logger.error(f"Failed to load camera config '{p}': {e}")
        logger.info(f"ServerState initialized with {len(self.camera_configs)} cameras.")

    def record_result(
        self,
        camera_id: str,
        occupancy_resp: OccupancyResponse,
        annotated_jpeg: Optional[bytes] = None,
    ) -> None:
        with self.lock:
            self.latest_occupancy[camera_id] = occupancy_resp
            if annotated_jpeg is not None:
                self.latest_images[camera_id] = annotated_jpeg

    def record_battery(
        self,
        camera_id: str,
        percentage: float,
        voltage: Optional[float] = None,
    ) -> None:
        with self.lock:
            self.latest_battery[camera_id] = {
                "percentage": round(percentage, 2),
                "voltage": round(voltage, 3) if voltage is not None else None,
                "updated_at": time.time(),
            }

    def get_camera_status(self, camera_id: str) -> Optional[CameraStatusResponse]:
        with self.lock:
            cfg = self.camera_configs.get(camera_id)
            if not cfg:
                return None

            latest = self.latest_occupancy.get(camera_id)
            bat = self.latest_battery.get(camera_id, {})
            bat_pct = bat.get("percentage")
            bat_v = bat.get("voltage")
            bat_ts = bat.get("updated_at")
            spots_list = []

            if latest:
                # Map spot occupancy
                latest_map = {s.spot_id: s for s in latest.spots}
                for spot_cfg in cfg.spots:
                    match = latest_map.get(spot_cfg.id)
                    spots_list.append(
                        SpotStatusItem(
                            spot_id=spot_cfg.id,
                            occupied=match.occupied if match else False,
                            confidence=match.confidence if match else 0.0,
                            polygon=spot_cfg.polygon,
                        )
                    )
                return CameraStatusResponse(
                    camera_id=camera_id,
                    name=cfg.name,
                    total_spots=len(cfg.spots),
                    occupied_spots=latest.occupied_count,
                    free_spots=latest.free_count,
                    last_processed_at=latest.timestamp,
                    inference_time_ms=latest.inference_time_ms,
                    battery_percentage=bat_pct,
                    battery_voltage=bat_v,
                    battery_updated_at=bat_ts,
                    spots=spots_list,
                )
            else:
                # No frame received yet; all default to vacant
                for spot_cfg in cfg.spots:
                    spots_list.append(
                        SpotStatusItem(
                            spot_id=spot_cfg.id,
                            occupied=False,
                            confidence=0.0,
                            polygon=spot_cfg.polygon,
                        )
                    )
                return CameraStatusResponse(
                    camera_id=camera_id,
                    name=cfg.name,
                    total_spots=len(cfg.spots),
                    occupied_spots=0,
                    free_spots=len(cfg.spots),
                    last_processed_at=None,
                    inference_time_ms=None,
                    battery_percentage=bat_pct,
                    battery_voltage=bat_v,
                    battery_updated_at=bat_ts,
                    spots=spots_list,
                )

    def get_overall_status(self) -> OverallStatusResponse:
        with self.lock:
            cam_ids = list(self.camera_configs.keys())

        cameras_map: Dict[str, CameraStatusResponse] = {}
        total_spots = 0
        total_occupied = 0
        total_free = 0

        for cid in cam_ids:
            stat = self.get_camera_status(cid)
            if stat:
                cameras_map[cid] = stat
                total_spots += stat.total_spots
                total_occupied += stat.occupied_spots
                total_free += stat.free_spots

        return OverallStatusResponse(
            total_spots=total_spots,
            total_occupied=total_occupied,
            total_free=total_free,
            timestamp=time.time(),
            cameras=cameras_map,
        )

    def get_health(self) -> HealthResponse:
        cuda_ok = torch.cuda.is_available()
        dev_name = "CPU"
        if cuda_ok:
            try:
                dev_name = torch.cuda.get_device_name(0)
            except Exception:
                dev_name = "CUDA (Unknown Device)"

        with self.lock:
            reg_count = len(self.camera_configs)

        return HealthResponse(
            status="healthy",
            uptime_seconds=round(time.time() - self.start_time, 1),
            cuda_available=cuda_ok,
            device_name=dev_name,
            registered_cameras=reg_count,
            timestamp=time.time(),
        )

    def get_camera_image(self, camera_id: str) -> Optional[bytes]:
        with self.lock:
            return self.latest_images.get(camera_id)


server_state = ServerState()
