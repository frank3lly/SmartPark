from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from detection.occupancy import (
    OccupancyResponse,
    calculate_ground_anchor,
    normalize_spot_polygon,
)

COLOR_FREE_OUTLINE = (0, 200, 0)       # Green
COLOR_OCCUPIED_OUTLINE = (0, 0, 230)   # Red
COLOR_OCCUPIED_FILL = (0, 0, 200)      # Translucent Red
COLOR_VEHICLE_BOX = (255, 220, 0)      # Cyan / Light Blue
COLOR_ANCHOR = (0, 255, 255)           # Yellow
COLOR_HUD_BG = (20, 20, 20)            # Dark Slate
COLOR_TEXT = (255, 255, 255)           # White
COLOR_TAG_BG = (30, 30, 30)            # Charcoal


def _put_labeled_tag(
    img: np.ndarray,
    text: str,
    org: Tuple[int, int],
    font_scale: float = 0.45,
    thickness: int = 1,
    text_color: Tuple[int, int, int] = COLOR_TEXT,
    bg_color: Tuple[int, int, int] = COLOR_TAG_BG,
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = org
    # Clamp to image borders
    h_img, w_img = img.shape[:2]
    x = max(2, min(x, w_img - tw - 4))
    y = max(th + 4, min(y, h_img - 4))

    cv2.rectangle(img, (x, y - th - 3), (x + tw + 4, y + baseline), bg_color, -1)
    cv2.putText(
        img,
        text,
        (x + 2, y - 1),
        font,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )


def draw_detection_overlay(
    image: np.ndarray,
    occupancy_response: Union[OccupancyResponse, Dict[str, Any]],
    spots: List[Dict[str, Any]],
    detections: Optional[List[Any]] = None,
    draw_anchors: bool = True,
    draw_hud: bool = True,
) -> np.ndarray:
    output = image.copy()
    overlay = output.copy()
    h_img, w_img = output.shape[:2]

    # Normalize response into dictionary format
    if isinstance(occupancy_response, OccupancyResponse):
        resp_dict = occupancy_response.to_dict()
    else:
        resp_dict = occupancy_response

    status_map: Dict[str, Dict[str, Any]] = {
        str(s.get("spot_id")): s for s in resp_dict.get("spots", [])
    }

    # 1. Draw Spot Polygons
    for idx, spot in enumerate(spots):
        spot_id = spot.get("id")
        if spot_id is None:
            spot_id = spot.get("spot_id")
        if spot_id is None:
            spot_id = f"spot_{idx + 1}"
        spot_id = str(spot_id)
        raw_poly = spot.get("polygon") or spot.get("roi") or spot.get("box")
        if raw_poly is None:
            continue

        contour = normalize_spot_polygon(raw_poly)
        spot_info = status_map.get(spot_id, {})
        is_occupied = spot_info.get("occupied", False)
        conf = spot_info.get("confidence", 0.0)

        if is_occupied:
            # Draw translucent fill on overlay
            cv2.fillPoly(overlay, [contour], COLOR_OCCUPIED_FILL)
            cv2.polylines(output, [contour], isClosed=True, color=COLOR_OCCUPIED_OUTLINE, thickness=2)
            label = f"{spot_id} [OCC {conf:.2f}]"
            tag_bg = (0, 0, 160)
        else:
            cv2.polylines(output, [contour], isClosed=True, color=COLOR_FREE_OUTLINE, thickness=2)
            label = f"{spot_id} [FREE]"
            tag_bg = (0, 120, 0)

        # Place label near the first vertex
        v0 = contour[0][0]
        _put_labeled_tag(output, label, (int(v0[0]), int(v0[1]) - 6), font_scale=0.42, bg_color=tag_bg)

    # Blend translucent fills
    cv2.addWeighted(overlay, 0.25, output, 0.75, 0, output)

    # 2. Draw Detected Vehicles
    if detections:
        for det in detections:
            box = getattr(det, "box", None) or (det.get("box") if isinstance(det, dict) else None)
            if not box:
                continue
            x1, y1, x2, y2 = [int(round(c)) for c in box]
            class_name = getattr(det, "class_name", None) or (det.get("class_name") if isinstance(det, dict) else "car")
            conf = getattr(det, "confidence", None) or (det.get("confidence") if isinstance(det, dict) else 0.0)

            # Draw vehicle bounding box
            cv2.rectangle(output, (x1, y1), (x2, y2), COLOR_VEHICLE_BOX, 2)
            det_label = f"{class_name} {float(conf):.2f}"
            _put_labeled_tag(output, det_label, (x1, y1 - 4), font_scale=0.40, bg_color=COLOR_TAG_BG)

            # Draw tire ground-contact anchor
            if draw_anchors:
                cx, anchor_y = calculate_ground_anchor(tuple(box))
                ax, ay = int(round(cx)), int(round(anchor_y))
                cv2.circle(output, (ax, ay), 4, COLOR_ANCHOR, -1)
                # Small crosshair
                cv2.line(output, (ax - 5, ay), (ax + 5, ay), COLOR_ANCHOR, 1)
                cv2.line(output, (ax, ay - 5), (ax, ay + 5), COLOR_ANCHOR, 1)

    # 3. Draw HUD Banner
    if draw_hud:
        hud_height = 34
        cv2.rectangle(output, (0, 0), (w_img, hud_height), COLOR_HUD_BG, -1)
        cv2.line(output, (0, hud_height), (w_img, hud_height), (60, 60, 60), 1)

        cam_id = resp_dict.get("camera_id", "camera")
        total = len(resp_dict.get("spots", []))
        occ = sum(1 for s in resp_dict.get("spots", []) if s.get("occupied"))
        free = total - occ
        ms = float(resp_dict.get("inference_time_ms", 0.0))

        hud_text = f"CAM: {cam_id}  |  TOTAL: {total}  |  OCCUPIED: {occ}  |  FREE: {free}  |  LATENCY: {ms:.1f}ms"
        cv2.putText(
            output,
            hud_text,
            (14, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            COLOR_TEXT,
            1,
            cv2.LINE_AA,
        )

    return output
