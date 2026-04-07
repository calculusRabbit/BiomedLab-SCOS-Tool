from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    """
    Immutable output of one processed frame.

    Scalar metrics (k2, bfi, cc, od) are single float values — the mean
    across all windows in the ROI for that frame.

    k2_maps is a tuple of 6 spatial images, one per K² component:
        [0] K_raw²   raw speckle contrast squared
        [1] K_s²     shot noise component
        [2] K_r²     read noise component
        [3] K_sp²    spatial noise component
        [4] K_q²     quantization noise component
        [5] K_f²     final blood-flow term  (K_raw² - K_s² - K_r² - K_sp² - K_q²)
    """
    k2:     float = 0.0
    bfi:    float = 0.0
    cc:     float = 0.0
    od:     float = 0.0
    k2_maps: tuple = field(default_factory=lambda: (None,) * 6)
