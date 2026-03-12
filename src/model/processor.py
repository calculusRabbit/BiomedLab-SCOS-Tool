# model/processor.py — DR. GAO'S FILE
#
# Input:  grayscale uint8 NumPy array (H, W)
# Output: SCOSResult with all fields filled in
#
# Standalone usage (no GUI needed):
#   from model.processor import process_all_data
#   result = process_all_data(frame)

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    frame:    np.ndarray
    k2:       float = 0.0
    bfi:      float = 0.0
    cc:       float = 0.0
    od:       float = 0.0
    k2_image: np.ndarray | None = None


def process_all_data(frame: np.ndarray) -> SCOSResult:
    return SCOSResult(
        frame = frame,
        k2    = compute_k2(frame),
        bfi   = compute_bfi(frame),
        cc    = compute_cc(frame),
        od    = compute_od(frame),
    )


def compute_k2(frame: np.ndarray) -> float:
    return frame.mean()

def compute_bfi(frame: np.ndarray) -> float:
    return frame.mean() / 255.0 + np.random.uniform(-0.05, 0.05)

def compute_cc(frame: np.ndarray) -> float:
    return frame.std()

def compute_od(frame: np.ndarray) -> float:
    return frame.max()