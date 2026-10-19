import logging
import time
from fastapi import APIRouter, HTTPException, Response, status

from server.schemas import (
    BatteryReportRequest,
    BatteryReportResponse,
    CameraStatusResponse,
    HealthResponse,
    OverallStatusResponse,
)
from server.state import server_state

logger = logging.getLogger("parqueame.server.status")
router = APIRouter(tags=["Status & Health"])


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get server uptime and hardware health status",
)
def get_health() -> HealthResponse:
    return server_state.get_health()


@router.get(
    "/api/v1/status",
    response_model=OverallStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated occupancy status across all cameras",
)
def get_overall_status() -> OverallStatusResponse:
    return server_state.get_overall_status()


@router.get(
    "/api/v1/cameras/{camera_id}/status",
    response_model=CameraStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed parking spot occupancy for a specific camera",
)
def get_camera_status(camera_id: str) -> CameraStatusResponse:
    cam_status = server_state.get_camera_status(camera_id)
    if cam_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )
    return cam_status


@router.post(
    "/api/v1/cameras/{camera_id}/battery",
    response_model=BatteryReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Report camera battery level and voltage telemetry",
)
def report_camera_battery(
    camera_id: str,
    payload: BatteryReportRequest,
) -> BatteryReportResponse:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' is not registered.",
        )

    server_state.record_battery(
        camera_id=camera_id,
        percentage=payload.battery_percentage,
        voltage=payload.battery_voltage,
    )

    return BatteryReportResponse(
        status="success",
        camera_id=camera_id,
        battery_percentage=payload.battery_percentage,
        battery_voltage=payload.battery_voltage,
        timestamp=time.time(),
    )


@router.get(
    "/api/v1/cameras/{camera_id}/image",
    status_code=status.HTTP_200_OK,
    summary="Get latest annotated JPEG snapshot with detection overlays",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "Latest annotated camera JPEG image.",
        },
        404: {"description": "Camera not found or no image uploaded yet."},
    },
)
def get_camera_image(camera_id: str) -> Response:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' is not registered.",
        )

    img_bytes = server_state.get_camera_image(camera_id)
    if not img_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No image has been uploaded yet for camera '{camera_id}'.",
        )

    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
