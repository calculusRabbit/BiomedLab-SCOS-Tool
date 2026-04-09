
from collections import deque

import numpy as np

from processing.scos_result import SCOSResult


WINDOW_SIZE = 7  # default window size (pixels)


def process_all_data(frame: np.ndarray, gain: float, dark_image: np.ndarray | None, frame_buf: deque) -> SCOSResult:

    k_raw2 = _compute_k_raw2(frame)
    k_s2 = _compute_k_s2(frame, gain)
    k_r2 = _compute_k_r2(frame, dark_image)
    k_sp2 = _compute_k_sp2(frame, frame_buf, gain)
    k_q2 = _compute_k_q2(frame)
    k_f2 = _compute_k_f2(k_raw2, k_s2, k_r2, k_sp2, k_q2)

    return SCOSResult(
        k2 = float(np.mean(k_f2))  if k_f2  is not None else 0.0,
        bfi = _compute_bfi(k_f2),
        cc = _compute_cc(frame),
        od = _compute_od(frame),
        k2_images = (k_raw2, k_s2, k_r2, k_sp2, k_q2, k_f2),
    )


# spatial windowing 

def _reshape_window(img: np.ndarray, window_size: int) -> np.ndarray:
    """
    Tile img into non-overlapping window_size × window_size patches.

    Returns a 2D array of shape (window_size², n_windows) where each
    column is one flattened patch — matches Dr. Gao's MATLAB convention.

    MATLAB reference:
        n_width  = floor(img_width  / window_size)
        n_height = floor(img_height / window_size)
        new_img  = img[0:n_height*window_size, 0:n_width*window_size]
        img_windowed shape: (window_size*window_size, n_windows)
    """
    h, w   = img.shape
    nw     = w // window_size
    nh     = h // window_size
    # crop so dimensions are exact multiples of window_size
    img    = img[:nh * window_size, :nw * window_size].astype(np.float64)
    # reshape into patches: (nh, window_size, nw, window_size)
    img    = img.reshape(nh, window_size, nw, window_size)
    # transpose to (nh, nw, window_size, window_size) then flatten patches
    img    = img.transpose(0, 2, 1, 3).reshape(nh * nw, window_size * window_size)
    return img.T   # (window_size², n_windows) — column = one window


def _window_output_shape(img: np.ndarray, window_size: int):
    """Return (nh, nw) — the spatial dimensions of the windowed output map."""
    return img.shape[0] // window_size, img.shape[1] // window_size


# ── K² component functions ────────────────────────────────────────────────────

def _compute_k_raw2(frame: np.ndarray) -> np.ndarray | None:
    """
    K_raw² = var(window) / mean(window)  for each spatial window.

    MATLAB reference:
        frame_windowed  = reshapeWindow(frame, window_size)
        windowed_mean   = mean(frame_windowed, 1)
        windowed_var    = var(frame_windowed, 1)
        K_raw_squared   = windowed_var ./ windowed_mean
    """
    # TODO: implement
    return None


def _compute_k_s2(frame: np.ndarray, gain: float) -> np.ndarray | None:
    """
    K_s² = gain / windowed_mean   (shot noise term).

    MATLAB reference:
        Ks2 = Gain ./ windowed_mean
    """
    # TODO: implement
    return None


def _compute_k_r2(
    frame: np.ndarray,
    dark_image: np.ndarray | None,
) -> np.ndarray | None:
    """
    K_r² = (mean(var(dark_windows)) - 1/12) / windowed_mean²   (read noise term).

    Requires a calibration dark image captured with the lens cap on.
    Returns None if dark_image is not available yet.

    MATLAB reference:
        dark_windowed         = reshapeWindow(average_dark_img, window_size)
        windowed_variance_dark = var(dark_windowed)
        Kr2 = (mean(windowed_variance_dark) - 1/12) ./ (windowed_mean .^ 2)
    """
    if dark_image is None:
        return None
    # TODO: implement
    return None


def _compute_k_sp2(
    frame: np.ndarray,
    frame_buf: deque,
    gain: float,
) -> np.ndarray | None:
    """
    K_sp² = spatial variance of the 50-frame temporal mean (spatial noise term).

    Returns zeros if fewer than 50 frames are available.

    MATLAB reference:
        if length(previous_frames) < 50:
            Ksp2 = zeros(size(frame))
        else:
            mean_50_frames         = mean(previous_frames)
            mean_50_frames_windowed = reshapeWindow(mean_50_frames, window_size)
            spatial_variance       = var(mean_50_frames_windowed, 0, 1)
            spatial_mean           = mean(mean_50_frames_windowed, 1)
            spatial_variance       = spatial_variance - Gain * spatial_mean / 50
            Ksp2 = spatial_variance ./ (spatial_mean .^ 2)
    """
    if len(frame_buf) < 50:
        return None
    # TODO: implement
    return None


def _compute_k_q2(frame: np.ndarray) -> np.ndarray | None:
    """
    K_q² = (1/12) / windowed_mean²   (quantization noise term).

    MATLAB reference:
        Kq2 = 1/12 ./ (windowed_mean .^ 2)
    """
    # TODO: implement
    return None


def _compute_k_f2(
    k_raw2:  np.ndarray | None,
    k_s2:    np.ndarray | None,
    k_r2:    np.ndarray | None,
    k_sp2:   np.ndarray | None,
    k_q2:    np.ndarray | None,
) -> np.ndarray | None:
    """
    K_f² = K_raw² - K_s² - K_r² - K_sp² - K_q²   (final blood-flow term).

    Any None component is treated as zero so the app keeps running
    while calibration data (dark image, frame history) is being collected.

    MATLAB reference:
        Kf2 = Kraw2 - Ks2 - Kr2 - Kq2 - Ksp2
    """
    if k_raw2 is None:
        return None
    result = k_raw2.copy()
    for component in (k_s2, k_r2, k_sp2, k_q2):
        if component is not None:
            result = result - component
    return result


# ── scalar metrics ────────────────────────────────────────────────────────────

def _compute_bfi(k_f2: np.ndarray | None) -> float:
    """
    BFI = 1 / mean(K_f²)

    MATLAB reference:
        BFI = 1 / mean(Kf2)
    """
    if k_f2 is None or np.mean(k_f2) == 0:
        return 0.0
    # TODO: implement properly
    return 0.0


def _compute_cc(frame: np.ndarray) -> float:
    """
    CC = windowed_mean (spatial mean of the ROI).

    MATLAB reference:
        cc = windowed_mean
    """
    # TODO: implement
    return 0.0


def _compute_od(frame: np.ndarray) -> float:
    """
    OD = -log10( |mean(frame)| / mean(frame[0]) )

    MATLAB reference:
        OD = -log10(abs(windowed_mean) ./ (ones(nTpts,1) * windowed_mean(1)))
    """
    # TODO: implement
    return 0.0
