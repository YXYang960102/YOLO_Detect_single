import unittest

from target_manager import TARGET_NORMAL, TARGET_RED, TargetManager


FRAME_WIDTH = 1000
FRAME_HEIGHT = 800


def make_hole(hole_id, cx, cy, conf=0.9, size=100):
    half = size // 2
    return {
        "id": hole_id,
        "cx": cx,
        "cy": cy,
        "conf": conf,
        "box": (cx - half, cy - half, cx + half, cy + half),
    }


class TargetManagerTest(unittest.TestCase):
    def test_normal_target_requires_stable_frames(self):
        manager = TargetManager(stable_frames=3)
        holes = [make_hole(5, 500, 350), make_hole(4, 250, 350)]

        self.assertIsNone(manager.select(holes, None, FRAME_WIDTH, FRAME_HEIGHT))
        self.assertIsNone(manager.select(holes, None, FRAME_WIDTH, FRAME_HEIGHT))
        target = manager.select(holes, None, FRAME_WIDTH, FRAME_HEIGHT)

        self.assertEqual(target["id"], 5)
        self.assertEqual(target["target_type"], TARGET_NORMAL)

    def test_stable_red_top_hole_overrides_normal_target(self):
        manager = TargetManager(stable_frames=1)
        normal = make_hole(5, 500, 350)
        red = make_hole(2, 650, 120)

        self.assertEqual(
            manager.select([normal, red], None, FRAME_WIDTH, FRAME_HEIGHT)["id"],
            5,
        )
        target = manager.select([normal, red], red, FRAME_WIDTH, FRAME_HEIGHT)

        self.assertEqual(target["id"], 2)
        self.assertEqual(target["target_type"], TARGET_RED)

    def test_red_detection_outside_top_row_is_not_red_priority(self):
        manager = TargetManager(stable_frames=1)
        center = make_hole(5, 500, 350)
        lower_red = make_hole(8, 500, 600)

        target = manager.select(
            [center, lower_red],
            lower_red,
            FRAME_WIDTH,
            FRAME_HEIGHT,
        )

        self.assertEqual(target["id"], 5)
        self.assertEqual(target["target_type"], TARGET_NORMAL)

    def test_edge_clipped_box_is_rejected(self):
        manager = TargetManager(stable_frames=1)
        clipped = make_hole(5, 20, 350, size=100)

        self.assertIsNone(
            manager.select([clipped], None, FRAME_WIDTH, FRAME_HEIGHT)
        )

    def test_three_confirmed_shots_exclude_target(self):
        manager = TargetManager(stable_frames=1)
        first = make_hole(5, 500, 350)
        second = make_hole(4, 300, 350)

        self.assertEqual(
            manager.select([first, second], None, FRAME_WIDTH, FRAME_HEIGHT)["id"],
            5,
        )
        manager.record_shot(5)
        manager.record_shot(5)
        manager.record_shot(5)

        target = manager.select(
            [first, second],
            None,
            FRAME_WIDTH,
            FRAME_HEIGHT,
        )
        self.assertEqual(target["id"], 4)


if __name__ == "__main__":
    unittest.main()
