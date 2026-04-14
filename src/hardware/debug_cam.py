import cv2

from hardware.base_camera import BaseCamera
from config import CAMERA_DEFAULT_GAIN, CAMERA_DEFAULT_EXPOSURE


class DebugCamera(BaseCamera):
    # Loop a video file used for development without physical hardware camerea

    video_paths: list[str] = []

    def __init__(self, index: int = 0):
        self._path = self.video_paths[index]
        self._cap = None
        self._gain = CAMERA_DEFAULT_GAIN
        self._exposure_time = CAMERA_DEFAULT_EXPOSURE

    @classmethod
    def scan(cls) -> list[str]:
        return [f"Debug [{i}] {p}" for i, p in enumerate(cls.video_paths)]

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {self._path}")

    def grab_frame(self):
        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
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


    def set_gain(self, value: float) -> None:
        self._gain = value

    def get_gain(self) -> float:
        return self._gain

    def set_exposure_time(self, value: float) -> None:
        self._exposure_time = value

    def get_exposure_time(self) -> float:
        return self._exposure_time
