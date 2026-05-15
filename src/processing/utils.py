
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


def to_preview_texture(img: np.ndarray, tex_w: int, tex_h: int) -> np.ndarray:
    # Letterbox resize: preserve aspect ratio, pad remainder with black, return flat RGB float32.
    img = np.nan_to_num(img, nan=0.0).astype(np.float32)
    h, w = img.shape[:2]
    scale = min(tex_w / w, tex_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))
    canvas = np.zeros((tex_h, tex_w), dtype=np.float32)
    y_off = (tex_h - new_h) // 2
    x_off = (tex_w - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    mn, mx = canvas.min(), canvas.max()
    if mx > mn:
        canvas = (canvas - mn) / (mx - mn)
    return np.stack([canvas, canvas, canvas], axis=2).flatten()
