import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from server.schemas import CameraFlowSummaryResponse, TimelineBucketItem
from server.state import server_state
from storage.analytics import (
    compute_camera_flow_summary,
    compute_timeline_series,
)
from storage.repository import get_system_summary_stats

logger = logging.getLogger("parqueame.server.analytics")
router = APIRouter(prefix="/api/v1/analytics", tags=["Flow Analytics"])


@router.get(
    "/cameras/{camera_id}",
    response_model=CameraFlowSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get parking flow analysis, turnover rate, and duration metrics",
)
def get_camera_flow_analytics(
    camera_id: str,
    hours: float = Query(
        default=2.0, ge=0.1, le=168.0, description="Observation window in hours"
    ),
) -> CameraFlowSummaryResponse:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )

    summary = compute_camera_flow_summary(camera_id=camera_id, hours=hours)
    return CameraFlowSummaryResponse.model_validate(summary)


@router.get(
    "/timeline",
    response_model=List[TimelineBucketItem],
    status_code=status.HTTP_200_OK,
    summary="Get time-binned occupancy series for frontend timeline charts",
)
def get_timeline_chart_data(
    camera_id: Optional[str] = Query(
        default=None, description="Optional filter by camera ID"
    ),
    hours: float = Query(
        default=2.0, ge=0.1, le=168.0, description="Window in hours"
    ),
    bucket_minutes: int = Query(
        default=15,
        ge=1,
        le=60,
        description="Interval size per bucket in minutes",
    ),
) -> List[TimelineBucketItem]:
    series = compute_timeline_series(
        camera_id=camera_id,
        hours=hours,
        bucket_minutes=bucket_minutes,
    )
    return [TimelineBucketItem.model_validate(b) for b in series]


@router.get(
    "/storage",
    status_code=status.HTTP_200_OK,
    summary="Get SQLite storage statistics and database metadata",
)
def get_storage_stats() -> Dict[str, Any]:
    return get_system_summary_stats()
