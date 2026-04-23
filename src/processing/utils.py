
# No dependencies on hardware, UI, or state = safe to import anywhere

# these are just helper function


import cv2
import numpy as np


def crop_frame(frame: np.ndarray, roi_pixels: tuple[int, int, int, int]) -> np.ndarray:
    
    ## Crop a frame to the given pixel region.
    # Returns cropped (H', W') frame. Returns original frame if crop is invalid.
    
    x1, y1, x2, y2 = roi_pixels
    x1 = max(0, min(x1, frame.shape[1]))
    y1 = max(0, min(y1, frame.shape[0]))
    x2 = max(0, min(x2, frame.shape[1]))
    y2 = max(0, min(y2, frame.shape[0]))
    if x2 > x1 and y2 > y1:
        return frame[y1:y2, x1:x2]
    return frame


def to_display_texture(img: np.ndarray, w: int, h: int) -> np.ndarray:
    # Resize -> normalize to [0, 1] -> flat float32 RGB for dpg.set_value().
    # NaN values (from zero-mean windows) are zeroed before resize so cv2 behaves correctly.
    img = np.nan_to_num(img, nan=0.0).astype(np.float32)
    img = cv2.resize(img, (w, h))
    mn, mx = img.min(), img.max()
    if mx > mn:
        img = (img - mn) / (mx - mn)
    return np.stack([img, img, img], axis=2).flatten()
