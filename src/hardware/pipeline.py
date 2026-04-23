# Worker thread: grab frames → process → feed the UI queue.

# Queue maxsize=1: always delivers the latest frame, drops stale ones.

# Pipeline is pure hardware: grab → crop → hand to Processor → queue result.


import queue
import threading
import time

import numpy as np

from config import DARK_IMAGE_PATH
from hardware.base_camera import BaseCamera
from processing.processor import Processor
from processing.utils import crop_frame


class Pipeline:

    def __init__(self, camera: BaseCamera):
        self._camera = camera
        self._queue = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._running = False

        self._processor = Processor()
        self._roi_pixels: tuple | None      = None
        self._dark_image: np.ndarray | None = None

        self.crashed: bool = False

        # FPS stats — updated every 2 s, readable by the UI for a future stats panel
        self.fps_camera: float = 0.0
        self.fps_processed: float = 0.0
        self.drop_rate: float = 0.0

        self._grabbed = 0
        self._processed = 0
        self._dropped = 0
        self._log_time = 0.0
        self._start_time = 0.0



    def start(self) -> None:
        if self._running:
            return
        self._camera.open()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if DARK_IMAGE_PATH:
            self.load_dark_image_from_file(DARK_IMAGE_PATH)

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

    def set_roi(self, roi_pixels: tuple | None) -> None:
        self._roi_pixels = roi_pixels

    def set_dark_image(self, img: np.ndarray | None) -> None:
        """Pass a full-frame dark image array for subtraction. None disables subtraction."""
        self._dark_image = img.astype(np.float64) if img is not None else None

    def load_dark_image_from_file(self, path: str) -> None:
        """Load a grayscale dark image from disk and set it. Logs if file not found."""
        import cv2
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            self.set_dark_image(img)
            print(f"[Pipeline] dark image loaded: {path}")
        else:
            print(f"[Pipeline] dark image not found: {path}")

    def reset_processor(self) -> None:
        """Reset all processing state — call when starting a new recording session."""
        self._processor.reset()

    def set_gain(self, value: float) -> None:
        self._camera.set_gain(value)

    def set_exposure_time(self, value: float) -> None:
        self._camera.set_exposure_time(value)

    # worker thread

    def _run(self) -> None:
        self._start_time = self._log_time = time.time()
        while self._running:
            try:
                frame = self._camera.grab_frame()
                if frame is None:
                    continue

                self._grabbed += 1
                full_frame = frame

                if self._roi_pixels:
                    cropped = crop_frame(frame, self._roi_pixels)
                    dark_cropped = crop_frame(self._dark_image, self._roi_pixels) if self._dark_image is not None else None
                else:
                    cropped = frame
                    dark_cropped = self._dark_image

                output = self._processor.process(cropped, dark_cropped)

                try:
                    self._queue.put_nowait((full_frame, output))
                    self._processed += 1
                except queue.Full:
                    self._dropped += 1

                self._update_stats()

            except Exception as e:
                print(f"[Pipeline._run] {e}")
                self.crashed = True
                self._running = False

    def _update_stats(self) -> None:
        now = time.time()
        interval = now - self._log_time
        if interval < 2.0:
            return

        self.fps_camera = self._grabbed   / interval
        self.fps_processed = self._processed / interval
        self.drop_rate = 100 * self._dropped / self._grabbed if self._grabbed else 0.0
        elapsed = now - self._start_time

        print(
            f"[Pipeline] t={elapsed:.1f}s | "
            f"camera: {self.fps_camera:.1f} fps | "
            f"processed: {self.fps_processed:.1f} fps | "
            f"drop rate: {self.drop_rate:.1f}%"
        )

        self._grabbed = self._processed = self._dropped = 0
        self._log_time = now
