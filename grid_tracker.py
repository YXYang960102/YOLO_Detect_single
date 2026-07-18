import cv2
import numpy as np

from config import (
    GRID_TRACKER_MAX_ERROR_RATIO,
    GRID_TRACKER_MIN_MATCHES,
    ROWS,
    COLS,
)


class GridTracker:
    def __init__(
        self,
        min_matches=GRID_TRACKER_MIN_MATCHES,
        max_error_ratio=GRID_TRACKER_MAX_ERROR_RATIO,
    ):
        self.min_matches = min_matches
        self.max_error_ratio = max_error_ratio
        self.positions = {}
        self.sizes = {}
        self.previous_gray = None

    def reset(self):
        self.positions.clear()
        self.sizes.clear()
        self.previous_gray = None

    def is_initialized(self):
        return len(self.positions) == ROWS * COLS

    def _initialize(self, holes):
        by_id = {hole.get("id"): hole for hole in holes}
        expected_ids = set(range(1, ROWS * COLS + 1))

        if set(by_id) != expected_ids:
            return False

        self.positions = {
            hole_id: np.array(
                [by_id[hole_id]["cx"], by_id[hole_id]["cy"]],
                dtype=np.float32,
            )
            for hole_id in expected_ids
        }
        self.sizes = {
            hole_id: self._hole_diagonal(by_id[hole_id])
            for hole_id in expected_ids
        }
        return True

    @staticmethod
    def _hole_diagonal(hole):
        x1, y1, x2, y2 = hole["box"]
        return max(1.0, float(np.hypot(x2 - x1, y2 - y1)))

    def _match_for_shift(self, holes, shift, max_error):
        edges = []

        for hole_index, hole in enumerate(holes):
            point = np.array([hole["cx"], hole["cy"]], dtype=np.float32)
            current_size = self._hole_diagonal(hole)

            for hole_id, previous in self.positions.items():
                error = float(np.linalg.norm(point - (previous + shift)))
                if error <= max_error:
                    size_error = abs(np.log(current_size / self.sizes[hole_id]))
                    combined_error = error + size_error * max_error
                    edges.append((combined_error, error, size_error, hole_index, hole_id))

        matches = []
        used_holes = set()
        used_ids = set()

        for _, error, size_error, hole_index, hole_id in sorted(edges):
            if hole_index in used_holes or hole_id in used_ids:
                continue

            used_holes.add(hole_index)
            used_ids.add(hole_id)
            matches.append((hole_index, hole_id, error, size_error))

        return matches

    def _best_translation(self, holes, max_error, motion_hint=None):
        current_points = [
            np.array([hole["cx"], hole["cy"]], dtype=np.float32)
            for hole in holes
        ]
        candidates = [np.zeros(2, dtype=np.float32)]

        for previous in self.positions.values():
            for current in current_points:
                candidates.append(current - previous)

        best_shift = None
        best_matches = []
        best_key = None

        for shift in candidates:
            matches = self._match_for_shift(holes, shift, max_error)
            if not matches:
                continue

            mean_error = sum(match[2] for match in matches) / len(matches)
            mean_size_error = sum(match[3] for match in matches) / len(matches)
            shift_size = float(np.linalg.norm(shift))
            motion_error = (
                float(np.linalg.norm(shift - motion_hint))
                if motion_hint is not None
                else shift_size
            )
            key = (
                -len(matches),
                mean_size_error,
                motion_error,
                mean_error,
                shift_size,
            )

            if best_key is None or key < best_key:
                best_key = key
                best_shift = shift
                best_matches = matches

        return best_shift, best_matches

    def _estimate_frame_motion(self, frame):
        if frame is None:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        previous = self.previous_gray
        self.previous_gray = gray

        if previous is None or previous.shape != gray.shape:
            return None

        points = cv2.goodFeaturesToTrack(
            previous,
            maxCorners=120,
            qualityLevel=0.01,
            minDistance=10,
        )
        if points is None or len(points) < 6:
            return None

        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous,
            gray,
            points,
            None,
        )
        if next_points is None or status is None:
            return None

        valid = status.reshape(-1) == 1
        if int(np.count_nonzero(valid)) < 6:
            return None

        deltas = next_points.reshape(-1, 2)[valid] - points.reshape(-1, 2)[valid]
        median = np.median(deltas, axis=0)
        deviations = np.linalg.norm(deltas - median, axis=1)
        cutoff = max(2.0, float(np.median(deviations)) * 3.0)
        inliers = deltas[deviations <= cutoff]

        if len(inliers) < 6:
            return None

        return np.median(inliers, axis=0).astype(np.float32)

    def update(self, holes, frame=None, motion_hint=None):
        frame_motion = self._estimate_frame_motion(frame)
        if motion_hint is None:
            motion_hint = frame_motion
        elif not isinstance(motion_hint, np.ndarray):
            motion_hint = np.array(motion_hint, dtype=np.float32)

        if not holes:
            return []

        if not self.is_initialized():
            self._initialize(holes)
            return holes

        if len(holes) == ROWS * COLS and self._initialize(holes):
            return holes

        diagonals = []
        for hole in holes:
            x1, y1, x2, y2 = hole["box"]
            diagonals.append(np.hypot(x2 - x1, y2 - y1))

        max_error = max(15.0, float(np.median(diagonals)) * self.max_error_ratio)
        shift, matches = self._best_translation(holes, max_error, motion_hint)

        if shift is None or len(matches) < self.min_matches:
            return []

        for hole_id in self.positions:
            self.positions[hole_id] = self.positions[hole_id] + shift

        tracked = []
        for hole_index, hole_id, error, _ in matches:
            hole = holes[hole_index]
            hole["id"] = hole_id
            hole["id_mode"] = "track"
            hole["track_error"] = error
            self.positions[hole_id] = np.array(
                [hole["cx"], hole["cy"]],
                dtype=np.float32,
            )
            self.sizes[hole_id] = self._hole_diagonal(hole)
            tracked.append(hole)

        tracked.sort(key=lambda hole: hole["id"])
        return tracked
