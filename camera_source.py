from dataclasses import dataclass
from typing import Dict, Optional

import cv2
import numpy as np

from depth_distance import CameraIntrinsics


class RecoverableCameraError(RuntimeError):
    """Camera hardware/session failure that may succeed after reopening."""


class CameraUnavailableError(RecoverableCameraError):
    """Camera device or requested stream is temporarily unavailable."""


class CameraReadError(RecoverableCameraError):
    """An active camera session failed while waiting for or aligning a frame."""


@dataclass
class CameraFrame:
    color: np.ndarray
    depth_mm: Optional[np.ndarray] = None
    intrinsics: Optional[CameraIntrinsics] = None
    timestamp_ms: Optional[float] = None


class OpenCVCamera:
    def __init__(self, index=0):
        self.index = int(index)
        self.capture = cv2.VideoCapture(self.index)
        if not self.capture.isOpened():
            raise CameraUnavailableError(
                f"cannot open OpenCV camera index {self.index}"
            )

    def read(self):
        ok, color = self.capture.read()
        if not ok:
            return None
        return CameraFrame(color=color)

    def info(self) -> Dict[str, object]:
        return {
            "source": "opencv",
            "camera_index": self.index,
            "color_width": int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "color_height": int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(self.capture.get(cv2.CAP_PROP_FPS)),
            "depth": False,
        }

    def print_info(self):
        print("Camera source: OpenCV")
        for key, value in self.info().items():
            if key != "source":
                print(f"  {key}: {value}")

    def close(self):
        self.capture.release()


