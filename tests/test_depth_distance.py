import unittest

import numpy as np

from depth_distance import CameraIntrinsics, DepthEstimator


FRAME_WIDTH = 400
FRAME_HEIGHT = 400
BOX = (150, 150, 250, 250)
CENTER = (200, 200)
INTRINSICS = CameraIntrinsics(
    fx=600.0, fy=600.0, ppx=200.0, ppy=200.0, width=FRAME_WIDTH, height=FRAME_HEIGHT
)


def _radius_grid():
    x1, y1, x2, y2 = BOX
    cx, cy = CENTER
    rx = (x2 - x1) / 2.0
    ry = (y2 - y1) / 2.0
    yy, xx = np.ogrid[0:FRAME_HEIGHT, 0:FRAME_WIDTH]
    return np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)


def make_depth(ring_mm=None, hole_mm=None, fill_mm=5000.0):
    depth = np.full((FRAME_HEIGHT, FRAME_WIDTH), fill_mm, dtype=np.float32)
    radius = _radius_grid()

    if ring_mm is not None:
        depth[(radius >= 0.60) & (radius <= 1.10)] = ring_mm
    if hole_mm is not None:
        depth[radius <= 0.35] = hole_mm
    return depth


def invalidate_ring(depth):
    depth[(_radius_grid() >= 0.60) & (_radius_grid() <= 1.10)] = np.nan
    return depth


class DepthEstimatorTest(unittest.TestCase):
    def test_rejects_invalid_hole_sampling_ratio(self):
        for ratio in (0.0, 0.60, float("nan")):
            with self.subTest(ratio=ratio):
                with self.assertRaises(ValueError):
                    DepthEstimator(hole_inner_ratio=ratio)

    def test_rejects_non_finite_hole_recess(self):
        for recess_mm in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(recess_mm=recess_mm):
                with self.assertRaises(ValueError):
                    DepthEstimator(hole_recess_mm=recess_mm)

    def test_ring_measurement_is_used_when_available(self):
        estimator = DepthEstimator(hole_recess_mm=50.0)
        depth = make_depth(ring_mm=1000.0, hole_mm=1200.0)

        measurement = estimator.measure(depth, BOX, CENTER, INTRINSICS)

        self.assertIsNotNone(measurement)
        self.assertEqual(measurement.source, "ring")
        self.assertAlmostEqual(measurement.z_mm, 1000.0, places=3)

    def test_falls_back_to_hole_depth_when_ring_is_invalid(self):
        estimator = DepthEstimator(hole_recess_mm=50.0)
        depth = invalidate_ring(make_depth(hole_mm=1200.0))

        measurement = estimator.measure(depth, BOX, CENTER, INTRINSICS)

        self.assertIsNotNone(measurement)
        self.assertEqual(measurement.source, "hole_fallback")
        # z_board = z_hole - recess = 1200 - 50 = 1150
        self.assertAlmostEqual(measurement.z_mm, 1150.0, places=3)

    def test_fallback_disabled_without_calibrated_recess(self):
        estimator = DepthEstimator(hole_recess_mm=None)
        depth = invalidate_ring(make_depth(hole_mm=1200.0))

        measurement = estimator.measure(depth, BOX, CENTER, INTRINSICS)

        self.assertIsNone(measurement)

    def test_returns_none_when_both_ring_and_hole_are_invalid(self):
        estimator = DepthEstimator(hole_recess_mm=50.0)
        depth = np.full((FRAME_HEIGHT, FRAME_WIDTH), np.nan, dtype=np.float32)

        measurement = estimator.measure(depth, BOX, CENTER, INTRINSICS)

        self.assertIsNone(measurement)

    # Dashboard ring view (2026-10-28): share of usable ring pixels and the
    # 8 sectors with depth (0 = right, clockwise on screen, y down).
    def test_ring_coverage_full_and_none(self):
        estimator = DepthEstimator(inner_ratio=0.60, outer_ratio=1.10)
        self.assertEqual(estimator.ring_coverage(make_depth(), BOX), (100, 0xFF))
        depth = invalidate_ring(make_depth())
        self.assertEqual(estimator.ring_coverage(depth, BOX), (0, 0))
        self.assertIsNone(estimator.ring_coverage(None, BOX))
        self.assertIsNone(estimator.ring_coverage(depth, None))

    def test_ring_coverage_right_half_missing(self):
        estimator = DepthEstimator(inner_ratio=0.60, outer_ratio=1.10)
        depth = make_depth()
        depth[:, CENTER[0] + 1:] = 0.0          # no depth right of center
        percent, mask = estimator.ring_coverage(depth, BOX)
        self.assertTrue(48 <= percent <= 52)
        # Left side (sectors 3, 4, 5) has depth; right (7, 0, 1) has none;
        # straight up / down (6, 2) are split in half.
        self.assertEqual(mask & 0b10111011, 0b00111000)
        depth = make_depth()
        depth[CENTER[1] + 1:, :] = np.nan        # nothing below center
        _, mask = estimator.ring_coverage(depth, BOX)
        self.assertEqual(mask & 0b11101110, 0b11100000)   # 5, 6, 7 (above) only

    def test_ring_coverage_clipped_by_the_frame_edge(self):
        estimator = DepthEstimator(inner_ratio=0.60, outer_ratio=1.10)
        box = (340, 150, 440, 250)              # right part outside the image
        percent, mask = estimator.ring_coverage(make_depth(), box)
        self.assertEqual(percent, 100)           # of the pixels in the image
        self.assertEqual(mask & 1, 0)            # sector 0 has no pixels
        self.assertEqual(mask & (1 << 4), 1 << 4)


if __name__ == "__main__":
    unittest.main()
