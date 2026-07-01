import argparse

import cv2
from ultralytics import YOLO

from config import CAMERA_INDEX, CONFIDENCE, IMAGE_SIZE, MODEL_PATH
from hole_grid import assign_ids
from red_target import TargetStabilizer, select_red_target
from serial_tx import VisionSerial


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
            })

    return holes


def draw_debug(frame, holes, target_hole, tx, ty, valid):
    height, width = frame.shape[:2]
    frame_center_x = width // 2
    frame_center_y = height // 2

    cv2.line(frame, (frame_center_x, 0), (frame_center_x, height), (255, 255, 0), 1)
    cv2.line(frame, (0, frame_center_y), (width, frame_center_y), (255, 255, 0), 1)

    for hole in holes:
        hole_id = hole["id"]
        x1, y1, x2, y2 = hole["box"]
        ring_x1, ring_y1, ring_x2, ring_y2 = hole["ring_box"]
        is_target = target_hole is not None and hole_id == target_hole["id"]
        color = (0, 0, 255) if is_target else (0, 255, 0)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.rectangle(frame, (ring_x1, ring_y1), (ring_x2, ring_y2), (0, 0, 180), 1)
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
        f"TX:{tx} TY:{ty} Target:{target_id} Valid:{valid}",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=CAMERA_INDEX)
    parser.add_argument("--serial", action="store_true")
    parser.add_argument("--serial-port", default=None)
    parser.add_argument("--no-display", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(args.camera)
    stabilizer = TargetStabilizer()
    serial_tx = VisionSerial(port=args.serial_port, enabled=args.serial)

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        height, width = frame.shape[:2]
        frame_center_x = width // 2
        frame_center_y = height // 2

        results = model(frame, imgsz=IMAGE_SIZE, conf=CONFIDENCE, verbose=False)
        holes = assign_ids(build_holes(results), width)
        target_hole = select_red_target(frame, holes, stabilizer)

        if target_hole is not None:
            tx = target_hole["cx"] - frame_center_x
            ty = target_hole["cy"] - frame_center_y
            distance = 0
            target_id = target_hole["id"]
            valid = 1
        else:
            tx = 0
            ty = 0
            distance = 0
            target_id = 0
            valid = 0

        serial_tx.send(tx, ty, distance, target_id, valid)

        if not args.no_display:
            draw_debug(frame, holes, target_hole, tx, ty, valid)
            cv2.imshow("Coordinate System", frame)

            if cv2.waitKey(1) == 27:
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
