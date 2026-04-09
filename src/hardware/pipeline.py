# Worker thread: grab frames from the camera -> run processing -> feed the UI queue.

# Queue maxsize=1: always keep the latest frame and drop stale ones.
# So the UI can have current data, not a previous history data

# The pipeline also have parameters that the processing functions need:
#   gain
#   dark_image
#   roi_pixels
#   frame_buf


import queue
import threading
from collections import deque

import cv2
import numpy as np

from hardware.base_camera import BaseCamera
from processing.processor import process_all_data
from processing.utils import crop_frame


_FRAME_BUF_SIZE = 50


class Pipeline:

    def __init__(self, camera: BaseCamera):
        self._camera = camera
        self._queue = queue.Queue(maxsize=1)
        self._thread = None
        self._running = False

        self._frame_buf: deque[np.ndarray] = deque(maxlen=_FRAME_BUF_SIZE)

        self.roi_pixels:  tuple | None = None
        self.gain: float = 10.0
        # TESTING, CHANGE THIS LATER!!!
        # Load dark image as grayscale and convert to float64
        dark_img = cv2.imread("debug_data/dark.png", cv2.IMREAD_GRAYSCALE)
        if dark_img is not None:
            self.dark_image: np.ndarray | None = dark_img.astype(np.float64)
        else:
            self.dark_image: np.ndarray | None = None

    ## public API ##

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
        ## Non-blocking. Returns (full_frame, SCOSResult) or None. Call from UI thread ##
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def set_gain(self, value: float) -> None:
        self.gain = value
        self._camera.set_gain(value)

    def set_exposure_time(self, value: float) -> None:
        self._camera.set_exposure_time(value)

    ## worker thread ##

    def _run(self) -> None:
        while self._running:
            try:
                frame = self._camera.grab_frame()
                if frame is None:
                    continue
                
                full_frame = frame
                if self.roi_pixels:
                    cropped = crop_frame(frame, self.roi_pixels)
                else:
                    cropped = frame

                # dark_cropped
                ## testing, remember to remove it later ##
                if self.dark_image is not None and self.roi_pixels:
                    dark_cropped = crop_frame(self.dark_image, self.roi_pixels)
                else:
                    dark_cropped = self.dark_image
                ## testing, remember to remove it later ##

                # Pass frame_buf BEFORE appending current frame so k2^2sp sees only past frames
                output = process_all_data(
                    frame = cropped,
                    gain = self.gain,
                    dark_image = dark_cropped,
                    frame_buf = self._frame_buf,
                )

                self._frame_buf.append(cropped.copy())

                try:
                    self._queue.put_nowait((full_frame, output))
                except queue.Full:
                    pass
            except Exception as e:
                print(f"[Pipeline._run] {e}")
                break

