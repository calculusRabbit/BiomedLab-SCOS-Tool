from abc import ABC, abstractmethod

import numpy as np


class BaseCamera(ABC):

    @classmethod
    @abstractmethod
    def scan(cls) -> list[str]:
        """Return a list of human-readable device names available on this machine."""

    @abstractmethod
    def open(self) -> None:
        """Open and initialise the camera."""

    @abstractmethod
    def close(self) -> None:
        """Release the camera and free resources."""

    @abstractmethod
    def grab_frame(self) -> np.ndarray | None:
        """Return the latest grayscale frame as a (H, W) uint array, or None on failure."""

    # Optional hardware controls — subclasses override if the hardware supports them.
    # Default implementations are no-ops so DebugCamera doesn't need to implement them.

    def set_gain(self, value: float) -> None:
        pass

    def set_exposure_time(self, value: float) -> None:
        pass
