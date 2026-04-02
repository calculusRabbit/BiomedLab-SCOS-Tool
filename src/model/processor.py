from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    k2: float = 0.0
    bfi: float = 0.0
    cc: float = 0.0
    od: float = 0.0
<<<<<<< HEAD
    k2_images: tuple = (None, None, None, None, None, None)
=======
    k2_image: np.ndarray | None = None
>>>>>>> main


def process_all_data(frame: np.ndarray) -> SCOSResult:
    return SCOSResult(
        k2 = compute_k2(frame),
        bfi = compute_bfi(frame),
        cc = compute_cc(frame),
        od = compute_od(frame),
<<<<<<< HEAD
        # below K2 image for left upper panel
        k2_images = (
            frame, # The very first bar on the left index 0 raw crop always shown
            compute_k2_t1(frame), # index 1
            compute_k2_t2(frame), # index 2
            compute_k2_t3(frame), # index 3
            compute_k2_t4(frame), # index 4
            compute_k2_t5(frame), # index 5
        )
=======
>>>>>>> main
    )


def compute_k2(frame: np.ndarray):
    return frame.mean()

def compute_bfi(frame: np.ndarray):
    return frame.mean() / 255.0 + np.random.uniform(-0.05, 0.05)

def compute_cc(frame: np.ndarray):
    return frame.std()

def compute_od(frame: np.ndarray):
<<<<<<< HEAD
    return frame.max()

# FOR UPPER LEFT PANEL
def compute_k2_t1(frame: np.ndarray):
    return (frame * 0.8)

def compute_k2_t2(frame: np.ndarray):
    return (frame * 0.6)

def compute_k2_t3(frame: np.ndarray):
    return (frame * 0.4)

def compute_k2_t4(frame: np.ndarray):
    return (frame * 0.2)

def compute_k2_t5(frame: np.ndarray):
    return (frame * 0.1)
=======
    return frame.max()
>>>>>>> main
