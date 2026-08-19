from math import isfinite
from typing import List, Optional

import cv2
import numpy as np

from depth_distance import CameraIntrinsics


class DepthHoleDetector:
    """Finds candidate hole positions directly from the depth image.

    Fallback for when YOLO finds nothing (too far, hole too small in frame,
    poor lighting for RGB). A hole's net funnel reads farther than the
    surrounding board face, or returns no depth at all (dark mesh material) --
    both count as evidence. Candidates are shaped like build_holes() output
    so they can go straight into the existing assign_ids()/grid_tracker/
    red_target/target_manager pipeline unchanged.
    """

    def __init__(
        self,
        min_mm=200,
        max_mm=8000,
        downsample=8,
        deviation_min_mm=25.0,
        min_diameter_mm=180.0,
        max_diameter_mm=420.0,
        diameter_tolerance=0.45,
        min_area_px=20,
        min_fill_ratio=0.5,
        min_aspect_ratio=0.4,
        morph_kernel=3,
        min_confidence=0.55,
    ):
        if min_mm < 0 or max_mm <= min_mm:
            raise ValueError("invalid depth range")
        if downsample < 1:
            raise ValueError("downsample must be >= 1")
        if not isfinite(deviation_min_mm) or deviation_min_mm <= 0:
            raise ValueError("deviation_min_mm must be finite and positive")
        if min_diameter_mm <= 0 or max_diameter_mm <= min_diameter_mm:
            raise ValueError("max_diameter_mm must be larger than min_diameter_mm")
        if diameter_tolerance < 0:
            raise ValueError("diameter_tolerance must be non-negative")
        if min_area_px < 1:
            raise ValueError("min_area_px must be positive")
        if not (0.0 <= min_confidence <= 1.0):
            raise ValueError("min_confidence must be within [0, 1]")

        self.min_mm = float(min_mm)
        self.max_mm = float(max_mm)
        self.downsample = int(downsample)
        self.deviation_min_mm = float(deviation_min_mm)
        self.min_diameter_mm = float(min_diameter_mm)
        self.max_diameter_mm = float(max_diameter_mm)
        self.diameter_tolerance = float(diameter_tolerance)
        self.min_area_px = int(min_area_px)
        self.min_fill_ratio = float(min_fill_ratio)
        self.min_aspect_ratio = float(min_aspect_ratio)
        self.morph_kernel = int(morph_kernel)
        self.min_confidence = float(min_confidence)

    def detect(
        self,
        depth_mm,
        intrinsics: Optional[CameraIntrinsics],
    ) -> List[dict]:
        if depth_mm is None or intrinsics is None:
            return []
        if depth_mm.ndim != 2:
            raise ValueError("depth_mm must be a two-dimensional array")
        if intrinsics.fx <= 0:
            raise ValueError("camera focal length must be positive")

        valid_mask = (
            np.isfinite(depth_mm)
            & (depth_mm >= self.min_mm)
            & (depth_mm <= self.max_mm)
        )
        board_plane_mm = self._board_plane_estimate(depth_mm, valid_mask)

        deviation = depth_mm - board_plane_mm
        far_mask = valid_mask & (deviation >= self.deviation_min_mm)
        hole_mask = ((far_mask | ~valid_mask).astype(np.uint8)) * 255

        if self.morph_kernel > 1:
            kernel = np.ones((self.morph_kernel, self.morph_kernel), np.uint8)
            hole_mask = cv2.morphologyEx(hole_mask, cv2.MORPH_OPEN, kernel)
            hole_mask = cv2.morphologyEx(hole_mask, cv2.MORPH_CLOSE, kernel)

        num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            hole_mask, connectivity=8
        )

        height, width = depth_mm.shape
        candidates = []

        for label in range(1, num_labels):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < self.min_area_px:
                continue

            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            w = int(stats[label, cv2.CC_STAT_WIDTH])
            h = int(stats[label, cv2.CC_STAT_HEIGHT])
            if w <= 0 or h <= 0:
                continue

            fill_ratio = area / float(w * h)
            aspect_ratio = min(w, h) / float(max(w, h))
            if fill_ratio < self.min_fill_ratio or aspect_ratio < self.min_aspect_ratio:
                continue

            local_distance_mm = self._local_reference_distance(
                board_plane_mm, x, y, w, h, width, height
            )
            if local_distance_mm is None:
                continue

            expected_px_min = self.min_diameter_mm * intrinsics.fx / local_distance_mm
            expected_px_max = self.max_diameter_mm * intrinsics.fx / local_distance_mm
            low = expected_px_min * (1.0 - self.diameter_tolerance)
            high = expected_px_max * (1.0 + self.diameter_tolerance)
            observed_px = (w + h) / 2.0
            if not (low <= observed_px <= high):
                continue

            cx, cy = centroids[label]
            conf = self._confidence(
                observed_px, expected_px_min, expected_px_max, fill_ratio
            )

            candidates.append({
                "box": (x, y, x + w, y + h),
                "cx": int(round(cx)),
                "cy": int(round(cy)),
                "conf": conf,
                "red_score": 0.0,
                "ring_box": (x, y, x + w, y + h),
                "detector": "depth",
            })

        return candidates

    def _confidence(self, observed_px, expected_px_min, expected_px_max, fill_ratio):
        diameter_mid_px = 0.5 * (expected_px_min + expected_px_max)
        diameter_spread_px = max(1.0, 0.5 * (expected_px_max - expected_px_min))
        diameter_score = max(
            0.0, 1.0 - abs(observed_px - diameter_mid_px) / diameter_spread_px
        )
        shape_score = min(1.0, fill_ratio / 0.9)
        conf = self.min_confidence + (0.95 - self.min_confidence) * (
            0.5 * diameter_score + 0.5 * shape_score
        )
        return float(min(conf, 0.95))

    def _board_plane_estimate(self, depth_mm, valid_mask):
        height, width = depth_mm.shape
        down_w = max(1, width // self.downsample)
        down_h = max(1, height // self.downsample)

        fill_value = (
            float(np.median(depth_mm[valid_mask]))
            if np.any(valid_mask)
            else self.min_mm
        )
        filled = np.where(valid_mask, depth_mm, fill_value).astype(np.float32)

        small = cv2.resize(filled, (down_w, down_h), interpolation=cv2.INTER_AREA)
        ksize = 5 if min(down_w, down_h) >= 5 else 3
        if min(down_w, down_h) >= 3:
            small = cv2.medianBlur(small, ksize)

        return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)

    def _local_reference_distance(self, board_plane_mm, x, y, w, h, width, height):
        cx = min(max(int(x + w / 2), 0), width - 1)
        cy = min(max(int(y + h / 2), 0), height - 1)
        value = float(board_plane_mm[cy, cx])
        if not isfinite(value) or value < self.min_mm or value > self.max_mm:
            return None
        return value
