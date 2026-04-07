from __future__ import annotations

import numpy as np

from state.roi_set import ROISet
from state.scos_timeseries import SCOSTimeSeries


class CameraSession:
    """
    Everything that belongs to one connected camera:
      - hardware pipeline reference
      - connection state
      - ROI coordinates
      - time-series data buffers

    The controller creates sessions via CameraManager.
    The controller reads session state but never mutates data buffers directly
    — it calls session.data.push() and session.data.clear().
    """

    def __init__(self, cam_id: str, pipeline):
        self.cam_id:      str                  = cam_id
        self.pipeline                          = pipeline
        self.is_connected: bool                = False
        self.roi_set:      ROISet              = ROISet()
        self.data:         SCOSTimeSeries      = SCOSTimeSeries()
        self.last_frame:   np.ndarray | None   = None
