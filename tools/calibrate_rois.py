import argparse
import json
import logging
import os
import sys

# Force Qt to use X11 (xcb) under WSL/Linux to prevent blank/frozen Wayland windows
if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("calibrate_rois")

COLOR_COMPLETED_OUTLINE = (255, 220, 0)     # Cyan
COLOR_COMPLETED_FILL = (180, 140, 0)        # Translucent Cyan
COLOR_IN_PROGRESS = (0, 140, 255)           # Bright Orange
COLOR_TEXT = (255, 255, 255)                # White
COLOR_BAR_BG = (30, 30, 30)                 # Dark Charcoal


class ROICalibrator:
    """Interactive OpenCV GUI calibrator for defining parking spot ROIs on reference frames."""

    def __init__(
        self,
        image_path: str,
        camera_id: str,
        config_dir: str = "config/cameras",
        clean_start: bool = False,
    ) -> None:
        self.image_path = image_path
        self.camera_id = camera_id
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / f"{camera_id}.json"

        self.base_image = cv2.imread(image_path)
        if self.base_image is None:
            raise FileNotFoundError(f"Failed to read image at '{image_path}'")

        self.h, self.w = self.base_image.shape[:2]
        self.spots: List[Dict[str, Any]] = []
        self.in_progress_points: List[List[int]] = []
        self.mouse_pos: Tuple[int, int] = (0, 0)
        self.window_name = f"Parqueame Calibration - {self.camera_id} ({self.w}x{self.h})"
        self.base_annotated_frame: np.ndarray = self.base_image.copy()

        if not clean_start:
            self._load_existing_config()
        self._update_spots_cache()

    def _load_existing_config(self) -> None:
        """Loads spots from an existing JSON configuration file if present."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "spots" in data:
                    self.spots = data["spots"]
                    logger.info(f"Loaded {len(self.spots)} existing spots from '{self.config_file}'")
            except Exception as e:
                logger.warning(f"Could not load existing config '{self.config_file}': {e}")

    def _update_spots_cache(self) -> None:
        """Pre-renders all saved spots onto the cached base frame for instant rendering."""
        frame = self.base_image.copy()
        if not self.spots:
            self.base_annotated_frame = frame
            return

        overlay = frame.copy()
        for spot in self.spots:
            poly = spot.get("polygon", [])
            if len(poly) >= 3:
                cnt = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(overlay, [cnt], COLOR_COMPLETED_FILL)
                cv2.polylines(frame, [cnt], isClosed=True, color=COLOR_COMPLETED_OUTLINE, thickness=2)
                v0 = poly[0]
                label = spot.get("id", "spot")
                cv2.putText(frame, label, (v0[0] + 4, v0[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT, 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        self.base_annotated_frame = frame

    def on_mouse(self, event: int, x: int, y: int, flags: int, param: Any) -> None:
        """Mouse event handler for drawing quadrilateral corners."""
        self.mouse_pos = (x, y)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.in_progress_points.append([int(x), int(y)])
            print(f"\r[+] Corner {len(self.in_progress_points)}/4 clicked at ({x}, {y})", flush=True)
            logger.info(f"Added vertex {len(self.in_progress_points)}/4 at ({x}, {y})")

            if len(self.in_progress_points) == 4:
                default_id = f"spot_{len(self.spots) + 1:02d}"
                print(f"\n[?] Enter ID for completed spot [Default: {default_id}]: ", end="", flush=True)
                user_id = default_id
                try:
                    import select
                    if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                        line = sys.stdin.readline().strip()
                        if line:
                            user_id = line
                except Exception:
                    pass

                self.spots.append({
                    "id": user_id,
                    "polygon": list(self.in_progress_points)
                })
                self._update_spots_cache()
                print(f"\n[✓] Recorded '{user_id}' with 4 vertices. Press 'S' to save.", flush=True)
                logger.info(f"Recorded '{user_id}' with 4 vertices. Press 'S' to save.")
                self.in_progress_points.clear()

    def save(self) -> None:
        """Saves current spot definitions to the target camera JSON configuration file."""
        payload = {
            "camera_id": self.camera_id,
            "name": f"Camera {self.camera_id}",
            "description": "Configured via calibrate_rois.py",
            "reference_resolution": [self.w, self.h],
            "spots": self.spots,
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n[✓] Successfully saved {len(self.spots)} spots to '{self.config_file}'", flush=True)
        logger.info(f"Successfully saved {len(self.spots)} spots to '{self.config_file}'")

    def undo(self) -> None:
        """Reverts the last clicked vertex or completed spot."""
        if self.in_progress_points:
            popped = self.in_progress_points.pop()
            print(f"\n[-] Undid in-progress point {popped}", flush=True)
            logger.info(f"Removed in-progress point {popped}")
        elif self.spots:
            popped_spot = self.spots.pop()
            self._update_spots_cache()
            print(f"\n[-] Undid spot '{popped_spot.get('id')}'", flush=True)
            logger.info(f"Removed spot '{popped_spot.get('id')}'")
        else:
            logger.info("Nothing to undo.")

    def render(self) -> np.ndarray:
        """Renders cached spots with in-progress lines, high-contrast vertices, and status bar."""
        frame = self.base_annotated_frame.copy()

        # 2. Draw in-progress vertices and connecting segments
        num_pts = len(self.in_progress_points)
        for i, pt in enumerate(self.in_progress_points):
            # Double ring: white outer + bright orange inner for maximum contrast
            cv2.circle(frame, (pt[0], pt[1]), 8, (255, 255, 255), 2)
            cv2.circle(frame, (pt[0], pt[1]), 6, COLOR_IN_PROGRESS, -1)
            # Text with shadow
            label = str(i + 1)
            cv2.putText(frame, label, (pt[0] + 9, pt[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, label, (pt[0] + 8, pt[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        if num_pts > 1:
            for i in range(num_pts - 1):
                p1 = self.in_progress_points[i]
                p2 = self.in_progress_points[i + 1]
                cv2.line(frame, (p1[0], p1[1]), (p2[0], p2[1]), (0, 0, 0), 3)
                cv2.line(frame, (p1[0], p1[1]), (p2[0], p2[1]), COLOR_IN_PROGRESS, 2)

        # Draw rubber-band line from last point to cursor
        if num_pts in (1, 2, 3):
            last_pt = self.in_progress_points[-1]
            cv2.line(frame, (last_pt[0], last_pt[1]), self.mouse_pos, (0, 220, 255), 2)

        # 3. Draw bottom instruction status bar
        bar_h = 28
        cv2.rectangle(frame, (0, self.h - bar_h), (self.w, self.h), COLOR_BAR_BG, -1)
        status_txt = f"Spots: {len(self.spots)} | In-Progress: {num_pts}/4 | [Click] Add Pt | [U] Undo | [C] Cancel | [R] Reset | [S] Save | [Q] Quit"
        cv2.putText(frame, status_txt, (10, self.h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.38, COLOR_TEXT, 1, cv2.LINE_AA)

        return frame

    def run(self) -> None:
        """Runs the interactive OpenCV calibration GUI event loop."""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.w, self.h)
        cv2.setMouseCallback(self.window_name, self.on_mouse)

        logger.info("=" * 60)
        logger.info(f"Started ROI Calibration for {self.camera_id}")
        logger.info("Click 4 corners for each spot (clockwise/counter-clockwise).")
        logger.info("Keys: [S] Save | [U] Undo | [C] Cancel Spot | [R] Reset | [Q] Quit")
        logger.info("=" * 60)

        try:
            while True:
                display_frame = self.render()
                cv2.imshow(self.window_name, display_frame)

                key = cv2.waitKey(20) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:  # 27 = ESC
                    logger.info("Exiting calibration tool.")
                    break
                elif key in [ord("s"), ord("S")]:
                    self.save()
                elif key in [ord("u"), ord("U")]:
                    self.undo()
                elif key in [ord("c"), ord("C")]:
                    self.in_progress_points.clear()
                    print("\n[!] Cancelled in-progress spot points.", flush=True)
                    logger.info("Cancelled current spot points.")
                elif key in [ord("r"), ord("R")]:
                    self.spots.clear()
                    self.in_progress_points.clear()
                    self._update_spots_cache()
                    print("\n[!] Reset all spots.", flush=True)
                    logger.info("Reset all spots.")
        finally:
            cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description="Parqueame Interactive ROI Calibration Tool")
    parser.add_argument("--image", type=str, required=True, help="Path to reference snapshot image")
    parser.add_argument("--camera", type=str, required=True, help="Camera ID (e.g. cam_01)")
    parser.add_argument("--config-dir", type=str, default="config/cameras", help="Directory to save JSON configs")
    parser.add_argument("--clean", action="store_true", help="Start with a blank canvas without loading existing spots")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without launching interactive GUI")

    args = parser.parse_args()

    if not os.path.exists(args.image):
        logger.error(f"Image not found: '{args.image}'")
        return 1

    if args.dry_run:
        logger.info(f"[Dry Run] Successfully validated inputs: image='{args.image}', camera='{args.camera}'")
        return 0

    try:
        calibrator = ROICalibrator(
            image_path=args.image,
            camera_id=args.camera,
            config_dir=args.config_dir,
            clean_start=args.clean,
        )
        calibrator.run()
        return 0
    except cv2.error as e:
        logger.error(f"OpenCV GUI error (X11/Wayland display server required): {e}")
        return 1
    except Exception as e:
        logger.error(f"Error during calibration: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
