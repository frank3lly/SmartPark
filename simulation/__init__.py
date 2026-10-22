"""Parqueame simulation package."""

from simulation.simulate_cameras import (
    camera_worker,
    main as simulate_cameras_main,
    resolve_camera_images,
    stop_event,
)
from simulation.scenarios import (
    ScenarioOrchestrator,
    SUPPORTED_SCENARIOS,
    parse_ground_truth_xml,
)

__all__ = [
    "camera_worker",
    "simulate_cameras_main",
    "resolve_camera_images",
    "stop_event",
    "ScenarioOrchestrator",
    "SUPPORTED_SCENARIOS",
    "parse_ground_truth_xml",
]
