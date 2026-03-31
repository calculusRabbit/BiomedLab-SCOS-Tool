import cv2
import numpy as np
from model.base_camera import BaseCamera

class DebugCamera(BaseCamera):
    def __init__(self, video_path):
        self._path = video_path
        self._cap: cv2.VideoCapture
        self.fps = 100.0

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {self._path}")
        self.fps = 100.0

    def grab_frame(self):
        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # loop
            ret, frame = self._cap.read()
        if not ret:
            return None
    
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
