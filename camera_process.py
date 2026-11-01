"""RealSense capture in its own process (branch camera-process, 2026-11-01).

Why: on the Orin the vision loop is one Python thread (one CPU core at
97 %, GPU ~20 %), and RealSense align alone takes ~20 ms of every ~52 ms
frame. A background thread does not help -- align keeps the GIL (measured:
the main thread fell to 49 % beside it) -- but a separate process has its
own interpreter and GIL, so wait + align + depth conversion run on another
core while the main loop does YOLO and the hole logic.

ProcessCamera has the same interface as RealSenseCamera (read / info /
print_info / close / last_read_timings), so vision_main only swaps the
camera factory (config.CAMERA_IN_SEPARATE_PROCESS).

Data path, per frame:
  child: camera.read() -> lock slot -> copy color + depth + header into the
         slot -> unlock -> send ("frame", slot) -> next frame goes to the
         other slot
  main:  read() waits for a frame newer than the last one it returned,
         locks that slot, copies it out, unlocks.
Color and depth of one frame are written and read under the same lock,
so a frame is never half old, half new. The header carries the sequence
number, so a slot rewritten between the message and the lock is still
returned consistently, and never an older frame than the last one.

Lifecycle: the child is started with "spawn" (a fresh interpreter -- the
main process already holds CUDA / PyTorch, which must not be forked). It
opens the camera, reports ("ready", info, intrinsics) or ("error", ...),
and stops on "stop", on its parent's death (getppid changes) or on a
camera error (reported, then the camera is closed). It ignores Ctrl+C so
the main process closes it in order. close() asks it to stop, then
terminates / kills it if it doesn't, so it never keeps the camera.
"""
import ctypes
import math
import multiprocessing
import os
import signal
import time
from typing import Dict

import numpy as np

from camera_source import (
    CameraFrame,
    CameraReadError,
    CameraUnavailableError,
    RealSenseCamera,
    create_camera,
)

# Header per slot: sequence, timestamp ms (NaN = none), and the child's
# wait / align / convert / copy-in times in seconds.
_HEADER_FIELDS = 6
_SLOTS = 2
# Spawning the child imports numpy / cv2 / pyrealsense2 and the vision
# modules, then the camera warms up: allow for all of it on the Orin.
START_TIMEOUT_S = 20.0
STOP_TIMEOUT_S = 2.0


def _camera_worker(conn, color_raw, depth_raw, header_raw, locks, shape,
                   camera_factory, camera_kwargs, parent_pid):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    height, width = shape
    camera = None
    try:
        camera = camera_factory(**camera_kwargs)
        info = camera.info() if hasattr(camera, "info") else {}
        conn.send(("ready", info, getattr(camera, "intrinsics", None)))

        color = np.frombuffer(color_raw, dtype=np.uint8).reshape(_SLOTS, height, width, 3)
        depth = np.frombuffer(depth_raw, dtype=np.float32).reshape(_SLOTS, height, width)
        header = np.frombuffer(header_raw, dtype=np.float64).reshape(_SLOTS, _HEADER_FIELDS)
        seq = 0
        slot = 0
        while True:
            if os.getppid() != parent_pid:
                break  # the main process is gone
            if conn.poll():
                try:
                    message = conn.recv()
                except EOFError:
                    break
                if message and message[0] == "stop":
                    break
            frame = camera.read()
            if frame is None:
                continue
            if frame.color.shape != (height, width, 3) or (
                    frame.depth_mm is None or frame.depth_mm.shape != (height, width)):
                raise CameraUnavailableError(
                    f"camera process: frame {frame.color.shape} / "
                    f"{None if frame.depth_mm is None else frame.depth_mm.shape} "
                    f"is not the configured {width}x{height} color + depth")
            timings = getattr(camera, "last_read_timings", {}) or {}
            seq += 1
            t0 = time.perf_counter()
            with locks[slot]:
                color[slot][...] = frame.color
                depth[slot][...] = frame.depth_mm
                header[slot] = (
                    seq,
                    float("nan") if frame.timestamp_ms is None else frame.timestamp_ms,
                    timings.get("wait", 0.0),
                    timings.get("align", 0.0),
                    timings.get("convert", 0.0),
                    time.perf_counter() - t0,
                )
            conn.send(("frame", slot))
            slot = 1 - slot
    except CameraUnavailableError as exc:
        _send_quietly(conn, ("error", "unavailable", str(exc)))
    except CameraReadError as exc:
        _send_quietly(conn, ("error", "read", str(exc)))
    except Exception as exc:  # anything else: not recoverable by reopening
        _send_quietly(conn, ("error", "fatal", f"{type(exc).__name__}: {exc}"))
    finally:
        if camera is not None:
            try:
                camera.close()
            except Exception:
                pass
        conn.close()


def _send_quietly(conn, message):
    try:
        conn.send(message)
    except (BrokenPipeError, EOFError, OSError):
        pass


def _raise_child_error(kind, text):
    if kind == "unavailable":
        raise CameraUnavailableError(text)
    if kind == "read":
        raise CameraReadError(text)
    raise RuntimeError(f"camera process failed: {text}")


