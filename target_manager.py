from hole_grid import predict_hole_position
from config import (
    GENERAL_TARGET_CONFIDENCE,
    GENERAL_TARGET_STABLE_FRAMES,
    MAX_SHOTS_PER_HOLE,
    RED_TARGET_IDS,
    TARGET_EDGE_MARGIN_RATIO,
)


TARGET_NONE = "none"
TARGET_NORMAL = "normal"
TARGET_RED = "red"


class TargetManager:
    def __init__(self, stable_frames=GENERAL_TARGET_STABLE_FRAMES):
        self.stable_frames = stable_frames
        self.locked_target_id = None
        self.locked_target_type = TARGET_NONE
        self.candidate_target_id = None
        self.candidate_target_type = TARGET_NONE
        self.candidate_count = 0
        self.shot_counts = {hole_id: 0 for hole_id in range(1, 13)}

    def reset_tracking(self):
        self.locked_target_id = None
        self.locked_target_type = TARGET_NONE
        self.candidate_target_id = None
        self.candidate_target_type = TARGET_NONE
        self.candidate_count = 0

    def reset_shots(self):
        for hole_id in self.shot_counts:
            self.shot_counts[hole_id] = 0
        self.reset_tracking()

    def record_shot(self, target_id):
        if target_id not in self.shot_counts:
            return

        self.shot_counts[target_id] = min(
            MAX_SHOTS_PER_HOLE,
            self.shot_counts[target_id] + 1,
        )

        if self.shot_counts[target_id] >= MAX_SHOTS_PER_HOLE:
            self.reset_tracking()

    def shots_for(self, target_id):
        return self.shot_counts.get(target_id, 0)

    def _is_reliable(self, hole, frame_width, frame_height):
        hole_id = hole.get("id")
        if hole_id not in self.shot_counts:
            return False
        if hole.get("conf", 0.0) < GENERAL_TARGET_CONFIDENCE:
            return False

        x1, y1, x2, y2 = hole["box"]
        margin_x = frame_width * TARGET_EDGE_MARGIN_RATIO
        margin_y = frame_height * TARGET_EDGE_MARGIN_RATIO

        return (
            x2 > x1
            and y2 > y1
            and x1 > margin_x
            and y1 > margin_y
            and x2 < frame_width - margin_x
            and y2 < frame_height - margin_y
        )

    def _normal_rank(self, hole, frame_width, frame_height):
        hole_id = hole["id"]
        small_hole_penalty = 2.0 if hole_id in RED_TARGET_IDS else 0.0
        horizontal_cost = abs(hole["cx"] - frame_width / 2) / frame_width
        vertical_cost = abs(hole["cy"] - frame_height / 2) / frame_height
        confidence_bonus = 0.15 * hole["conf"]

        return (
            small_hole_penalty
            + horizontal_cost
            + 0.35 * vertical_cost
            - confidence_bonus,
            hole_id,
        )

    def _find_desired_target(self, holes, red_target, frame_width, frame_height):
        reliable = {
            hole["id"]: hole
            for hole in holes
            if self._is_reliable(hole, frame_width, frame_height)
        }

        if red_target is not None:
            red_id = red_target["id"]
            if red_id in RED_TARGET_IDS and red_id in reliable:
                return reliable[red_id], TARGET_RED

        if self.locked_target_type == TARGET_NORMAL:
            locked = reliable.get(self.locked_target_id)
            if (
                locked is not None
                and self.shots_for(self.locked_target_id) < MAX_SHOTS_PER_HOLE
            ):
                return locked, TARGET_NORMAL

        candidates = [
            hole
            for hole in reliable.values()
            if self.shots_for(hole["id"]) < MAX_SHOTS_PER_HOLE
        ]
        if not candidates:
            return None, TARGET_NONE

        return (
            min(candidates, key=lambda hole: self._normal_rank(
                hole,
                frame_width,
                frame_height,
            )),
            TARGET_NORMAL,
        )

    def seen_mask(self, holes, frame_width, frame_height):
        """Protocol v3: bit (id - 1) set for every reliable RGB-detected hole
        in this frame (ids 1-12; depth-only detections never count)."""
        mask = 0
        for hole in holes:
            if hole.get("detector") == "depth":
                continue
            if self._is_reliable(hole, frame_width, frame_height):
                mask |= 1 << (hole["id"] - 1)
        return mask

    def select(self, holes, red_target, frame_width, frame_height,
               selected_target_id=0, allow_bonus=False, predict_missing=False):
        if selected_target_id != 0:
            # Explicit operator choice does not mutate automatic lock/shot
            # state. Missing, ambiguous or unreliable choices never fall back
            # to another hole. Protocol v3 (allow_bonus / predict_missing,
            # 2026-10-27): the bonus holes 1-3 can be chosen, and a choice
            # that is not reliably in view comes back as a PREDICTED target
            # (its expected position from the holes in view, "predicted":
            # True, no box) -- aim-only, never a lock or a shot.
            allowed = range(1, 13) if allow_bonus else range(4, 13)
            if selected_target_id not in allowed:
                return None
            matches = [hole for hole in holes
                       if hole.get("id") == selected_target_id]
            if len(matches) > 1:
                return None
            if matches and self._is_reliable(matches[0], frame_width, frame_height):
                return dict(matches[0], target_type=TARGET_NORMAL)
            if not predict_missing:
                return None
            position = predict_hole_position(holes, selected_target_id, frame_width, frame_height)
            if position is None:
                return None
            return {
                "id": selected_target_id,
                "cx": int(round(position[0])),
                "cy": int(round(position[1])),
                "box": None,
                "conf": 0.0,
                "predicted": True,
                "target_type": TARGET_NORMAL,
            }

        desired, target_type = self._find_desired_target(
            holes,
            red_target,
            frame_width,
            frame_height,
        )

        if desired is None:
            self.reset_tracking()
            return None

        target_id = desired["id"]

        if (
            target_id == self.locked_target_id
            and target_type == self.locked_target_type
        ):
            desired["target_type"] = target_type
            return desired

        if target_type == TARGET_RED:
            # select_red_target already requires a stable red detection.
            required_frames = 1
        else:
            required_frames = self.stable_frames

        if (
            target_id == self.candidate_target_id
            and target_type == self.candidate_target_type
        ):
            self.candidate_count += 1
        else:
            self.candidate_target_id = target_id
            self.candidate_target_type = target_type
            self.candidate_count = 1

        if self.candidate_count < required_frames:
            return None

        self.locked_target_id = target_id
        self.locked_target_type = target_type
        desired["target_type"] = target_type
        return desired
