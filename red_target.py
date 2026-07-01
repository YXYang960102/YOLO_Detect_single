import cv2
import numpy as np

from config import (
    INNER_SCALE,
    RED_SCORE_THRESHOLD,
    RING_SCALE,
    TARGET_STABLE_FRAMES,
)


def clip_box(x1, y1, x2, y2, width, height):
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(0, min(width - 1, int(x2)))
    y2 = max(0, min(height - 1, int(y2)))
    return x1, y1, x2, y2


def red_ring_score(frame, hole):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = hole["box"]
    cx = hole["cx"]
    cy = hole["cy"]
    box_w = x2 - x1
    box_h = y2 - y1

    outer_w = box_w * RING_SCALE
    outer_h = box_h * RING_SCALE
    ox1 = cx - outer_w / 2
    oy1 = cy - outer_h / 2
    ox2 = cx + outer_w / 2
    oy2 = cy + outer_h / 2
    ox1, oy1, ox2, oy2 = clip_box(ox1, oy1, ox2, oy2, width, height)

    inner_w = box_w * INNER_SCALE
    inner_h = box_h * INNER_SCALE
    ix1 = cx - inner_w / 2
    iy1 = cy - inner_h / 2
    ix2 = cx + inner_w / 2
    iy2 = cy + inner_h / 2
    ix1, iy1, ix2, iy2 = clip_box(ix1, iy1, ix2, iy2, width, height)

    if ox2 <= ox1 or oy2 <= oy1:
        return 0.0, (ox1, oy1, ox2, oy2)

    roi = frame[oy1:oy2, ox1:ox2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    lower_red_1 = np.array([0, 120, 130])
    upper_red_1 = np.array([10, 255, 255])
    lower_red_2 = np.array([170, 120, 130])
    upper_red_2 = np.array([180, 255, 255])

    red_mask_1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
    red_mask_2 = cv2.inRange(hsv, lower_red_2, upper_red_2)
    red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)

    ring_mask = np.full(red_mask.shape, 255, dtype=np.uint8)
    inner_x1 = max(0, ix1 - ox1)
    inner_y1 = max(0, iy1 - oy1)
    inner_x2 = min(red_mask.shape[1], ix2 - ox1)
    inner_y2 = min(red_mask.shape[0], iy2 - oy1)
    ring_mask[inner_y1:inner_y2, inner_x1:inner_x2] = 0

    ring_red = cv2.bitwise_and(red_mask, ring_mask)
    ring_area = max(1, cv2.countNonZero(ring_mask))
    score = cv2.countNonZero(ring_red) / ring_area
    return score, (ox1, oy1, ox2, oy2)


class TargetStabilizer:
    def __init__(self, stable_frames=TARGET_STABLE_FRAMES):
        self.stable_frames = stable_frames
        self.stable_target_id = None
        self.candidate_target_id = None
        self.candidate_count = 0

    def update(self, target_id):
        if target_id is None:
            self.candidate_target_id = None
            self.candidate_count = 0
            self.stable_target_id = None
            return None

        if target_id == self.candidate_target_id:
            self.candidate_count += 1
        else:
            self.candidate_target_id = target_id
            self.candidate_count = 1

        if self.candidate_count >= self.stable_frames:
            self.stable_target_id = self.candidate_target_id

        return self.stable_target_id


def select_red_target(frame, holes, stabilizer):
    best_red_hole = None

    for hole in holes:
        score, ring_box = red_ring_score(frame, hole)
        hole["red_score"] = score
        hole["ring_box"] = ring_box

        if score >= RED_SCORE_THRESHOLD:
            if best_red_hole is None or score > best_red_hole["red_score"]:
                best_red_hole = hole

    raw_target_id = best_red_hole["id"] if best_red_hole is not None else None
    target_id = stabilizer.update(raw_target_id)

    for hole in holes:
        if hole["id"] == target_id:
            return hole

    return None
