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
    def grab_frame(self) -> tuple[np.ndarray, int | None, int | None] | None:
        """Return (frame, camera_ts_ticks, frame_counter) or None on failure.
        camera_ts_ticks and frame_counter are None if the camera does not support chunk data."""

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
