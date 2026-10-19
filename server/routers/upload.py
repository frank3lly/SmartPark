import asyncio
import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from detection.config_loader import CameraConfig
from detection.detector import VehicleDetector
from detection.occupancy import OccupancyResponse, evaluate_occupancy
from detection.visualizer import draw_detection_overlay
from server.schemas import UploadResponse
from server.state import server_state

logger = logging.getLogger("parqueame.server.upload")
router = APIRouter(tags=["Ingestion"])


def process_frame_sync(
    image: np.ndarray,
    camera_cfg: CameraConfig,
    detector: VehicleDetector,
) -> Tuple[OccupancyResponse, bytes]:
    """Synchronous CPU/GPU worker running detection and spatial math."""
    spots = camera_cfg.to_detection_spots()
    detections, latency_ms = detector.detect(image)

    occupancy_resp = evaluate_occupancy(
        spots=spots,
        detections=detections,
        camera_id=camera_cfg.camera_id,
        inference_time_ms=latency_ms,
    )

    annotated = draw_detection_overlay(
        image=image,
        occupancy_response=occupancy_resp,
        spots=spots,
        detections=detections,
        draw_anchors=True,
        draw_hud=True,
    )

    success, buffer = cv2.imencode(
        ".jpg",
        annotated,
        [int(cv2.IMWRITE_JPEG_QUALITY), 85],
    )
    annotated_bytes = buffer.tobytes() if success else b""

    return occupancy_resp, annotated_bytes


@router.post(
    "/api/v1/upload/{camera_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload image from camera and trigger detection",
)
@router.post(
    "/upload/{camera_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def upload_camera_frame(
    camera_id: str,
    file: UploadFile = File(..., description="JPEG or PNG image frame from camera"),
    battery: Optional[float] = None,
    voltage: Optional[float] = None,
) -> UploadResponse:
    # 1. Validate camera configuration exists
    camera_cfg = server_state.camera_configs.get(camera_id)
    if not camera_cfg:
        logger.warning(f"Upload rejected: camera '{camera_id}' is not registered.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in server configuration.",
        )

    if server_state.detector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Detection engine is not yet initialized.",
        )

    # 2. Read bytes into RAM and decode directly via OpenCV
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Received empty file payload.",
        )

    nparr = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image encoding. File could not be decoded as an image.",
        )

    # 3. Dispatch synchronous vision workload to threadpool
    try:
        occupancy_resp, annotated_bytes = await asyncio.to_thread(
            process_frame_sync,
            image,
            camera_cfg,
            server_state.detector,
        )
    except Exception as e:
        logger.error(f"Inference pipeline failed for '{camera_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference pipeline error: {str(e)}",
        )

    # 4. Record detection result and battery telemetry to state cache
    server_state.record_result(
        camera_id=camera_id,
        occupancy_resp=occupancy_resp,
        annotated_jpeg=annotated_bytes,
    )
    if battery is not None:
        server_state.record_battery(
            camera_id=camera_id,
            percentage=battery,
            voltage=voltage,
        )

    logger.info(
        f"Camera '{camera_id}' processed in {occupancy_resp.inference_time_ms:.1f}ms: "
        f"{occupancy_resp.occupied_count} occupied, {occupancy_resp.free_count} free."
    )

    # 5. Return summary
    return UploadResponse(
        status="success",
        camera_id=camera_id,
        processed_at=occupancy_resp.timestamp,
        inference_time_ms=occupancy_resp.inference_time_ms,
        total_spots=occupancy_resp.total_spots,
        occupied_spots=occupancy_resp.occupied_count,
        free_spots=occupancy_resp.free_count,
    )
