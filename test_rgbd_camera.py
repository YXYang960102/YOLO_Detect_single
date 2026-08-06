"""Read Solomon/RealSense RGB, aligned depth, and camera parameters without YOLO."""

import argparse
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from camera_source import RealSenseCamera
from config import (
    DEPTH_DISPLAY_MAX_MM,
    DEPTH_MAX_MM,
    DEPTH_MIN_MM,
    REALSENSE_ENABLE_EMITTER,
    REALSENSE_FPS,
    REALSENSE_HEIGHT,
    REALSENSE_SERIAL,
    REALSENSE_TIMEOUT_MS,
    REALSENSE_WARMUP_FRAMES,
    REALSENSE_WIDTH,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=REALSENSE_WIDTH)
    parser.add_argument("--height", type=int, default=REALSENSE_HEIGHT)
    parser.add_argument("--fps", type=int, default=REALSENSE_FPS)
    parser.add_argument("--serial", default=REALSENSE_SERIAL)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--frames", type=int, default=0)
    return parser.parse_args()


def robust_pixel_depth(depth_mm, x, y, radius=4):
    height, width = depth_mm.shape
    left = max(0, x - radius)
    right = min(width, x + radius + 1)
    top = max(0, y - radius)
    bottom = min(height, y + radius + 1)
    roi = depth_mm[top:bottom, left:right]
    valid = roi[
        np.isfinite(roi)
        & (roi >= DEPTH_MIN_MM)
        & (roi <= DEPTH_MAX_MM)
    ]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def depth_to_color(depth_mm):
    clipped = np.clip(depth_mm, 0, DEPTH_DISPLAY_MAX_MM)
    scaled = cv2.convertScaleAbs(
        clipped,
        alpha=255.0 / max(1.0, float(DEPTH_DISPLAY_MAX_MM)),
    )
    return cv2.applyColorMap(scaled, cv2.COLORMAP_JET)


def save_frame(frame):
    output = Path("captures")
    output.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rgb_path = output / f"rgb_{stamp}.png"
    depth_png_path = output / f"depth_mm_{stamp}.png"
    depth_npy_path = output / f"depth_mm_{stamp}.npy"
    cv2.imwrite(str(rgb_path), frame.color)
    cv2.imwrite(
        str(depth_png_path),
        np.clip(frame.depth_mm, 0, 65535).astype(np.uint16),
    )
    np.save(depth_npy_path, frame.depth_mm)
    print(f"Saved {rgb_path}, {depth_png_path}, {depth_npy_path}")


def main():
    args = parse_args()
    camera = RealSenseCamera(
        width=args.width,
        height=args.height,
        fps=args.fps,
        serial_number=args.serial,
        timeout_ms=REALSENSE_TIMEOUT_MS,
        warmup_frames=REALSENSE_WARMUP_FRAMES,
        enable_emitter=REALSENSE_ENABLE_EMITTER,
    )
    camera.print_info()

    selected = [args.width // 2, args.height // 2]

    def on_mouse(event, x, y, _flags, _userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            selected[0] = x
            selected[1] = y

    if not args.no_display:
        cv2.namedWindow("RGB")
        cv2.setMouseCallback("RGB", on_mouse)

    frame_count = 0
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue

            frame_count += 1
            x = min(max(selected[0], 0), frame.color.shape[1] - 1)
            y = min(max(selected[1], 0), frame.color.shape[0] - 1)
            distance = robust_pixel_depth(frame.depth_mm, x, y)

            if args.no_display:
                if frame_count == 1 or frame_count % 30 == 0:
                    print(
                        f"frame={frame_count} pixel=({x},{y}) "
                        f"depth_mm={distance if distance is not None else 'invalid'}"
                    )
            else:
                rgb = frame.color.copy()
                cv2.drawMarker(
                    rgb,
                    (x, y),
                    (0, 255, 255),
                    cv2.MARKER_CROSS,
                    24,
                    2,
                )
                label = (
                    f"({x},{y}) {distance:.0f} mm"
                    if distance is not None
                    else f"({x},{y}) invalid depth"
                )
                cv2.putText(
                    rgb,
                    label,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 255),
                    2,
                )
                depth_color = depth_to_color(frame.depth_mm)
                cv2.imshow("RGB", rgb)
                cv2.imshow("Aligned Depth", depth_color)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord("s"):
                    save_frame(frame)

            if args.frames > 0 and frame_count >= args.frames:
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
