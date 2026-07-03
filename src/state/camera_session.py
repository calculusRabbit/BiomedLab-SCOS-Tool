import numpy as np

from state.roi_set import ROISet
from state.scos_timeseries import SCOSTimeSeries


class CameraSession:
    # Holds everything associated with one connected camera.

    # Created by CameraManager when a camera is scanned. One session
    # per physical camera, persists until the next scan.

    def __init__(self, cam_id: str, pipeline):
        self.cam_id: str= cam_id
        self.pipeline= pipeline
        self.is_connected: bool= False
        self.roi_set: ROISet= ROISet()
        self.data: SCOSTimeSeries = SCOSTimeSeries()
        self.last_frame: np.ndarray | None = None  # most recent full frame shown in the UI

    def sync_pipeline_roi(self) -> None:
        # push the current ROI (in sensor pixels) down to the pipeline
        # call this after connecting or after the user moves the ROI
        self.pipeline.set_roi(self.roi_set.to_pixels("1"))

    def reset(self, start_time: float) -> None:
        # clear accumulated plot data and reset the processor baseline
        # called at the start of each preview or recording session
        self.data.clear()
        self.data.start_time = start_time
        self.pipeline.reset_processor()
