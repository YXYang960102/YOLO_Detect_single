import argparse

import cv2
from ultralytics import YOLO

from camera_source import create_camera
from config import (
    CAMERA_INDEX,
    CAMERA_SOURCE,
    CONFIDENCE,
    DEPTH_DISTANCE_MODE,
    DEPTH_HOLE_DETECT_DEVIATION_MM,
    DEPTH_HOLE_DETECT_DIAMETER_TOLERANCE,
    DEPTH_HOLE_DETECT_DOWNSAMPLE,
    DEPTH_HOLE_DETECT_MAX_DIAMETER_MM,
    DEPTH_HOLE_DETECT_MIN_AREA_PX,
    DEPTH_HOLE_DETECT_MIN_CONFIDENCE,
    DEPTH_HOLE_DETECT_MIN_DIAMETER_MM,
    DEPTH_HOLE_INNER_RATIO,
    DEPTH_HOLE_RECESS_MM,
    DEPTH_MAD_SCALE,
    DEPTH_MAX_MM,
    DEPTH_MIN_MM,
    DEPTH_MIN_VALID_FRACTION,
    DEPTH_MIN_VALID_SAMPLES,
    DEPTH_RING_INNER_RATIO,
    DEPTH_RING_OUTER_RATIO,
    DEPTH_SMOOTHING,
    IMAGE_SIZE,
    MAX_SHOTS_PER_HOLE,
    MODEL_PATH,
    REALSENSE_ENABLE_EMITTER,
    REALSENSE_FPS,
    REALSENSE_HEIGHT,
    REALSENSE_SERIAL,
    REALSENSE_TIMEOUT_MS,
    REALSENSE_WARMUP_FRAMES,
    REALSENSE_WIDTH,
    RED_SCORE_THRESHOLD,
    RED_TARGET_IDS,
)
from depth_distance import DepthEstimator
from depth_hole_detector import DepthHoleDetector
from grid_tracker import GridTracker
from hole_grid import assign_ids, grid_memory_count, reset_grid_memory
from red_target import TargetStabilizer, select_red_target
from serial_tx import VisionSerial
from target_manager import TARGET_NONE, TargetManager


def build_holes(results):
    holes = []

    for result in results:
        for box in result.boxes:
            conf = float(box.conf[0])

            if conf < CONFIDENCE:
                continue

            x1, y1, x2, y2 = box.xyxy[0]
            x1 = int(x1)
            y1 = int(y1)
            x2 = int(x2)
            y2 = int(y2)
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            holes.append({
                "box": (x1, y1, x2, y2),
                "cx": cx,
                "cy": cy,
                "conf": conf,
                "red_score": 0.0,
                "ring_box": (x1, y1, x2, y2),
                "detector": "yolo",
            })

    return holes


def build_observation_holes(candidates):
    """Assigns display-only IDs to depth-only candidates for the debug overlay.

    Must never touch control-owned state: does not call assign_ids() (writes
    hole_grid's module-level grid memory), GridTracker.update(),
    select_red_target()/TargetStabilizer, or TargetManager.select(). A prior
    depth-only frame must not be able to bias a later YOLO frame's target
    selection. See docs/codex-handoff.md, 2026-08-19 Codex review.
    """
    holes = []
    for index, candidate in enumerate(candidates, start=1):
        hole = dict(candidate)
        hole["id"] = index
        hole["id_mode"] = "depth_observe"
        holes.append(hole)
    return holes


def resolve_distance_and_validity(
    target_hole,
    depth_mm,
    intrinsics,
    depth_estimator,
    distance_mode,
):
    """Returns (distance_mm, valid, depth_measurement) for the selected target.

    Depth-only detections (no RGB/YOLO evidence a real hole is there) are
    observation-only: ordinary sensor dropout looks identical to a hole to
    that detector, so they must never drive valid=1 / serial output until a
    depth-specific quality gate exists. See docs/codex-handoff.md, 2026-08-19
    Codex review.
    """
    if target_hole is None:
        return 0, 0, None

    if target_hole.get("detector") == "depth":
        return 0, 0, None

    if depth_mm is None:
        # Preserve the original webcam behavior when no depth stream exists:
        # target coordinates are still valid, distance is 0.
        return 0, 1, None

    depth_measurement = depth_estimator.measure(
        depth_mm,
        target_hole["box"],
        (target_hole["cx"], target_hole["cy"]),
        intrinsics,
        target_id=target_hole["id"],
    )
    if depth_measurement is None:
        return 0, 0, None

    distance_value = (
        depth_measurement.range_mm
        if distance_mode == "range"
        else depth_measurement.z_mm
    )
    return int(round(distance_value)), 1, depth_measurement


