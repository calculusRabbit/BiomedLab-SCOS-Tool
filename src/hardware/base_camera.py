from abc import ABC, abstractmethod

import numpy as np


class BaseCamera(ABC):

    @classmethod
    @abstractmethod
    def scan(cls) -> list[str]:
        """ Return a list of string of device names available on this computer """

    @abstractmethod
    def open(self) -> None:
        """Open and initialise the camera"""

    @abstractmethod
    def close(self) -> None:
        """Release the camera and free resources"""

    @abstractmethod
    def grab_frame(self) -> tuple[np.ndarray, int | None, int | None, int | None] | None:
        """Return (frame, cam_ts_ticks, frame_counter, exposure_end_ts) or None on failure.
        cam_ts_ticks, frame_counter, exposure_end_ts are None if unsupported."""

    @abstractmethod
    def get_gain(self) -> float:
        """Return the current gain value"""

    @abstractmethod
    def get_exposure_time(self) -> float:
        """Return the current exposure time value"""

    def set_gain(self, value: float) -> None:
        pass

    def set_exposure_time(self, value: float) -> None:
        pass

    def get_fps(self) -> float | None:
        return None

    def get_tick_frequency_hz(self) -> int | None:
        return None

    def has_camera_time(self) -> bool:
        return False

    def has_exp_end_time(self) -> bool:
        return False

    def has_frame_counter(self) -> bool:
        return False
