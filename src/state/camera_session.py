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
        self.last_frame: np.ndarray | None = None  # most recent full frame, used for dark capture preview
        self._dark_image: np.ndarray | None = None

    @property
    def dark_image(self) -> np.ndarray | None:
        return self._dark_image

    @dark_image.setter
    def dark_image(self, img: np.ndarray | None) -> None:
        # keep a reference here AND push to the pipeline so both stay in sync
        # important: the image must already be cropped to ROI "1" before setting
        self._dark_image = img
        self.pipeline.set_dark_image(img)

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
