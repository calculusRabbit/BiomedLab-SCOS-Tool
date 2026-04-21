import numpy as np

from state.roi_set import ROISet
from state.scos_timeseries import SCOSTimeSeries


class CameraSession:
    
    # Everything that belongs to one connected camera:
    #   hardware pipeline reference
    #   connection state
    #   ROI coordinates
    #   time-series data buffers

    # The controller creates sessions via CameraManager.

    def __init__(self, cam_id: str, pipeline):
        self.cam_id: str= cam_id
        self.pipeline= pipeline
        self.is_connected: bool= False
        self.roi_set: ROISet= ROISet()
        self.data: SCOSTimeSeries = SCOSTimeSeries()
        self.last_frame: np.ndarray | None = None

    def sync_pipeline_roi(self) -> None:
        self.pipeline.set_roi(self.roi_set.to_pixels("source"))

    def reset(self, start_time: float) -> None:
        self.data.clear()
        self.data.start_time = start_time
        self.pipeline.reset_temporal_buffer()
