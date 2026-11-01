"""ProcessCamera (branch camera-process) with a fake RealSense in the child.

The fake fills each frame's color with seq % 256 and its depth with seq, so
a frame whose color and depth come from different frames is caught, and
the sequence shows whether frames go backwards or repeat.
"""
import time
import unittest

import numpy as np

from camera_process import ProcessCamera
from camera_source import CameraFrame, CameraReadError, CameraUnavailableError
from depth_distance import CameraIntrinsics

W, H = 64, 48


class FakeRealSense:
    """Module level, so the spawned child can import it."""

    def __init__(self, width, height, timeout_ms, mode="ok", fps=200, **_):
        if mode == "open_unavailable":
            raise CameraUnavailableError("fake: no RealSense device found")
        if mode == "open_crash":
            raise ValueError("fake: broken install")
        self.width = width if mode != "wrong_size" else width + 2
        self.height = height
        self.mode = mode
        self.period = 1.0 / fps
        self.seq = 0
        self.intrinsics = CameraIntrinsics(fx=600.0, fy=600.0, ppx=32.0, ppy=24.0,
                                           width=width, height=height)
        self.last_read_timings = {}

    def info(self):
        return {"source": "realsense", "name": "fake"}

    def read(self):
        time.sleep(self.period)
        self.seq += 1
        if self.mode == "read_error" and self.seq > 5:
            raise CameraReadError("fake: RealSense frame read failed")
        self.last_read_timings = {"wait": 0.001, "align": 0.020, "convert": 0.001}
        return CameraFrame(
            color=np.full((self.height, self.width, 3), self.seq % 256, dtype=np.uint8),
            depth_mm=np.full((self.height, self.width), float(self.seq), dtype=np.float32),
            intrinsics=self.intrinsics,
            timestamp_ms=1000.0 + self.seq,
        )

    def close(self):
        pass


def open_camera(mode="ok", **kwargs):
    return ProcessCamera(width=W, height=H, timeout_ms=2000, camera_factory=FakeRealSense,
                         mode=mode, **kwargs)


class ProcessCameraTest(unittest.TestCase):
    def test_frames_are_whole_and_in_order(self):
        camera = open_camera()
        try:
            self.assertEqual(camera.intrinsics.fx, 600.0)
            self.assertEqual(camera.info()["capture"], "separate process")
            last = 0
            for _ in range(60):
                frame = camera.read()
                seq = int(frame.depth_mm[0, 0])
                # color and depth from the same frame, every pixel
                self.assertTrue(np.all(frame.depth_mm == seq))
                self.assertTrue(np.all(frame.color == seq % 256))
                self.assertGreater(seq, last)
                self.assertEqual(frame.timestamp_ms, 1000.0 + seq)
                self.assertEqual(frame.color.shape, (H, W, 3))
                last = seq
                time.sleep(0.003)  # slower than the camera sometimes
            self.assertAlmostEqual(camera.last_read_timings["align"], 0.020)
            self.assertIn("wait", camera.last_read_timings)
            self.assertIn("copy", camera.last_read_timings)
        finally:
            camera.close()

    def test_returned_frame_is_a_copy(self):
        camera = open_camera()
        try:
            frame = camera.read()
            seq = int(frame.depth_mm[0, 0])
            for _ in range(10):
                camera.read()
            self.assertTrue(np.all(frame.depth_mm == seq))  # not overwritten
        finally:
            camera.close()

    def test_newest_frame_after_a_slow_loop(self):
        camera = open_camera()
        try:
            first = int(camera.read().depth_mm[0, 0])
            time.sleep(0.2)  # ~40 frames go by at 200 fps
            second = int(camera.read().depth_mm[0, 0])
            self.assertGreater(second - first, 10)
        finally:
            camera.close()

    def test_close_stops_the_child(self):
        camera = open_camera()
        camera.read()
        process = camera._process
        camera.close()
        self.assertFalse(process.is_alive())
        camera.close()  # twice is fine
        with self.assertRaises(CameraReadError):
            camera.read()

    def test_unavailable_at_open(self):
        start = time.monotonic()
        with self.assertRaises(CameraUnavailableError):
            open_camera("open_unavailable")
        self.assertLess(time.monotonic() - start, 10.0)

    def test_crash_at_open_is_not_recoverable(self):
        with self.assertRaises(RuntimeError) as caught:
            open_camera("open_crash")
        self.assertNotIsInstance(caught.exception, CameraUnavailableError)

    def test_read_error_reaches_the_main_process(self):
        camera = open_camera("read_error")
        try:
            with self.assertRaises(CameraReadError):
                for _ in range(100):
                    camera.read()
            camera.close()
            self.assertFalse(camera._process.is_alive())
        finally:
            camera.close()

    def test_wrong_frame_size_is_reported(self):
        camera = open_camera("wrong_size")
        try:
            with self.assertRaises(CameraUnavailableError):
                for _ in range(10):
                    camera.read()
        finally:
            camera.close()

    def test_killed_child_is_a_read_error(self):
        camera = open_camera()
        try:
            camera.read()
            camera._process.kill()
            camera._process.join(2.0)
            with self.assertRaises(CameraReadError):
                for _ in range(100):
                    camera.read()
        finally:
            camera.close()


if __name__ == "__main__":
    unittest.main()
