"""
Worker thread — grabs frames from the camera, runs processing, feeds the UI queue.

Queue maxsize=1: always keeps the latest frame and drops stale ones.
This is intentional — the UI wants current data, not a backlog.

The pipeline also owns all parameters that the processing functions need:
  gain        — camera gain value, forwarded to K_s² computation
  dark_image  — calibration image, forwarded to K_r² computation
  roi_pixels  — (x1, y1, x2, y2) crop applied before processing
  _frame_buf  — rolling 50-frame history for K_sp² computation
"""

import queue
import threading
from collections import deque

import numpy as np

from hardware.base_camera import BaseCamera
from processing.processor import process_all_data
from processing.utils import crop_frame


_FRAME_BUF_SIZE = 50


class Pipeline:

    def __init__(self, camera: BaseCamera):
        self._camera  = camera
        self._queue   = queue.Queue(maxsize=1)
        self._thread  = None
        self._running = False

        self._frame_buf: deque[np.ndarray] = deque(maxlen=_FRAME_BUF_SIZE)

        # Settable from the controller in real time — safe because they are
        # read atomically (single Python assignment is thread-safe for simple types).
        self.roi_pixels:  tuple | None       = None
        self.gain:        float              = 10.0
        self.dark_image:  np.ndarray | None  = None

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._camera.open()
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._camera.close()

    def get_latest(self):
        """Non-blocking. Returns (full_frame, SCOSResult) or None. Call from UI thread."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def set_gain(self, value: float) -> None:
        self.gain = value
        self._camera.set_gain(value)

    def set_exposure_time(self, value: float) -> None:
        self._camera.set_exposure_time(value)

    # ── worker thread ─────────────────────────────────────────────────────────

    def _run(self) -> None:
        while self._running:
            frame = self._camera.grab_frame()
            if frame is None:
                continue

            full_frame = frame
            cropped    = crop_frame(frame, self.roi_pixels) if self.roi_pixels else frame

            # Pass frame_buf BEFORE appending current frame so K_sp² sees only past frames.
            output = process_all_data(
                frame       = cropped,
                gain        = self.gain,
                dark_image  = self.dark_image,
                frame_buf   = self._frame_buf,
            )

            self._frame_buf.append(cropped.copy())

            try:
                self._queue.put_nowait((full_frame, output))
            except queue.Full:
                pass

