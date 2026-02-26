import cv2
import threading
import numpy as np


class testLiveCamera:

    def __init__(self):
        self.latest_frame = None
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _capture_loop(self):
        vid = cv2.VideoCapture(0)
        while self._running:
            ret, frame = vid.read()
            if ret:
                with self._lock:
                    self.latest_frame = frame
        vid.release()

    def get_frame(self):
        with self._lock:
            if self.latest_frame is None:
                return None
            gray = cv2.cvtColor(self.latest_frame, cv2.COLOR_BGR2GRAY)
            heat = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
            return heat