import copy
import unittest

from depth_distance import DepthMeasurement
from grid_tracker import GridTracker
from hole_grid import assign_ids, grid_anchors, reset_grid_memory
from red_target import TargetStabilizer, select_red_target
from target_manager import TargetManager
from vision_main import build_observation_holes, resolve_distance_and_validity


BOX = (100, 100, 200, 200)


def make_yolo_hole(hole_id, cx, cy):
    return {
        "id": hole_id,
        "cx": cx,
        "cy": cy,
        "conf": 0.9,
        "box": (cx - 50, cy - 50, cx + 50, cy + 50),
        "red_score": 0.0,
        "ring_box": (cx - 50, cy - 50, cx + 50, cy + 50),
        "detector": "yolo",
    }


def make_depth_candidate(cx, cy):
    return {
        "box": (cx - 15, cy - 15, cx + 15, cy + 15),
        "cx": cx,
        "cy": cy,
        "conf": 0.75,
        "red_score": 0.0,
        "ring_box": (cx - 15, cy - 15, cx + 15, cy + 15),
        "detector": "depth",
    }


def make_hole(detector="yolo", hole_id=1):
    return {
        "id": hole_id,
        "cx": 150,
        "cy": 150,
        "box": BOX,
        "detector": detector,
    }


class FakeDepthEstimator:
    def __init__(self, measurement=None):
        self.measurement = measurement

    def measure(self, depth_mm, box, center, intrinsics, target_id=None):
        return self.measurement


class ResolveDistanceAndValidityTest(unittest.TestCase):
    def test_no_target_is_invalid(self):
        distance, valid, measurement = resolve_distance_and_validity(
            None, "depth-array", "intrinsics", FakeDepthEstimator(), "range"
        )

        self.assertEqual((distance, valid, measurement), (0, 0, None))

    def test_depth_only_detection_is_always_invalid(self):
        # Safety invariant: even when depth data and estimator would report a
        # confident measurement, a depth-only detection (no RGB/YOLO evidence)
        # must never produce valid=1. See docs/codex-handoff.md, 2026-08-19
        # Codex review — ordinary sensor dropout looks identical to a hole to
        # DepthHoleDetector.
        good_measurement = DepthMeasurement(
            z_mm=1500.0, range_mm=1500.0, x_mm=0.0, y_mm=0.0,
            valid_fraction=1.0, sample_count=200, source="ring",
        )
        estimator = FakeDepthEstimator(measurement=good_measurement)
        hole = make_hole(detector="depth")

        distance, valid, measurement = resolve_distance_and_validity(
            hole, "depth-array", "intrinsics", estimator, "range"
        )

        self.assertEqual((distance, valid, measurement), (0, 0, None))

    def test_webcam_without_depth_stream_is_valid_with_zero_distance(self):
        hole = make_hole(detector="yolo")

        distance, valid, measurement = resolve_distance_and_validity(
            hole, None, "intrinsics", FakeDepthEstimator(), "range"
        )

        self.assertEqual((distance, valid, measurement), (0, 1, None))

    def test_yolo_detection_uses_depth_measurement_when_available(self):
        measurement = DepthMeasurement(
            z_mm=1234.0, range_mm=1250.0, x_mm=10.0, y_mm=20.0,
            valid_fraction=0.9, sample_count=100, source="ring",
        )
        estimator = FakeDepthEstimator(measurement=measurement)
        hole = make_hole(detector="yolo")

        distance, valid, returned = resolve_distance_and_validity(
            hole, "depth-array", "intrinsics", estimator, "range"
        )

        self.assertEqual(distance, 1250)
        self.assertEqual(valid, 1)
        self.assertIs(returned, measurement)

    def test_yolo_detection_with_no_reliable_depth_is_invalid(self):
        hole = make_hole(detector="yolo")

        distance, valid, measurement = resolve_distance_and_validity(
            hole, "depth-array", "intrinsics", FakeDepthEstimator(measurement=None), "range"
        )

        self.assertEqual((distance, valid, measurement), (0, 0, None))


class BuildObservationHolesTest(unittest.TestCase):
    def test_assigns_sequential_display_ids_and_keeps_detector_tag(self):
        candidates = [make_depth_candidate(400, 360), make_depth_candidate(880, 360)]

        holes = build_observation_holes(candidates)

        self.assertEqual([h["id"] for h in holes], [1, 2])
        self.assertTrue(all(h["id_mode"] == "depth_observe" for h in holes))
        self.assertTrue(all(h["detector"] == "depth" for h in holes))

    def test_does_not_mutate_input_candidates(self):
        candidates = [make_depth_candidate(400, 360)]
        original = copy.deepcopy(candidates)

        build_observation_holes(candidates)

        self.assertEqual(candidates, original)


class DepthObservationStateIsolationTest(unittest.TestCase):
    # Regression test for the 2026-08-19 Codex review: depth-only frames must
    # never bias a later YOLO frame's target selection through shared,
    # control-owned state (hole_grid's module-level grid memory, GridTracker,
    # TargetStabilizer, TargetManager).

    FRAME_W, FRAME_H = 1280, 720

    def test_depth_observation_frames_leave_control_state_untouched(self):
        reset_grid_memory()
        self.assertEqual(grid_anchors, {})

        grid_tracker = GridTracker()
        stabilizer = TargetStabilizer()
        target_manager = TargetManager()

        depth_candidates = [make_depth_candidate(400, 360), make_depth_candidate(880, 360)]
        for _ in range(5):
            build_observation_holes(depth_candidates)

        # None of the control-owned objects were ever called with the
        # observation-only path, so they must still be at their fresh state.
        self.assertEqual(grid_anchors, {})
        self.assertEqual(grid_tracker.positions, {})
        self.assertIsNone(target_manager.locked_target_id)
        self.assertIsNone(target_manager.candidate_target_id)
        self.assertEqual(target_manager.candidate_count, 0)

    def test_prior_depth_observation_does_not_change_next_yolo_selection(self):
        # Hole 10 is closer to frame center than hole 11, so a cleanly
        # evaluated TargetManager should prefer it.
        clean_holes = [make_yolo_hole(10, 660, 360), make_yolo_hole(11, 900, 360)]

        def run_yolo_frames(manager):
            target = None
            for _ in range(3):
                target = manager.select(clean_holes, None, self.FRAME_W, self.FRAME_H)
            return target["id"] if target else None

        reset_grid_memory()
        contaminated_manager = TargetManager()
        depth_candidates = [make_depth_candidate(400, 360), make_depth_candidate(880, 360)]
        for _ in range(5):
            build_observation_holes(depth_candidates)  # observation-only, no side effects
        contaminated_result = run_yolo_frames(contaminated_manager)

        reset_grid_memory()
        fresh_manager = TargetManager()
        fresh_result = run_yolo_frames(fresh_manager)

        self.assertEqual(contaminated_result, fresh_result)
        self.assertEqual(fresh_result, 10)


if __name__ == "__main__":
    unittest.main()
