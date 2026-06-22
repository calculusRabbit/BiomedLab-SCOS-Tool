import time
from pathlib import Path

import cv2
import numpy as np

from hardware.base_camera import BaseCamera
from config import CAMERA_DEFAULT_GAIN, CAMERA_DEFAULT_EXPOSURE


class DebugCamera(BaseCamera):
    # Fake camera that replays PNG frames from a folder at a fixed FPS.
    # Set DebugCamera.folder_paths before instantiating, one path per camera index.
    # Hardware timestamps and frame counters are not available, so those return None.

    folder_paths: list[str] = []
    target_fps: float = 30.0

    def __init__(self, serial: str):
        index = int(serial.split("-")[1])
        self._serial = serial
        self._folder = Path(self.folder_paths[index])
        self._frames: list[Path] = []
        self._index: int = 0
        self._gain: float = CAMERA_DEFAULT_GAIN
        self._exposure_time: float = CAMERA_DEFAULT_EXPOSURE
        self._next_frame_time: float = 0.0

    @classmethod
    def scan(cls) -> list[tuple[str, str]]:
        result = []
        for i in range(len(cls.folder_paths)):
            result.append((f"DEBUG-{i}", "DebugCamera"))
        return result

    def open(self) -> None:
        self._frames = sorted(self._folder.glob("*.png"))
        if not self._frames:
            raise FileNotFoundError(f"No PNG files in: {self._folder}")
        self._index = 0
        self._next_frame_time = time.time()

    def grab_frame(self) -> tuple[np.ndarray, None, None, None] | None:
        frame = cv2.imread(str(self._frames[self._index]), cv2.IMREAD_GRAYSCALE)
        self._index = (self._index + 1) % len(self._frames)

        if frame is None:
            return None

        self._next_frame_time += 1.0 / self.target_fps
        remaining = self._next_frame_time - time.time()
        if remaining > 0:
            time.sleep(remaining)

        return frame, None, None, None

    def close(self) -> None:
        self._frames = []
        self._index = 0

    def get_serial(self) -> str:
        return self._serial

    def get_model(self) -> str:
        return "DebugCamera"

    def set_gain(self, value: float) -> None:
        self._gain = value

    def get_gain(self) -> float:
        return self._gain

    def set_exposure_time(self, value: float) -> None:
        self._exposure_time = value

    def get_exposure_time(self) -> float:
        return self._exposure_time

    def get_fps(self) -> float | None:
        return self.target_fps
