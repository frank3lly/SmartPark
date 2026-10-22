# Camera Endpoints

### POST /api/v1/upload/{camera_id}
- **Gets:**
  - Path: `camera_id` (str)
  - Query: `battery` (float, optional), `voltage` (float, optional)
  - Body (multipart/form-data): `file` (image bytes, JPEG/PNG)
  - *Alias: `POST /upload/{camera_id}`*
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "status": "success",
    "camera_id": "cam_01",
    "processed_at": 1700000000.0,
    "inference_time_ms": 15.2,
    "total_spots": 5,
    "occupied_spots": 2,
    "free_spots": 3
  }
  ```

### POST /api/v1/cameras/{camera_id}/battery
- **Gets:**
  - Path: `camera_id` (str)
  - Body (application/json):
  ```json
  {
    "battery_percentage": 85.5,
    "battery_voltage": 3.95
  }
  ```
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "status": "success",
    "camera_id": "cam_01",
    "battery_percentage": 85.5,
    "battery_voltage": 3.95,
    "timestamp": 1700000000.0
  }
  ```

---

# Web Endpoints

### GET /
- **Gets:**
  - None
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "project": "Parqueame Smart Parking API",
    "version": "1.0.0",
    "status": "online",
    "docs_url": "/docs",
    "health_url": "/api/v1/health",
    "status_url": "/api/v1/status"
  }
  ```

### GET /api/v1/health
- **Gets:**
  - None
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "status": "healthy",
    "uptime_seconds": 123.4,
    "cuda_available": true,
    "device_name": "NVIDIA GeForce RTX ...",
    "registered_cameras": 2,
    "timestamp": 1700000000.0
  }
  ```

### GET /api/v1/status
- **Gets:**
  - None
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "total_spots": 105,
    "total_occupied": 10,
    "total_free": 95,
    "timestamp": 1700000000.0,
    "cameras": {
      "cam_01": {
        "camera_id": "cam_01",
        "name": "cam_01",
        "total_spots": 5,
        "occupied_spots": 2,
        "free_spots": 3,
        "last_processed_at": 1700000000.0,
        "inference_time_ms": 15.2,
        "battery_percentage": 85.5,
        "battery_voltage": 3.95,
        "battery_updated_at": 1700000000.0,
        "spots": [
          {
            "spot_id": "spot_01",
            "occupied": true,
            "confidence": 0.88,
            "polygon": [[10, 20], [30, 20], [30, 40], [10, 40]]
          }
        ]
      }
    }
  }
  ```

### GET /api/v1/cameras/{camera_id}/status
- **Gets:**
  - Path: `camera_id` (str)
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "camera_id": "cam_01",
    "name": "cam_01",
    "total_spots": 5,
    "occupied_spots": 2,
    "free_spots": 3,
    "last_processed_at": 1700000000.0,
    "inference_time_ms": 15.2,
    "battery_percentage": 85.5,
    "battery_voltage": 3.95,
    "battery_updated_at": 1700000000.0,
    "spots": [
      {
        "spot_id": "spot_01",
        "occupied": true,
        "confidence": 0.88,
        "polygon": [[10, 20], [30, 20], [30, 40], [10, 40]]
      }
    ]
  }
  ```

### GET /api/v1/cameras/{camera_id}/image
- **Gets:**
  - Path: `camera_id` (str)
- **Vomits:**
  - Binary image (200 OK, `image/jpeg`)

### GET /storage/images/latest_{camera_id}.jpg
- **Gets:**
  - Path: `camera_id` (str)
- **Vomits:**
  - Static binary image (200 OK, `image/jpeg`)

### GET /api/v1/analytics/cameras/{camera_id}
- **Gets:**
  - Path: `camera_id` (str)
  - Query: `hours` (float, default 2.0)
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "camera_id": "cam_01",
    "time_window_hours": 2.0,
    "total_stalls": 5,
    "total_turnovers": 3,
    "turnover_rate_per_stall": 0.6,
    "average_duration_minutes": 20.0,
    "average_occupancy_percentage": 40.0,
    "peak_occupied_spots": 3,
    "peak_timestamp": 1700000000.0,
    "spots_breakdown": {
      "spot_01": {
        "spot_id": "spot_01",
        "turnover_count": 1,
        "average_duration_minutes": 15.0,
        "occupancy_percentage": 50.0,
        "total_sessions_recorded": 1,
        "currently_occupied": false
      }
    }
  }
  ```

### GET /api/v1/analytics/timeline
- **Gets:**
  - Query: `camera_id` (str, optional), `hours` (float, default 2.0), `bucket_minutes` (int, default 15)
- **Vomits:**
  - JSON (200 OK):
  ```json
  [
    {
      "timestamp": 1700000000.0,
      "time_label": "14:15",
      "occupied_avg": 2.4,
      "free_avg": 2.6,
      "sample_count": 10
    }
  ]
  ```

### GET /api/v1/analytics/storage
- **Gets:**
  - None
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "total_logs": 150,
    "total_spot_records": 750,
    "first_log_time": 1700000000.0,
    "last_log_time": 1700003600.0,
    "active_cameras": ["cam_01", "cam_03"]
  }
  ```

### GET /api/v1/analytics/summary
- **Gets:**
  - Query: `hours` (float, default 2.0)
- **Vomits:**
  - JSON (200 OK):
  ```json
  {
    "time_window_hours": 2.0,
    "total_cameras": 2,
    "total_stalls": 105,
    "total_turnovers": 12,
    "turnover_rate_per_stall": 0.11,
    "average_duration_minutes": 22.5,
    "cameras": {
      "cam_01": {
        "camera_id": "cam_01",
        "time_window_hours": 2.0,
        "total_stalls": 5,
        "total_turnovers": 3,
        "turnover_rate_per_stall": 0.6,
        "average_duration_minutes": 20.0,
        "average_occupancy_percentage": 40.0,
        "peak_occupied_spots": 3,
        "peak_timestamp": 1700000000.0,
        "spots_breakdown": {}
      }
    },
    "timeline": [
      {
        "timestamp": 1700000000.0,
        "time_label": "14:15",
        "occupied_avg": 2.4,
        "free_avg": 2.6,
        "sample_count": 10
      }
    ]
  }
  ```
