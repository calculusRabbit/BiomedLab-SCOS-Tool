from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SCOSResult:

    # Immutable output of one processed frame.

    # (k2, bfi, cc, od) are single float values
    # across all windows in the ROI for that frame.

    # k2_images is a tuple of 6 spatial images, one per K^2 component:
        # [0] K_raw^2   raw speckle contrast squared
        # [1] K_s^2
        # [2] K_r^2
        # [3] K_sp^2
        # [4] K_q^2
        # [5] K_f^2 final blood-flow term  (K_raw² - K_s² - K_r² - K_sp² - K_q²)

    k2: float = 0.0
    bfi: float = 0.0
    cc: float = 0.0
    od: float = 0.0
    k2_images: tuple = (None,) * 6
