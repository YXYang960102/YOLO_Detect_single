import unittest

from grid_tracker import GridTracker


def make_grid(dx=0, dy=0):
    holes = []
    for row in range(4):
        for col in range(3):
            hole_id = row * 3 + col + 1
            cx = 200 + col * 180 + dx
            cy = 120 + row * 150 + dy
            half_size = 28 if row == 0 else 45
            holes.append({
                "id": hole_id,
                "cx": cx,
                "cy": cy,
                "conf": 0.9,
                "box": (
                    cx - half_size,
                    cy - half_size,
                    cx + half_size,
                    cy + half_size,
                ),
                "id_mode": "layout",
            })
    return holes


class GridTrackerTest(unittest.TestCase):
    def test_vertical_crop_preserves_original_row_ids(self):
        tracker = GridTracker()
        tracker.update(make_grid())

        shifted = make_grid(dy=-80)[3:12]
        for index, hole in enumerate(shifted, start=1):
            hole["id"] = index

        tracked = tracker.update(shifted)

        self.assertEqual([hole["id"] for hole in tracked], list(range(4, 13)))
        self.assertTrue(all(hole["id_mode"] == "track" for hole in tracked))

    def test_horizontal_crop_preserves_original_column_ids(self):
        tracker = GridTracker()
        tracker.update(make_grid())

        shifted = [
            hole for hole in make_grid(dx=-60)
            if (hole["id"] - 1) % 3 != 0
        ]
        for row in range(4):
            shifted[row * 2]["id"] = row * 3 + 1
            shifted[row * 2 + 1]["id"] = row * 3 + 2

        tracked = tracker.update(shifted)

        self.assertEqual(
            [hole["id"] for hole in tracked],
            [2, 3, 5, 6, 8, 9, 11, 12],
        )

    def test_ambiguous_two_hole_view_is_rejected(self):
        tracker = GridTracker()
        tracker.update(make_grid())

        self.assertEqual(tracker.update(make_grid(dy=-40)[4:6]), [])

    def test_motion_hint_resolves_large_multi_row_shift(self):
        tracker = GridTracker()
        tracker.update(make_grid())

        first_crop = make_grid(dy=-60)[3:12]
        for index, hole in enumerate(first_crop, start=1):
            hole["id"] = index
        tracker.update(first_crop, motion_hint=(0, -60))

        second_crop = make_grid(dy=-130)[6:12]
        for index, hole in enumerate(second_crop, start=1):
            hole["id"] = index
        tracked = tracker.update(second_crop, motion_hint=(0, -70))

        self.assertEqual([hole["id"] for hole in tracked], list(range(7, 13)))


if __name__ == "__main__":
    unittest.main()
