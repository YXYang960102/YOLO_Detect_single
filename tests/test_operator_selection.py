"""Host-only protocol, selection and positional-ID regression checks."""
import copy
import unittest

from hole_grid import assign_ids, reset_grid_memory
from serial_tx import VisionSerial
from target_manager import TargetManager
from test_serial_tx import FakeClock, FakeSerial
from test_target_manager import make_hole
from test_vision_main import FakeDepthEstimator
from vision_main import resolve_distance_and_validity


class OperatorSelectionTest(unittest.TestCase):
    def link(self):
        clock = FakeClock()
        link = VisionSerial(enabled=False, protocol_version=2, clock=clock)
        link.enabled = True
        link.serial = FakeSerial()
        return link, clock

    def test_v2_fragmented_selection_and_heartbeat_are_independent(self):
        link, clock = self.link()
        link.serial.feed(b"MEGA_TARGET,2,")
        self.assertFalse(link.poll_mega())
        self.assertEqual(link.selected_target_id, 0)
        link.serial.feed(b"10\r\n")
        self.assertFalse(link.poll_mega())
        self.assertEqual(link.selected_target_id, 10)
        link.serial.feed(b"MEGA_READY,1\n")
        self.assertFalse(link.poll_mega())
        link.serial.feed(b"MEGA_READY,2\nMEGA_HEARTBEAT,2\n")
        self.assertTrue(link.poll_mega())
        clock.now = 2.0
        link.serial.feed(b"MEGA_TARGET,2,10\n")
        self.assertFalse(link.poll_mega())
        self.assertEqual(link.selected_target_id, 10)
        link.send_status("VISION_READY", force=True)
        self.assertEqual(link.serial.messages[-1], b"VISION_READY,2\n")

    def test_invalid_commands_preserve_selection_and_zero_clears(self):
        link, _ = self.link()
        link.serial.feed(b"MEGA_TARGET,2,4\n")
        link.poll_mega()
        for line in ("MEGA_TARGET,1,0", "MEGA_TARGET,2,1", "MEGA_TARGET,2,3",
                     "MEGA_TARGET,2,13", "MEGA_TARGET,2,-1", "MEGA_TARGET,2,4.0",
                     "MEGA_TARGET,2,nan", "MEGA_TARGET,2,0,extra", "MEGA_TARGET,2"):
            with self.subTest(line=line):
                link.serial.feed((line + "\n").encode())
                link.poll_mega()
                self.assertEqual(link.selected_target_id, 4)
        link.serial.feed(b"MEGA_TARGET,2,0\n")
        link.poll_mega()
        self.assertEqual(link.selected_target_id, 0)

    def test_all_nine_selections_switch_without_red_fallback(self):
        link, _ = self.link()
        manager = TargetManager()
        holes = [make_hole(i, 200 + ((i-4) % 3)*250,
                           250 + ((i-4)//3)*180) for i in range(4, 13)]
        red = make_hole(2, 500, 100)
        holes.append(red)
        for target_id in range(4, 13):
            link.serial.feed(f"MEGA_TARGET,2,{target_id}\n".encode())
            link.poll_mega()
            selected = manager.select(holes, red, 1000, 800, link.selected_target_id)
            self.assertEqual(selected["id"], target_id)
            missing = manager.select([h for h in holes if h["id"] != target_id],
                                     red, 1000, 800, link.selected_target_id)
            self.assertIsNone(missing)
            self.assertEqual(resolve_distance_and_validity(
                missing, None, None, FakeDepthEstimator(), "range")[:2], (0, 0))

    def test_override_preserves_auto_state_and_zero_uses_original_logic(self):
        manager = TargetManager(stable_frames=2)
        control = TargetManager(stable_frames=2)
        holes = [make_hole(5, 500, 350), make_hole(4, 250, 350)]
        manager.select(holes, None, 1000, 800)
        control.select(holes, None, 1000, 800)
        state = copy.deepcopy(manager.__dict__)
        self.assertEqual(manager.select(holes, None, 1000, 800, 4)["id"], 4)
        self.assertEqual(manager.__dict__, state)
        self.assertEqual(manager.select(holes, None, 1000, 800, 0),
                         control.select(holes, None, 1000, 800))

    def test_unreliable_duplicate_and_bonus_selection_rejected(self):
        manager = TargetManager()
        good = make_hole(4, 250, 350)
        for holes, selected in (([good, good], 4),
                                ([make_hole(4, 250, 350, conf=0.01)], 4),
                                ([make_hole(4, 10, 350)], 4),
                                ([make_hole(1, 250, 350)], 1)):
            self.assertIsNone(manager.select(holes, None, 1000, 800, selected))

    def test_selected_depth_only_hole_still_invalid(self):
        hole = dict(make_hole(4, 250, 350), detector="depth")
        selected = TargetManager().select([hole], None, 1000, 800, 4)
        self.assertEqual(resolve_distance_and_validity(
            selected, "depth", None, FakeDepthEstimator(), "range")[:2], (0, 0))

    def test_full_grid_positions_have_existing_row_major_ids(self):
        reset_grid_memory()
        self.addCleanup(reset_grid_memory)
        # Three small bonus holes above three rows of larger standard holes.
        holes = [make_hole(0, x, y, size=40 if row == 0 else 80)
                 for row, y in enumerate((100, 300, 480, 660))
                 for x in (250, 500, 750)]
        for h in holes:
            del h["id"]
        assigned = assign_ids(list(reversed(holes)), 1000)
        actual = {(h["cx"], h["cy"]): h["id"] for h in assigned}
        for row, y in enumerate((300, 480, 660)):
            for col, x in enumerate((250, 500, 750)):
                self.assertEqual(actual[(x, y)], 4 + row*3 + col)

    def test_session_consumes_uart_selection_and_sends_only_selected_packet(self):
        from unittest.mock import patch
        import numpy as np
        from test_vision_recovery import FakeCamera, make_args
        from vision_main import run_vision_session
        for selected_id, expected in ((4, b"-250,-50,0,4,1\n"),
                                      (12, b"0,0,0,0,0\n")):
            with self.subTest(selected_id=selected_id):
                link, _ = self.link()
                link.serial.feed(f"MEGA_TARGET,2,{selected_id}\n".encode())
                camera = FakeCamera()
                camera.frame.color = np.zeros((800, 1000, 3), dtype=np.uint8)
                holes = [make_hole(4, 250, 350), make_hole(5, 500, 350)]
                with (patch("vision_main.build_holes", return_value=holes),
                      patch("vision_main.assign_ids", side_effect=lambda h, w: h),
                      patch("vision_main.GridTracker.update", side_effect=lambda h, **kw: h),
                      patch("vision_main.select_red_target", return_value=None),
                      patch("vision_main.draw_debug"),
                      patch("vision_main.cv2.imshow"),
                      patch("vision_main.cv2.destroyAllWindows"),
                      patch("vision_main.cv2.waitKey", return_value=27)):
                    run_vision_session(make_args(), link,
                        model_factory=lambda path: lambda frame, **kw: [],
                        camera_factory=lambda **kw: camera)
                self.assertIn(expected, link.serial.messages)
                self.assertFalse(any(b",5,1" in m for m in link.serial.messages))


class ProtocolV3Test(unittest.TestCase):
    """v3 (2026-10-27): bonus holes, predicted out-of-view position, the
    detected-ids mask, and tx / ty kept when only the depth fails."""

    def link(self):
        clock = FakeClock()
        link = VisionSerial(enabled=False, protocol_version=3, clock=clock)
        link.enabled = True
        link.serial = FakeSerial()
        return link, clock

    def test_v3_accepts_bonus_ids_and_only_its_own_version(self):
        link, _ = self.link()
        for target in range(0, 13):
            link.serial.feed(f"MEGA_TARGET,3,{target}\n".encode())
            link.poll_mega()
            self.assertEqual(link.selected_target_id, target)
        for line in ("MEGA_TARGET,2,4", "MEGA_TARGET,3,13", "MEGA_TARGET,3,-1", "MEGA_TARGET,3"):
            link.serial.feed((line + "\n").encode())
            link.poll_mega()
            self.assertEqual(link.selected_target_id, 12)
        link.serial.feed(b"MEGA_HEARTBEAT,2\n")
        self.assertFalse(link.poll_mega())                 # v2 heartbeats refused
        link.serial.feed(b"MEGA_HEARTBEAT,3\n")
        self.assertTrue(link.poll_mega())

    def test_v3_packet_has_the_seen_mask(self):
        link, _ = self.link()
        link.send(-250, -50, 2480, 8, 1, seen_mask=0b100110000, force=True)
        self.assertEqual(link.serial.messages[-1], b"-250,-50,2480,8,1,304,-1,0,0\n")
        # 2026-10-28: the depth ring's share and sectors for the Dashboard.
        link.send(-250, -50, 2480, 8, 1, seen_mask=304, ring=(62, 0b11100011), force=True)
        self.assertEqual(link.serial.messages[-1], b"-250,-50,2480,8,1,304,62,227,0\n")
        # 2026-10-31: the lit bonus hole (vision id 1-3) as field 9.
        link.send(-250, -50, 2480, 8, 1, seen_mask=304, ring=(62, 0b11100011), lit_id=2, force=True)
        self.assertEqual(link.serial.messages[-1], b"-250,-50,2480,8,1,304,62,227,2\n")
        v2 = VisionSerial(enabled=False, protocol_version=2, clock=FakeClock())
        v2.enabled = True
        v2.serial = FakeSerial()
        v2.send(-250, -50, 2480, 8, 1, seen_mask=304, force=True)
        self.assertEqual(v2.serial.messages[-1], b"-250,-50,2480,8,1\n")   # v2 unchanged

    def test_bonus_selection_only_with_allow_bonus(self):
        manager = TargetManager()
        holes = [make_hole(2, 500, 120, size=60), make_hole(5, 500, 350)]
        self.assertIsNone(manager.select(holes, None, 1000, 800, 2))
        self.assertEqual(manager.select(holes, None, 1000, 800, 2, allow_bonus=True)["id"], 2)

    def test_out_of_view_choice_is_predicted_aim_only(self):
        manager = TargetManager()
        # Camera too far left: left and middle columns at x = 900 / 1150 in a
        # 1280 x 720 frame; the right column (ids 6, 9, 12) is out of view.
        holes = [make_hole(i, 900 + ((i - 4) % 3) * 250, 180 + ((i - 4) // 3) * 180, size=80)
                 for i in (4, 5, 7, 8, 10, 11)]
        target = manager.select(holes, None, 1280, 720, 9, predict_missing=True)
        self.assertTrue(target["predicted"])
        self.assertEqual((target["id"], target["cx"], target["cy"]), (9, 1400, 360))
        self.assertEqual(resolve_distance_and_validity(
            target, "depth", None, FakeDepthEstimator(), "range"), (0, 2, None))
        # v2 behavior without the flag: nothing.
        self.assertIsNone(manager.select(holes, None, 1280, 720, 9))
        # One column in view can't place another column.
        self.assertIsNone(manager.select([h for h in holes if h["id"] in (4, 7, 10)],
                                         None, 1280, 720, 9, predict_missing=True))
        # Never predicted when the hole itself is there and reliable.
        self.assertNotIn("predicted", manager.select(holes, None, 1280, 720, 5, predict_missing=True))

    def test_seen_mask_counts_reliable_rgb_holes_only(self):
        manager = TargetManager()
        holes = [make_hole(5, 500, 350), make_hole(9, 700, 350),
                 make_hole(2, 500, 120, conf=0.01),          # unreliable
                 dict(make_hole(4, 300, 350), detector="depth")]
        self.assertEqual(manager.seen_mask(holes, 1000, 800), (1 << 4) | (1 << 8))

    def test_depth_failure_keeps_target_valid_only_in_v3(self):
        hole = make_hole(5, 500, 350)
        self.assertEqual(resolve_distance_and_validity(
            hole, "depth", None, FakeDepthEstimator(None), "range")[:2], (0, 0))
        self.assertEqual(resolve_distance_and_validity(
            hole, "depth", None, FakeDepthEstimator(None), "range",
            keep_valid_without_depth=True)[:2], (0, 1))

    def test_debug_overlays_draw_without_error(self):
        import numpy as np
        from depth_distance import DepthEstimator
        from vision_main import draw_depth_ring, draw_predicted_target
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        depth = np.full((720, 1280), 2500.0, dtype=np.float32)
        depth[340:360, :] = 0.0                               # a stripe with no depth
        estimator = DepthEstimator(inner_ratio=1.15, outer_ratio=1.60)
        draw_depth_ring(frame, make_hole(5, 640, 350), depth, estimator)
        ring = frame[350 - 80:350 + 81, 640 - 80:640 + 81]
        self.assertTrue((ring[:, :, 1] > 0).any() and (ring[:, :, 2] > 0).any())   # green and red tints
        draw_depth_ring(frame, make_hole(5, 640, 350), None, estimator)          # webcam: outlines only
        draw_predicted_target(frame, {"id": 9, "cx": 1400, "cy": 360, "predicted": True})

    def test_session_v3_sends_prediction_and_mask(self):
        from unittest.mock import patch
        import numpy as np
        from test_vision_recovery import FakeCamera, make_args
        from vision_main import run_vision_session
        link, _ = self.link()
        link.serial.feed(b"MEGA_TARGET,3,6\n")
        camera = FakeCamera()
        camera.frame.color = np.zeros((800, 1000, 3), dtype=np.uint8)
        # Left and middle columns in view (x 600 / 800); hole 6 is out of view.
        holes = [make_hole(i, 600 + ((i - 4) % 3) * 200, 250 + ((i - 4) // 3) * 180)
                 for i in (4, 5, 7, 8, 10, 11)]
        with (patch("vision_main.build_holes", return_value=holes),
              patch("vision_main.assign_ids", side_effect=lambda h, w: h),
              patch("vision_main.GridTracker.update", side_effect=lambda h, **kw: h),
              patch("vision_main.select_red_target", return_value=None),
              patch("vision_main.draw_debug"),
              patch("vision_main.cv2.imshow"),
              patch("vision_main.cv2.destroyAllWindows"),
              patch("vision_main.cv2.waitKey", return_value=27)):
            run_vision_session(make_args(), link,
                model_factory=lambda path: lambda frame, **kw: [],
                camera_factory=lambda **kw: camera)
        mask = sum(1 << (i - 1) for i in (4, 5, 7, 8, 10, 11))
        # Predicted: no ring data (-1, 0).
        self.assertIn(f"500,-150,0,6,2,{mask},-1,0,0\n".encode(), link.serial.messages)
