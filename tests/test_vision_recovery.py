import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from camera_source import CameraFrame, CameraReadError, RealSenseCamera
from vision_main import (
    CameraRecoveryPolicy,
    VisionRecoveryExhaustedError,
    run_vision_session,
    wait_recovery_backoff,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeLink:
    def __init__(self, alive=True):
        self.alive = alive
        self.idle_poll_seconds = 0.02
        self.statuses = []
        self.packets = []

    def mega_alive(self):
        return self.alive

    def send_status(self, status, force=False):
        self.statuses.append((status, force))
        return True

    def send(self, tx, ty, distance, target_id, valid, force=False):
        self.packets.append(
            ((tx, ty, distance, target_id, valid), force)
        )
        return True


class FakeCamera:
    def __init__(self, failure=None):
        self.failure = failure
        self.closed = False
        self.frame = CameraFrame(
            color=np.zeros((20, 20, 3), dtype=np.uint8),
            depth_mm=None,
        )

    def print_info(self):
        pass

    def read(self):
        if self.failure is not None:
            raise self.failure
        return self.frame

    def close(self):
        self.closed = True


def make_args():
    return SimpleNamespace(
        model="fake.pt",
        source="opencv",
        camera=0,
        width=20,
        height=20,
        fps=30,
        realsense_serial=None,
        distance_mode="range",
        no_display=False,
    )


class CameraRecoveryPolicyTest(unittest.TestCase):
    def test_exhausts_after_configured_retries(self):
        policy = CameraRecoveryPolicy(max_attempts=2, reset_seconds=10.0)

        self.assertEqual(policy.record_failure(0.0), (1, True))
        self.assertEqual(policy.record_failure(0.0), (2, True))
        self.assertEqual(policy.record_failure(0.0), (3, False))

    def test_stable_active_period_resets_consecutive_failures(self):
        policy = CameraRecoveryPolicy(max_attempts=2, reset_seconds=10.0)
        policy.record_failure(0.0)
        policy.record_failure(0.0)

        self.assertEqual(policy.record_failure(10.0), (1, True))


class RecoveryBackoffTest(unittest.TestCase):
    def test_keeps_error_status_fresh_while_sleeping(self):
        clock = FakeClock()
        link = FakeLink(alive=True)

        completed = wait_recovery_backoff(
            link,
            seconds=0.05,
            require_mega=True,
            clock=clock,
            sleeper=clock.sleep,
        )

        self.assertTrue(completed)
        self.assertGreaterEqual(len(link.statuses), 3)
        self.assertTrue(all(status == "VISION_ERROR" for status, _ in link.statuses))
        self.assertAlmostEqual(clock.now, 0.05)

    def test_aborts_recovery_when_mega_is_lost(self):
        link = FakeLink(alive=False)

        self.assertFalse(
            wait_recovery_backoff(link, seconds=1.0, require_mega=True)
        )
        self.assertEqual(link.statuses, [])


class RealSenseErrorBoundaryTest(unittest.TestCase):
    def test_wait_for_frames_runtime_error_becomes_recoverable(self):
        class FailingPipeline:
            def wait_for_frames(self, timeout_ms):
                raise RuntimeError(f"timeout {timeout_ms}")

        camera = RealSenseCamera.__new__(RealSenseCamera)
        camera.pipeline = FailingPipeline()
        camera.timeout_ms = 123

        with self.assertRaises(CameraReadError):
            camera.read()


class VisionSessionRecoveryTest(unittest.TestCase):
    def test_camera_reopens_without_reloading_model(self):
        first = FakeCamera(CameraReadError("temporary timeout"))
        second = FakeCamera()
        cameras = [first, second]
        model_loads = []
        model_calls = []
        link = FakeLink()

        def camera_factory(**kwargs):
            return cameras.pop(0)

        def model_factory(path):
            model_loads.append(path)

            def model(frame, **kwargs):
                model_calls.append(frame.shape)
                return []

            return model

        with (
            patch("vision_main.cv2.imshow"),
            patch("vision_main.cv2.waitKey", return_value=27),
        ):
            outcome = run_vision_session(
                make_args(),
                link,
                model_factory=model_factory,
                camera_factory=camera_factory,
                recovery_policy=CameraRecoveryPolicy(1, 10.0),
                recovery_backoff_seconds=0.0,
            )

        self.assertEqual(outcome, "user_exit")
        self.assertEqual(model_loads, ["fake.pt"])
        self.assertEqual(len(model_calls), 1)
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertIn(("VISION_ERROR", True), link.statuses)
        self.assertIn(((0, 0, 0, 0, 0), True), link.packets)

    def test_exhausted_camera_retries_raise_for_systemd(self):
        cameras = [
            FakeCamera(CameraReadError("failure one")),
            FakeCamera(CameraReadError("failure two")),
        ]
        args = make_args()
        args.no_display = True

        with patch("vision_main.cv2.destroyAllWindows") as destroy_windows:
            with self.assertRaises(VisionRecoveryExhaustedError):
                run_vision_session(
                    args,
                    FakeLink(),
                    model_factory=lambda path: lambda frame, **kwargs: [],
                    camera_factory=lambda **kwargs: cameras.pop(0),
                    recovery_policy=CameraRecoveryPolicy(1, 10.0),
                    recovery_backoff_seconds=0.0,
                )

        destroy_windows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
