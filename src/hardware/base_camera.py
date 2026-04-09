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
    def grab_frame(self) -> np.ndarray | None:
        """Return the latest grayscale frame as a (H, W) uint array, or None on failure"""


    def set_gain(self, value: float) -> None:
        pass

    def set_exposure_time(self, value: float) -> None:
        pass
