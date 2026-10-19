from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SpotStatusItem(BaseModel):
    """Status for an individual parking spot."""
    spot_id: str = Field(..., description="Unique identifier of the spot")
    occupied: bool = Field(..., description="True if a vehicle is parked in this spot")
    confidence: float = Field(default=0.0, description="Detection confidence score (0.0 if vacant)")
    polygon: Optional[List[List[int]]] = Field(default=None, description="4-corner polygon coordinates")


class CameraStatusResponse(BaseModel):
    """Detailed status breakdown for a specific camera."""
    camera_id: str = Field(..., description="Camera identifier")
    name: str = Field(default="", description="Camera location name")
    total_spots: int = Field(default=0, description="Total number of spots monitored")
    occupied_spots: int = Field(default=0, description="Number of currently occupied spots")
    free_spots: int = Field(default=0, description="Number of currently vacant spots")
    last_processed_at: Optional[float] = Field(default=None, description="Timestamp of last processed frame")
    inference_time_ms: Optional[float] = Field(default=None, description="Inference latency of last frame in ms")
    battery_percentage: Optional[float] = Field(default=None, description="Battery percentage (0.0 to 100.0)")
    battery_voltage: Optional[float] = Field(default=None, description="Battery voltage in Volts (e.g. 3.95)")
    battery_updated_at: Optional[float] = Field(default=None, description="Timestamp of last battery report")
    spots: List[SpotStatusItem] = Field(default_factory=list, description="List of spot states")


class BatteryReportRequest(BaseModel):
    """Payload sent by cameras to report battery health."""
    battery_percentage: float = Field(..., ge=0.0, le=100.0, description="Battery level percentage from 0 to 100")
    battery_voltage: Optional[float] = Field(default=None, description="Measured battery voltage in Volts")


class BatteryReportResponse(BaseModel):
    """Confirmation response after battery level recorded."""
    status: str = Field(default="success", description="Status confirmation")
    camera_id: str = Field(..., description="Camera ID")
    battery_percentage: float = Field(..., description="Recorded battery percentage")
    battery_voltage: Optional[float] = Field(default=None, description="Recorded voltage")
    timestamp: float = Field(..., description="Timestamp of recording")


class OverallStatusResponse(BaseModel):
    """Aggregated status across all registered parking cameras."""
    total_spots: int = Field(default=0, description="Grand total spots across all cameras")
    total_occupied: int = Field(default=0, description="Total occupied spots across all cameras")
    total_free: int = Field(default=0, description="Total vacant spots across all cameras")
    timestamp: float = Field(..., description="Current server timestamp")
    cameras: Dict[str, CameraStatusResponse] = Field(default_factory=dict, description="Status mapping per camera")


class UploadResponse(BaseModel):
    """Response returned immediately after an image upload is processed."""
    status: str = Field(default="success", description="Processing status ('success' or 'error')")
    camera_id: str = Field(..., description="ID of the camera that uploaded the frame")
    processed_at: float = Field(..., description="UNIX timestamp when processing finished")
    inference_time_ms: float = Field(..., description="Time taken to run AI inference in milliseconds")
    total_spots: int = Field(..., description="Total spots evaluated")
    occupied_spots: int = Field(..., description="Count of occupied spots")
    free_spots: int = Field(..., description="Count of vacant spots")


class HealthResponse(BaseModel):
    """System health check and hardware metrics."""
    status: str = Field(default="healthy", description="Server health status")
    uptime_seconds: float = Field(..., description="Seconds since server started")
    cuda_available: bool = Field(..., description="True if NVIDIA GPU CUDA is active")
    device_name: Optional[str] = Field(default=None, description="GPU hardware name")
    registered_cameras: int = Field(..., description="Count of configured camera JSON profiles")
    timestamp: float = Field(..., description="Current server timestamp")


class SpotFlowMetrics(BaseModel):
    spot_id: str
    turnover_count: int
    average_duration_minutes: float
    occupancy_percentage: float
    total_sessions_recorded: int
    currently_occupied: bool


class CameraFlowSummaryResponse(BaseModel):
    camera_id: str
    time_window_hours: float
    total_stalls: int
    total_turnovers: int
    turnover_rate_per_stall: float
    average_duration_minutes: float
    average_occupancy_percentage: float
    peak_occupied_spots: int
    peak_timestamp: Optional[float] = None
    spots_breakdown: Dict[str, SpotFlowMetrics] = Field(default_factory=dict)


class TimelineBucketItem(BaseModel):
    timestamp: float
    time_label: str
    occupied_avg: float
    free_avg: float
    sample_count: int

