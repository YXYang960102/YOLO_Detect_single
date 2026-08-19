import unittest

import numpy as np

from depth_distance import CameraIntrinsics
from depth_hole_detector import DepthHoleDetector


FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
BOARD_MM = 6000.0
HOLE_DIAMETER_MM = 200.0
INTRINSICS = CameraIntrinsics(
    fx=900.0, fy=900.0, ppx=640.0, ppy=360.0, width=FRAME_WIDTH, height=FRAME_HEIGHT
)
HOLE_CENTERS = [(400, 360), (880, 360)]
HOLE_RADIUS_PX = 15


def _hole_mask(cx, cy, radius):
    yy, xx = np.ogrid[0:FRAME_HEIGHT, 0:FRAME_WIDTH]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2


def make_board(hole_value=None, hole_centers=HOLE_CENTERS):
    depth = np.full((FRAME_HEIGHT, FRAME_WIDTH), BOARD_MM, dtype=np.float32)
    if hole_value is not None:
        for cx, cy in hole_centers:
            depth[_hole_mask(cx, cy, HOLE_RADIUS_PX)] = hole_value
    return depth


def centers_of(candidates):
    return sorted((c["cx"], c["cy"]) for c in candidates)


class DepthHoleDetectorTest(unittest.TestCase):
    def test_detects_holes_as_far_deviation(self):
        detector = DepthHoleDetector()
        depth = make_board(hole_value=BOARD_MM + 100.0)

        candidates = detector.detect(depth, INTRINSICS)

        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            self.assertGreaterEqual(candidate["conf"], 0.55)
            self.assertEqual(candidate["detector"], "depth")

        found = centers_of(candidates)
        for (ex, ey), (fx, fy) in zip(sorted(HOLE_CENTERS), found):
            self.assertLess(abs(ex - fx), 5)
            self.assertLess(abs(ey - fy), 5)

    def test_detects_holes_as_invalid_region(self):
        detector = DepthHoleDetector()
        depth = make_board(hole_value=np.nan)

        candidates = detector.detect(depth, INTRINSICS)

        self.assertEqual(len(candidates), 2)

    def test_no_false_positive_on_flat_board(self):
        detector = DepthHoleDetector()
        depth = make_board(hole_value=None)

        candidates = detector.detect(depth, INTRINSICS)

        self.assertEqual(candidates, [])

    def test_rejects_blob_outside_expected_diameter_range(self):
        detector = DepthHoleDetector()
        depth = make_board(hole_value=None)
        # A blob far larger than any configured hole diameter at this range.
        depth[200:520, 550:730] = BOARD_MM + 150.0

        candidates = detector.detect(depth, INTRINSICS)

        self.assertEqual(candidates, [])

    def test_returns_empty_without_depth_or_intrinsics(self):
        detector = DepthHoleDetector()
        depth = make_board(hole_value=BOARD_MM + 100.0)

        self.assertEqual(detector.detect(None, INTRINSICS), [])
        self.assertEqual(detector.detect(depth, None), [])

    def test_rejects_invalid_diameter_range(self):
        with self.assertRaises(ValueError):
            DepthHoleDetector(min_diameter_mm=400.0, max_diameter_mm=200.0)

    def test_rejects_non_finite_deviation_threshold(self):
        for value in (float("nan"), float("inf"), 0.0, -5.0):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    DepthHoleDetector(deviation_min_mm=value)


if __name__ == "__main__":
    unittest.main()
