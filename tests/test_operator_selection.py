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
