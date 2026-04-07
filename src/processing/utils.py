"""
Stateless utility functions for frame manipulation.

No dependencies on hardware, UI, or state — safe to import anywhere,
including Jupyter notebooks and standalone scripts.
"""

import cv2
import numpy as np


def crop_frame(frame: np.ndarray, roi_pixels: tuple[int, int, int, int]) -> np.ndarray:
    """
    Crop a frame to the given pixel region.

    Parameters
    ----------
    frame      : (H, W) grayscale frame
    roi_pixels : (x1, y1, x2, y2) in pixel coordinates

    Returns
    -------
    Cropped (H', W') frame. Returns original frame if crop is invalid.
    """
    x1, y1, x2, y2 = roi_pixels
    x1 = max(0, min(x1, frame.shape[1]))
    y1 = max(0, min(y1, frame.shape[0]))
    x2 = max(0, min(x2, frame.shape[1]))
    y2 = max(0, min(y2, frame.shape[0]))
    if x2 > x1 and y2 > y1:
        return frame[y1:y2, x1:x2]
    return frame


def to_display_texture(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """
    Prepare a grayscale image for DearPyGUI raw texture display.

    Steps: resize → normalize to 0.0–1.0 → convert to flat RGB float32 array.

    Parameters
    ----------
    img : (H, W) float or uint grayscale image
    w, h: target texture dimensions

    Returns
    -------
    Flat float32 array of length w * h * 3, ready for dpg.set_value()
    """
    img = cv2.resize(img.astype(np.float32), (w, h))
    mn, mx = img.min(), img.max()
    if mx > mn:
        img = (img - mn) / (mx - mn)
    return np.stack([img, img, img], axis=2).flatten()
