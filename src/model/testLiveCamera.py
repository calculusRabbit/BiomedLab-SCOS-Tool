import cv2
import numpy as np


class testLiveCamera:

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self._vid = None

    def start(self):
        self._vid = cv2.VideoCapture(0)

    def stop(self):
        if self._vid:
            self._vid.release()

    def get_processed_frame(self):
        if self._vid is None:
            return None
        ret, frame = self._vid.read()
        if not ret:
            return None
        frame = cv2.resize(frame, (self.width, self.height))
        data = np.flip(frame, 2).ravel().astype("f") / 255.0
        return {"frame": data}