class RealSenseCamera:
    def __init__(
        self,
        width=1280,
        height=720,
        fps=30,
        serial_number=None,
        timeout_ms=5000,
        warmup_frames=15,
        enable_emitter=True,
    ):
        try:
            import pyrealsense2 as rs
        except ImportError as exc:
            raise RuntimeError(
                "pyrealsense2 is required for the Solomon/RealSense camera"
            ) from exc

        self.rs = rs
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.timeout_ms = int(timeout_ms)
        self.serial_number = serial_number
        self.pipeline = rs.pipeline()
        self._closed = False

        context = rs.context()
        devices = list(context.query_devices())
        if not devices:
            raise CameraUnavailableError(
                "no RealSense device found; check USB 3 cable, power, udev rules, "
                "and run rs-enumerate-devices"
            )

        if serial_number is not None:
            matching = [
                device
                for device in devices
                if self._device_info(device, rs.camera_info.serial_number)
                == str(serial_number)
            ]
            if not matching:
                detected = [
                    self._device_info(device, rs.camera_info.serial_number)
                    for device in devices
                ]
                raise CameraUnavailableError(
                    f"RealSense serial {serial_number} was not found; detected {detected}"
                )

        config = rs.config()
        if serial_number:
            config.enable_device(str(serial_number))
        config.enable_stream(
            rs.stream.depth,
            self.width,
            self.height,
            rs.format.z16,
            self.fps,
        )
        config.enable_stream(
            rs.stream.color,
            self.width,
            self.height,
            rs.format.bgr8,
            self.fps,
        )

        try:
            self.profile = self.pipeline.start(config)
        except RuntimeError as exc:
            raise CameraUnavailableError(
                f"cannot start RealSense at {self.width}x{self.height}@{self.fps}; "
                "verify the camera profile with realsense-viewer"
            ) from exc

        try:
            self.device = self.profile.get_device()
            self.depth_sensor = self.device.first_depth_sensor()
            self.depth_scale_mm = (
                float(self.depth_sensor.get_depth_scale()) * 1000.0
            )
            self.align = rs.align(rs.stream.color)

            if enable_emitter is not None:
                try:
                    if self.depth_sensor.supports(rs.option.emitter_enabled):
                        self.depth_sensor.set_option(
                            rs.option.emitter_enabled,
                            1.0 if enable_emitter else 0.0,
                        )
                except RuntimeError as exc:
                    print(f"Warning: could not change IR emitter state: {exc}")

            color_profile = self.profile.get_stream(
                rs.stream.color
            ).as_video_stream_profile()
            intr = color_profile.get_intrinsics()
            self.intrinsics = self._convert_intrinsics(intr)

            # Discard initial auto-exposure frames before measurements are used.
            for _ in range(max(0, int(warmup_frames))):
                self.pipeline.wait_for_frames(timeout_ms=self.timeout_ms)
        except RuntimeError as exc:
            try:
                self.pipeline.stop()
            except RuntimeError:
                pass
            self._closed = True
            raise CameraReadError(
                "RealSense initialization or warm-up failed "
                f"within the {self.timeout_ms} ms frame timeout"
            ) from exc

    @staticmethod
    def _device_info(device, field):
        try:
            if device.supports(field):
                return device.get_info(field)
        except RuntimeError:
            pass
        return ""

    def _convert_intrinsics(self, intr):
        coeffs = tuple(float(value) for value in intr.coeffs)
        return CameraIntrinsics(
            fx=float(intr.fx),
            fy=float(intr.fy),
            ppx=float(intr.ppx),
            ppy=float(intr.ppy),
            width=int(intr.width),
            height=int(intr.height),
            distortion_model=str(intr.model),
            coeffs=coeffs,
        )

    def read(self):
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=self.timeout_ms)
            aligned = self.align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                raise CameraReadError(
                    "RealSense frameset did not contain both color and depth"
                )

            color = np.asanyarray(color_frame.get_data())
            depth_mm = (
                np.asanyarray(depth_frame.get_data()).astype(np.float32)
                * self.depth_scale_mm
            )

            # Because depth is aligned to color, the pixel coordinates and
            # intrinsics used by YOLO are the color-camera coordinates.
            intr = color_frame.profile.as_video_stream_profile().get_intrinsics()
            intrinsics = self._convert_intrinsics(intr)

            return CameraFrame(
                color=color,
                depth_mm=depth_mm,
                intrinsics=intrinsics,
                timestamp_ms=float(color_frame.get_timestamp()),
            )
        except CameraReadError:
            raise
        except RuntimeError as exc:
            raise CameraReadError(
                f"RealSense frame read failed after {self.timeout_ms} ms"
            ) from exc

    def info(self) -> Dict[str, object]:
        rs = self.rs
        info = {
            "source": "realsense",
            "name": self._device_info(self.device, rs.camera_info.name),
            "serial": self._device_info(
                self.device, rs.camera_info.serial_number
            ),
            "firmware": self._device_info(
                self.device, rs.camera_info.firmware_version
            ),
            "usb_type": self._device_info(
                self.device, rs.camera_info.usb_type_descriptor
            ),
            "color_width": self.intrinsics.width,
            "color_height": self.intrinsics.height,
            "fps": self.fps,
            "depth_scale_mm_per_unit": self.depth_scale_mm,
        }
        info.update({f"intrinsics_{key}": value for key, value in self.intrinsics.as_dict().items()})
        return info

    def print_info(self):
        print("Camera source: Solomon / Intel RealSense")
        for key, value in self.info().items():
            if key != "source":
                print(f"  {key}: {value}")

    def close(self):
        if not self._closed:
            try:
                self.pipeline.stop()
            except RuntimeError as exc:
                print(f"Warning: RealSense stop failed during cleanup: {exc}")
            self._closed = True


def create_camera(
    source,
    camera_index=0,
    width=1280,
    height=720,
    fps=30,
    serial_number=None,
    timeout_ms=5000,
    warmup_frames=15,
    enable_emitter=True,
):
    normalized = str(source).strip().lower()
    if normalized == "opencv":
        return OpenCVCamera(camera_index)
    if normalized == "realsense":
        return RealSenseCamera(
            width=width,
            height=height,
            fps=fps,
            serial_number=serial_number,
            timeout_ms=timeout_ms,
            warmup_frames=warmup_frames,
            enable_emitter=enable_emitter,
        )
    raise ValueError(f"unsupported camera source: {source}")
