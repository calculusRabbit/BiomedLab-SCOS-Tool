from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    k2: float = 0.0
    bfi: float = 0.0
    cc: float = 0.0
    od: float = 0.0
    k2_images: tuple = (None, None, None, None, None, None)


def process_all_data(frame: np.ndarray) -> SCOSResult:
    return SCOSResult(
        k2 = compute_k2(frame),
        bfi = compute_bfi(frame),
        cc = compute_cc(frame),
        od = compute_od(frame),
        k2_images = (
            compute_k2_t1(frame),
            compute_k2_t2(frame),
            compute_k2_t3(frame),
            compute_k2_t4(frame),
            compute_k2_t5(frame),
            compute_k2_t6(frame),
        )
    )


def compute_k2(frame: np.ndarray):
    return frame.mean()

def compute_bfi(frame: np.ndarray):
    return frame.mean() / 255.0 + np.random.uniform(-0.05, 0.05)

def compute_cc(frame: np.ndarray):
    return frame.std()

def compute_od(frame: np.ndarray):
    return frame.max()


# upper pannel:
def compute_k2_t1(frame):
    return frame

def compute_k2_t2(frame):
    (frame * 0.8).astype(np.float32)

def compute_k2_t3(frame):
    (frame * 0.6).astype(np.float32)

def compute_k2_t4(frame):
    (frame * 0.4).astype(np.float32)

def compute_k2_t5(frame):
    (frame * 0.2).astype(np.float32)

def compute_k2_t6(frame):
    (frame * 0.1).astype(np.float32)