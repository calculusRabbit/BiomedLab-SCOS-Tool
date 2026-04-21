from collections import deque

import numpy as np


class TemporalBuffer:

    def __init__(self, max_frames: int = 50):
        self._max_frames = max_frames
        self._buf: deque[np.ndarray] = deque(maxlen=max_frames)
        self._running_sum: np.ndarray | None = None
        self._frame_count: int = 0

    def update(self, frame: np.ndarray) -> np.ndarray | None:
        frame = frame.astype(np.float64)

        if self._running_sum is not None and frame.shape != self._running_sum.shape:
            self._buf.clear()
            self._running_sum = None
            self._frame_count = 0

        if self._running_sum is None:
            self._running_sum = frame.copy()
        elif self._frame_count < self._max_frames:
            self._running_sum += frame
        else:
            # rolling mean: subtract evicted frame before deque drops it
            self._running_sum = self._running_sum - self._buf[0] + frame

        self._buf.append(frame)
        self._frame_count = min(self._frame_count + 1, self._max_frames)

        if self._frame_count < self._max_frames:
            return None  # still warming up

        return self._running_sum / self._max_frames

    def reset(self) -> None:
        self._buf.clear()
        self._running_sum = None
        self._frame_count = 0
