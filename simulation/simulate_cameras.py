import argparse
import logging
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("camera_simulator")

stop_event = threading.Event()


def resolve_camera_images(camera_id: str, samples_dir: Path) -> List[Path]:
    """Finds image files for a camera, falling back to root sample images if needed."""
    cam_folder = samples_dir / camera_id
    images: List[Path] = []

    if cam_folder.is_dir():
        for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
            images.extend(cam_folder.glob(ext))

    # Fallback to general test-samples directory
    if not images and samples_dir.is_dir():
        for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
            images.extend(samples_dir.glob(ext))

    return sorted(list(set(images)))


def camera_worker(
    camera_id: str,
    server_url: str,
    images: List[Path],
    interval: float,
    jitter: float,
    loop: bool,
    max_frames: int,
    initial_battery: float,
    battery_drain: float,
    custom_stop_event: Optional[threading.Event] = None,
) -> None:
    """Thread target simulating an independent camera device."""
    current_stop_event = custom_stop_event if custom_stop_event is not None else stop_event

    if not images:
        logger.warning(f"[{camera_id}] No images found to simulate. Worker stopping.")
        return

    logger.info(f"[{camera_id}] Worker started. {len(images)} images loaded. Interval: {interval}s.")
    battery = initial_battery
    frame_idx = 0
    sent_count = 0

    while not current_stop_event.is_set():
        img_path = images[frame_idx]
        voltage = 3.30 + (0.90 * (battery / 100.0))

        upload_url = (
            f"{server_url.rstrip('/')}/api/v1/upload/{camera_id}"
            f"?battery={battery:.1f}&voltage={voltage:.2f}"
        )

        try:
            t0 = time.perf_counter()
            with open(img_path, "rb") as f:
                files = {"file": (img_path.name, f, "image/jpeg")}
                response = requests.post(upload_url, files=files, timeout=15.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"[{camera_id}] Frame {sent_count + 1} ({img_path.name}) -> 200 OK "
                    f"[Occupied: {data.get('occupied_spots')}/{data.get('total_spots')}] "
                    f"in {elapsed_ms:.1f}ms (Bat: {battery:.1f}%)"
                )
            else:
                logger.warning(
                    f"[{camera_id}] Upload {img_path.name} returned HTTP {response.status_code}: {response.text[:100]}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"[{camera_id}] Connection error to {server_url}: {e}")

        sent_count += 1
        battery = max(5.0, battery - battery_drain)

        if max_frames > 0 and sent_count >= max_frames:
            logger.info(f"[{camera_id}] Reached max frames ({max_frames}). Worker stopping.")
            break

        frame_idx += 1
        if frame_idx >= len(images):
            if loop:
                frame_idx = 0
                logger.info(f"[{camera_id}] Looping sequence back to start.")
            else:
                logger.info(f"[{camera_id}] Finished image sequence. Worker stopping.")
                break

        sleep_duration = interval + (random.uniform(0, jitter) if jitter > 0 else 0)
        if current_stop_event.wait(timeout=sleep_duration):
            break

    logger.info(f"[{camera_id}] Worker finished. Total frames sent: {sent_count}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parqueame Multi-Camera Hardware Simulator")
    parser.add_argument("--server-url", type=str, default="http://localhost:8000", help="FastAPI server URL")
    parser.add_argument("--cameras", type=str, default="cam_01,cam_02,cam_03,cam_04", help="Comma-separated camera IDs")
    parser.add_argument("--interval", type=float, default=30.0, help="Seconds between frames per camera")
    parser.add_argument("--jitter", type=float, default=1.0, help="Random interval jitter in seconds")
    parser.add_argument("--loop", action="store_true", help="Loop images indefinitely")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames per camera (0 = all)")
    parser.add_argument("--initial-battery", type=float, default=100.0, help="Starting battery percentage")
    parser.add_argument("--battery-drain", type=float, default=0.05, help="Battery %% drained per upload")
    parser.add_argument("--samples-dir", type=str, default="test-samples", help="Path to test-samples directory")

    args = parser.parse_args()

    camera_list = [c.strip() for c in args.cameras.split(",") if c.strip()]
    samples_dir = Path(args.samples_dir)

    def handle_sigint(sig, frame):
        logger.info("\nCaught interrupt signal! Stopping all camera simulation threads...")
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, handle_sigint)
    except (ValueError, AttributeError):
        pass

    logger.info("=" * 60)
    logger.info("Parqueame: Multi-Camera Hardware Simulator")
    logger.info(f"Target Server:  {args.server_url}")
    logger.info(f"Cameras:        {', '.join(camera_list)}")
    logger.info(f"Interval:       {args.interval}s (+/- {args.jitter}s jitter)")
    logger.info(f"Looping:        {args.loop}")
    logger.info("Press Ctrl+C to stop simulation gracefully.")
    logger.info("=" * 60)

    threads: List[threading.Thread] = []
    for cam_id in camera_list:
        cam_imgs = resolve_camera_images(cam_id, samples_dir)
        t = threading.Thread(
            target=camera_worker,
            kwargs={
                "camera_id": cam_id,
                "server_url": args.server_url,
                "images": cam_imgs,
                "interval": args.interval,
                "jitter": args.jitter,
                "loop": args.loop,
                "max_frames": args.max_frames,
                "initial_battery": args.initial_battery,
                "battery_drain": args.battery_drain,
            },
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Keep main thread alive waiting for workers or interrupt
    try:
        while any(t.is_alive() for t in threads) and not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    for t in threads:
        t.join(timeout=2.0)

    logger.info("Simulator shutdown complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
