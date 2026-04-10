from collections import deque

import numpy as np

from config import MAX_PLOT_POINTS
from processing.scos_result import SCOSResult


class SCOSTimeSeries:
    
    # Rolling time-series buffers for one camera session.


    # Designed so adding SNIRF/BIDS saving later is one method:
    # def save_snirf(self, path)
    

    def __init__(self):
        self.start_time: float = 0.0
        self._last_result: SCOSResult | None = None

        self._t_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._k2_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._bfi_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._cc_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._od_buf = deque(maxlen=MAX_PLOT_POINTS)

    ## WRITE ##

    def push(self, t: float, result: SCOSResult) -> None:
        self._t_buf.append(t)
        self._k2_buf.append(result.k2)
        self._bfi_buf.append(result.bfi)
        self._cc_buf.append(result.cc)
        self._od_buf.append(result.od)
        self._last_result = result

    def clear(self) -> None:
        for buf in (self._t_buf, self._k2_buf, self._bfi_buf, self._cc_buf, self._od_buf):
            buf.clear()
        self.start_time   = 0.0
        self._last_result = None

    ## READ ##

    def latest(self) -> SCOSResult | None:
        """Return the most recent SCOSResult, or None if no data yet."""
        return self._last_result

    def as_lists(self) -> tuple[list, list, list, list, list]:
        """Return (t, k2, bfi, cc, od) as plain lists — ready for DearPyGUI plots."""
        return (
            list(self._t_buf),
            list(self._k2_buf),
            list(self._bfi_buf),
            list(self._cc_buf),
            list(self._od_buf),
        )

    def __bool__(self) -> bool:
        return len(self._t_buf) > 0
