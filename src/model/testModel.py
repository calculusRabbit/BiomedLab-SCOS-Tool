import cv2
import time
import numpy as np
from dataclasses import dataclass
from scipy.ndimage import gaussian_filter


# ── Data contract ────────────────────────────────────────────
@dataclass
class SCOSResult:
    frame:     np.ndarray = None  # camera image → texture
    heat_maps: list       = None  # 6 x 2D numpy arrays → heat bars
    k2:        float      = 0.0   # scalar → K² plot
    bfi:       float      = 0.0   # scalar → BFI plot
    cc:        float      = 0.0   # scalar → CC plot
    od:        float      = 0.0   # scalar → OD plot
    time:      float      = 0.0   # timestamp → x axis


# ── Test model ───────────────────────────────────────────────
class TestModel:
    """
    Temporary test model — replace with real SCOSProcessor later.
    Professor's real computation goes in a new file, not here.
    Can be tested standalone: python -m model.test_model
    """

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height
        self._vid   = None

    # ── Lifecycle ────────────────────────────────────────────

    def start(self):
        self._vid = cv2.VideoCapture(0)


    # ── Main entry point ─────────────────────────────────────

    def get_result(self):
        frame = self._get_frame()
        if frame is None:
            return None
        return SCOSResult(
            frame     = frame,
            heat_maps = self._compute_heat_maps(),
            #k2        = float(np.random.uniform(0.1, 0.9)),
            #bfi       = float(np.random.uniform(0.1, 0.9)),
            #cc        = float(np.random.uniform(0.1, 0.9)),
            #od        = float(np.random.uniform(0.1, 0.9)),
            #time      = time.time(),
        )

    # ── Internal helpers ─────────────────────────────────────

    def _get_frame(self):
        if self._vid is None:
            return None
        ret, frame = self._vid.read()
        if not ret:
            return None
        frame = cv2.resize(frame, (self.width, self.height))
        frame = cv2.applyColorMap(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
            cv2.COLORMAP_JET
        )
        return np.flip(frame, 2).ravel().astype("f") / 255.0

    def _compute_heat_maps(self):
        # 6 fake K^2 map, returns list of 2D numpy arrays
        maps = []
        for _ in range(6):
            data = np.random.uniform(0, 1, (50, 10))
            smooth = gaussian_filter(data, sigma=3)
            smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
            maps.append(smooth.astype(float))
        return maps 


# Standalone test 
if __name__ == "__main__":
    model = TestModel(width=640, height=480)
    model.start()
    result = model.get_result()
    print("frame length:", len(result.frame))
    print("heat maps:   ", len(result.heat_maps))
    print("heat map shape:", result.heat_maps[0].shape)
    print("k2:          ", result.k2)
    print("bfi:         ", result.bfi)
    print("time:        ", result.time)