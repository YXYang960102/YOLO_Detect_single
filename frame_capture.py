"""Training-image capture (2026-11-14, Jeremy: this year's field graphics
differ a lot from last year's, so the model needs photos of the new field).

Saves the camera's raw color frame -- before any overlay is drawn -- as a
JPEG into one folder per program start:

    dataset_capture/20261114_153012/000001_153013.jpg

--capture-every N saves one frame every N seconds (also with --no-display,
so the robot collects while it drives in practice). The Dashboard's P key
/ the pad's View button turns it on and off from the driver station
(Mega -> MEGA_CAPTURE, set_remote(); 2026-11-14): every remote_every
seconds, or every N when --capture-every is also given. 'p' in the
display window saves one at once. The files are written by a background thread,
so the vision loop only pays for a frame copy; when the writer falls
behind, that frame is skipped instead of waiting. Saving stops once the
whole dataset_capture folder holds max_images JPEGs (the Orin's disk).
"""

import os
import queue
import threading
import time
from datetime import datetime

import cv2


class FrameCapture:
    def __init__(self, root, every_seconds=0.0, max_images=3000, jpeg_quality=95,
                 remote_every=1.0, clock=time.monotonic):
        self.root = root
        self.every_seconds = max(0.0, float(every_seconds or 0.0))
        self.remote_every = max(0.1, float(remote_every))
        self.remote_on = False
        self.max_images = int(max_images)
        self.jpeg_quality = int(jpeg_quality)
        self.clock = clock
        self.session_dir = os.path.join(root, datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.saved = 0
        self.skipped = 0
        self.total = self._count_existing()
        self._last_auto = None
        self._full_warned = False
        self._queue = queue.Queue(maxsize=2)
        self._thread = None
        if self.every_seconds > 0:
            print(f"[capture] every {self.every_seconds:.1f} s -> {self.session_dir} "
                  f"({self.total}/{self.max_images} images in {root})")

    @property
    def auto_enabled(self):
        return self.every_seconds > 0 or self.remote_on

    @property
    def interval(self):
        return self.every_seconds if self.every_seconds > 0 else self.remote_every

    def set_remote(self, on):
        """The Dashboard's P toggle, as the Mega last reported it."""
        on = bool(on)
        if on == self.remote_on:
            return
        self.remote_on = on
        if on:
            print(f"[capture] ON from the Dashboard: every {self.interval:.1f} s -> "
                  f"{self.session_dir} ({self.total}/{self.max_images})")
        else:
            print(f"[capture] OFF from the Dashboard ({self.saved} saved this run)")

    def _count_existing(self):
        count = 0
        if os.path.isdir(self.root):
            for _dirpath, _dirs, files in os.walk(self.root):
                count += sum(1 for name in files if name.lower().endswith(".jpg"))
        return count

    def maybe_save(self, frame):
        """Call once per frame: saves when --capture-every is due."""
        if not self.auto_enabled or frame is None:
            return
        now = self.clock()
        if self._last_auto is not None and now - self._last_auto < self.interval:
            return
        self._last_auto = now
        self._submit(frame)

    def save_now(self, frame):
        """The 'p' key: one frame right away, with or without --capture-every."""
        if frame is not None and self._submit(frame):
            print(f"[capture] saved #{self.total} (p)")

    def _submit(self, frame):
        if self.total >= self.max_images:
            if not self._full_warned:
                print(f"[capture] {self.root} holds {self.total} images "
                      f"(max {self.max_images}): not saving any more")
                self._full_warned = True
            return False
        self._start_writer()
        index = self.total + 1
        name = f"{index:06d}_{datetime.now().strftime('%H%M%S')}.jpg"
        try:
            self._queue.put_nowait((os.path.join(self.session_dir, name), frame.copy()))
        except queue.Full:
            self.skipped += 1
            return False
        self.total = index
        self.saved += 1
        if self.auto_enabled and self.saved % 50 == 0:
            print(f"[capture] {self.saved} saved this run ({self.total}/{self.max_images}), "
                  f"{self.skipped} skipped")
        return True

    def _start_writer(self):
        if self._thread is not None:
            return
        os.makedirs(self.session_dir, exist_ok=True)
        self._thread = threading.Thread(target=self._write_loop, name="frame-capture",
                                        daemon=True)
        self._thread.start()

    def _write_loop(self):
        params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        while True:
            item = self._queue.get()
            if item is None:
                return
            path, image = item
            try:
                if not cv2.imwrite(path, image, params):
                    print(f"[capture] could not write {path}")
            except Exception as exc:  # never take the vision loop down
                print(f"[capture] write failed: {exc}")

    def close(self, timeout=3.0):
        """Writes what is queued, then stops the writer thread."""
        if self._thread is None:
            return
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            return
        self._thread.join(timeout)
        if self.saved:
            print(f"[capture] {self.saved} saved this run in {self.session_dir}, "
                  f"{self.skipped} skipped")