def draw_debug(
    frame,
    holes,
    target_hole,
    tx,
    ty,
    distance,
    valid,
    target_manager,
    depth_measurement=None,
):
    height, width = frame.shape[:2]
    frame_center_x = width // 2
    frame_center_y = height // 2

    cv2.line(frame, (frame_center_x, 0), (frame_center_x, height), (255, 255, 0), 1)
    cv2.line(frame, (0, frame_center_y), (width, frame_center_y), (255, 255, 0), 1)

    for hole in holes:
        hole_id = hole["id"]
        x1, y1, x2, y2 = hole["box"]
        is_target = target_hole is not None and hole_id == target_hole["id"]
        target_type = target_hole.get("target_type", TARGET_NONE) if is_target else TARGET_NONE

        if target_type == "red":
            color = (0, 0, 255)
        elif target_type == "normal":
            color = (255, 255, 0)
        else:
            color = (0, 255, 0)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        if hole_id in RED_TARGET_IDS and hole["red_score"] >= RED_SCORE_THRESHOLD:
            ring_x1, ring_y1, ring_x2, ring_y2 = hole["ring_box"]
            cv2.rectangle(
                frame,
                (ring_x1, ring_y1),
                (ring_x2, ring_y2),
                (0, 0, 255),
                2,
            )
        cv2.circle(frame, (hole["cx"], hole["cy"]), 5, (0, 255, 0), -1)
        cv2.putText(
            frame,
            f"ID:{hole_id} R:{hole['red_score']:.3f}",
            (hole["cx"] + 8, hole["cy"]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )

    target_id = target_hole["id"] if target_hole is not None else 0
    target_type = target_hole.get("target_type", TARGET_NONE) if target_hole else TARGET_NONE
    shots = target_manager.shots_for(target_id)
    id_mode = holes[0].get("id_mode", "-") if len(holes) > 0 else "-"
    detector_source = holes[0].get("detector", "-") if len(holes) > 0 else "-"
    cv2.putText(
        frame,
        f"Detected: {len(holes)}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2,
    )
    cv2.putText(
        frame,
        f"TX:{tx} TY:{ty} Dist:{distance}mm Target:{target_id} Type:{target_type} Valid:{valid}",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2,
    )
    cv2.putText(
        frame,
        f"Shots:{shots}/{MAX_SHOTS_PER_HOLE} Mem:{grid_memory_count()} "
        f"ID:{id_mode} Det:{detector_source}",
        (20, 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )

    if depth_measurement is not None:
        cv2.putText(
            frame,
            (
                f"X:{depth_measurement.x_mm:.0f} Y:{depth_measurement.y_mm:.0f} "
                f"Z:{depth_measurement.z_mm:.0f} Range:{depth_measurement.range_mm:.0f} mm "
                f"Src:{depth_measurement.source}"
            ),
            (20, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            (
                f"Depth samples:{depth_measurement.sample_count} "
                f"valid:{depth_measurement.valid_fraction:.2f}"
            ),
            (20, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )
    elif target_hole is not None:
        cv2.putText(
            frame,
            "Depth: invalid / unavailable",
            (20, 140),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 165, 255),
            2,
        )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL_PATH)
    parser.add_argument(
        "--source",
        choices=("realsense", "opencv"),
        default=CAMERA_SOURCE,
    )
    parser.add_argument("--camera", type=int, default=CAMERA_INDEX)
    parser.add_argument("--realsense-serial", default=REALSENSE_SERIAL)
    parser.add_argument("--width", type=int, default=REALSENSE_WIDTH)
    parser.add_argument("--height", type=int, default=REALSENSE_HEIGHT)
    parser.add_argument("--fps", type=int, default=REALSENSE_FPS)
    parser.add_argument(
        "--distance-mode",
        choices=("range", "z"),
        default=DEPTH_DISTANCE_MODE,
    )
    parser.add_argument("--serial", action="store_true")
    parser.add_argument("--serial-port", default=None)
    parser.add_argument("--no-display", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.model)
    camera = create_camera(
        source=args.source,
        camera_index=args.camera,
        width=args.width,
        height=args.height,
        fps=args.fps,
        serial_number=args.realsense_serial,
        timeout_ms=REALSENSE_TIMEOUT_MS,
        warmup_frames=REALSENSE_WARMUP_FRAMES,
        enable_emitter=REALSENSE_ENABLE_EMITTER,
    )
    camera.print_info()

    stabilizer = TargetStabilizer()
    grid_tracker = GridTracker()
    target_manager = TargetManager()
    depth_estimator = DepthEstimator(
        min_mm=DEPTH_MIN_MM,
        max_mm=DEPTH_MAX_MM,
        inner_ratio=DEPTH_RING_INNER_RATIO,
        outer_ratio=DEPTH_RING_OUTER_RATIO,
        min_valid_samples=DEPTH_MIN_VALID_SAMPLES,
        min_valid_fraction=DEPTH_MIN_VALID_FRACTION,
        mad_scale=DEPTH_MAD_SCALE,
        smoothing=DEPTH_SMOOTHING,
        hole_inner_ratio=DEPTH_HOLE_INNER_RATIO,
        hole_recess_mm=DEPTH_HOLE_RECESS_MM,
    )
    depth_hole_detector = DepthHoleDetector(
        min_mm=DEPTH_MIN_MM,
        max_mm=DEPTH_MAX_MM,
        downsample=DEPTH_HOLE_DETECT_DOWNSAMPLE,
        deviation_min_mm=DEPTH_HOLE_DETECT_DEVIATION_MM,
        min_diameter_mm=DEPTH_HOLE_DETECT_MIN_DIAMETER_MM,
        max_diameter_mm=DEPTH_HOLE_DETECT_MAX_DIAMETER_MM,
        diameter_tolerance=DEPTH_HOLE_DETECT_DIAMETER_TOLERANCE,
        min_area_px=DEPTH_HOLE_DETECT_MIN_AREA_PX,
        min_confidence=DEPTH_HOLE_DETECT_MIN_CONFIDENCE,
    )
    serial_tx = VisionSerial(port=args.serial_port, enabled=args.serial)

    try:
        while True:
            camera_frame = camera.read()

            if camera_frame is None:
                continue

            frame = camera_frame.color
            height, width = frame.shape[:2]
            frame_center_x = width // 2
            frame_center_y = height // 2

            # Original detection / grid / tracking / red-target / target-manager
            # algorithm is intentionally kept in the same order.
            results = model(frame, imgsz=IMAGE_SIZE, conf=CONFIDENCE, verbose=False)
            raw_holes = build_holes(results)

            if len(raw_holes) == 0 and camera_frame.depth_mm is not None:
                # Observation-only: depth-only candidates must never reach
                # control-owned state (grid memory, GridTracker, red
                # stabilizer, TargetManager, depth smoothing, shot counts),
                # so a noisy frame here can never bias a later YOLO frame's
                # target selection. Draw them, but always send the canonical
                # neutral packet. See docs/codex-handoff.md, 2026-08-19
                # Codex review.
                depth_candidates = depth_hole_detector.detect(
                    camera_frame.depth_mm, camera_frame.intrinsics
                )
                holes = build_observation_holes(depth_candidates)
                target_hole = None
                depth_measurement = None
                tx, ty, distance, target_id, valid = 0, 0, 0, 0, 0
            else:
                holes = assign_ids(raw_holes, width)
                holes = grid_tracker.update(holes, frame=frame)
                red_target = select_red_target(frame, holes, stabilizer)
                target_hole = target_manager.select(holes, red_target, width, height)

                target_id = target_hole["id"] if target_hole is not None else 0
                tx = target_hole["cx"] - frame_center_x if target_hole is not None else 0
                ty = target_hole["cy"] - frame_center_y if target_hole is not None else 0
                distance, valid, depth_measurement = resolve_distance_and_validity(
                    target_hole,
                    camera_frame.depth_mm,
                    camera_frame.intrinsics,
                    depth_estimator,
                    args.distance_mode,
                )

            serial_tx.send(tx, ty, distance, target_id, valid)

            if not args.no_display:
                draw_debug(
                    frame,
                    holes,
                    target_hole,
                    tx,
                    ty,
                    distance,
                    valid,
                    target_manager,
                    depth_measurement,
                )
                cv2.imshow("Coordinate System RGB-D", frame)

                key = cv2.waitKey(1) & 0xFF

                if key == 27:
                    break
                if key == ord("r"):
                    reset_grid_memory()
                    grid_tracker.reset()
                    target_manager.reset_tracking()
                    depth_estimator.reset()
                if key == ord("s") and target_hole is not None:
                    target_manager.record_shot(target_hole["id"])
                if key == ord("c"):
                    target_manager.reset_shots()
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