class ProcessCamera:
    def __init__(self, width=1280, height=720, timeout_ms=5000,
                 camera_factory=RealSenseCamera, start_timeout_s=START_TIMEOUT_S,
                 **camera_kwargs):
        self.width = int(width)
        self.height = int(height)
        self.timeout_s = max(0.1, int(timeout_ms) / 1000.0)
        self.last_read_timings = {}
        self.intrinsics = None
        self._info = {}
        self._last_seq = 0
        self._closed = False

        ctx = multiprocessing.get_context("spawn")
        pixels = self.width * self.height
        self._color_raw = ctx.RawArray(ctypes.c_uint8, _SLOTS * pixels * 3)
        self._depth_raw = ctx.RawArray(ctypes.c_float, _SLOTS * pixels)
        self._header_raw = ctx.RawArray(ctypes.c_double, _SLOTS * _HEADER_FIELDS)
        self._color = np.frombuffer(self._color_raw, dtype=np.uint8).reshape(
            _SLOTS, self.height, self.width, 3)
        self._depth = np.frombuffer(self._depth_raw, dtype=np.float32).reshape(
            _SLOTS, self.height, self.width)
        self._header = np.frombuffer(self._header_raw, dtype=np.float64).reshape(
            _SLOTS, _HEADER_FIELDS)
        self._locks = [ctx.Lock() for _ in range(_SLOTS)]

        self._conn, child_conn = ctx.Pipe(duplex=True)
        kwargs = dict(camera_kwargs, width=self.width, height=self.height,
                      timeout_ms=int(timeout_ms))
        self._process = ctx.Process(
            target=_camera_worker,
            name="camera-process",
            args=(child_conn, self._color_raw, self._depth_raw, self._header_raw,
                  self._locks, (self.height, self.width), camera_factory, kwargs,
                  os.getpid()),
            daemon=True,
        )
        self._process.start()
        child_conn.close()  # the child's end lives in the child now

        try:
            self._wait_ready(start_timeout_s)
        except BaseException:
            self.close()
            raise

    def _wait_ready(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CameraUnavailableError(
                    f"camera process did not open the camera within {timeout_s:.0f} s")
            if self._conn.poll(min(remaining, 0.1)):
                message = self._receive()
                if message[0] == "ready":
                    self._info = dict(message[1] or {})
                    self.intrinsics = message[2]
                    return
            elif not self._process.is_alive():
                raise CameraUnavailableError(
                    f"camera process exited while opening the camera "
                    f"(exit code {self._process.exitcode})")

    def _receive(self):
        try:
            message = self._conn.recv()
        except (EOFError, OSError) as exc:
            raise CameraReadError(
                f"camera process exited (exit code {self._process.exitcode})") from exc
        if message[0] == "error":
            _raise_child_error(message[1], message[2])
        return message

    def read(self):
        if self._closed:
            raise CameraReadError("camera process is closed")
        started = time.perf_counter()
        deadline = time.monotonic() + self.timeout_s
        while True:
            # The newest published slot; older messages are skipped.
            slot = None
            while self._conn.poll(0):
                message = self._receive()
                if message[0] == "frame":
                    slot = message[1]
            if slot is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CameraReadError(
                        f"camera process sent no frame for {self.timeout_s:.1f} s")
                if not self._conn.poll(min(remaining, 0.1)):
                    if not self._process.is_alive():
                        raise CameraReadError(
                            f"camera process exited (exit code {self._process.exitcode})")
                    continue
                continue  # a message arrived: drain it above
            waited = time.perf_counter() - started
            t0 = time.perf_counter()
            with self._locks[slot]:
                header = self._header[slot].copy()
                if header[0] <= self._last_seq:
                    continue  # already returned (rewritten since): wait for a newer one
                color = self._color[slot].copy()
                depth = self._depth[slot].copy()
            self._last_seq = header[0]
            self.last_read_timings = {
                "wait": waited,                       # main waiting for a new frame
                "copy": time.perf_counter() - t0,     # main copying it out
                "align": float(header[3]),            # child, off the main loop
                "child_wait": float(header[2]),
                "child_convert": float(header[4]) + float(header[5]),
            }
            timestamp = None if math.isnan(header[1]) else float(header[1])
            return CameraFrame(color=color, depth_mm=depth,
                               intrinsics=self.intrinsics, timestamp_ms=timestamp)

    def info(self) -> Dict[str, object]:
        info = dict(self._info)
        info["capture"] = "separate process"
        return info

    def print_info(self):
        print("Camera source: Solomon / Intel RealSense (capture in a separate process)")
        for key, value in self.info().items():
            if key != "source":
                print(f"  {key}: {value}")

    def close(self):
        if self._closed:
            return
        self._closed = True
        _send_quietly(self._conn, ("stop",))
        self._process.join(STOP_TIMEOUT_S)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(STOP_TIMEOUT_S)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(STOP_TIMEOUT_S)
        try:
            self._conn.close()
        except OSError:
            pass


def create_process_camera(
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
    """Same arguments as camera_source.create_camera. RealSense is captured
    in a separate process; the OpenCV webcam (bench) stays in-process."""
    if str(source).strip().lower() != "realsense":
        return create_camera(source, camera_index=camera_index, width=width,
                             height=height, fps=fps, serial_number=serial_number,
                             timeout_ms=timeout_ms, warmup_frames=warmup_frames,
                             enable_emitter=enable_emitter)
    return ProcessCamera(
        width=width,
        height=height,
        timeout_ms=timeout_ms,
        fps=fps,
        serial_number=serial_number,
        warmup_frames=warmup_frames,
        enable_emitter=enable_emitter,
    )
