from collections import deque

import numpy as np
from pypylon import pylon, genicam

from hardware.base_camera import BaseCamera
from config import CAMERA_PIXEL_FORMAT, CAMERA_DEFAULT_GAIN, CAMERA_DEFAULT_EXPOSURE


class _ExposureEndHandler(pylon.CameraEventHandler):
    # Receives ExposureEnd events from the camera in pypylon's callback thread.
    # Timestamps are pushed into a deque.
    # grab_frame() pops from the front safe because the event always arrives
    # before the corresponding frame (Basler hardware guarantee).

    def __init__(self):
        super().__init__()
        self._ts_queue: deque[int] = deque(maxlen=50)

    def OnCameraEvent(self, camera, user_id, node):
        try:
            if genicam.IsReadable(camera.EventExposureEndTimestamp):
                self._ts_queue.append(camera.EventExposureEndTimestamp.Value)
        except Exception:
            pass


class Camera(BaseCamera):

    def __init__(self, index: int = 0):
        self._camera = None
        self._index = index
        self._has_chunk_ts: bool = False
        self._has_chunk_fc: bool = False
        self._has_exp_event: bool = False
        self._exp_handler: _ExposureEndHandler | None = None

    @classmethod
    def scan(cls) -> list[str]:
        try:
            tl = pylon.TlFactory.GetInstance()
            devices = tl.EnumerateDevices()
            if not devices:
                print("[Camera.scan] no cameras found")
                return []
            return [f"Basler [{i}] {d.GetModelName()} | SN:{d.GetSerialNumber()}"
                    for i, d in enumerate(devices)]
        except Exception as e:
            print(f"[Camera.scan] {e}")
            return []

    def open(self) -> None:
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if not devices:
                raise RuntimeError("No camera found")
            self._camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[self._index]))
        except Exception:
            print("[Camera.open] EnumerateDevices failed, trying CreateFirstDevice...")
            self._camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())

        self._camera.Open()
        self._camera.PixelFormat.Value = CAMERA_PIXEL_FORMAT
        self._camera.ExposureTime.Value = CAMERA_DEFAULT_EXPOSURE
        self._camera.Gain.Value = CAMERA_DEFAULT_GAIN
        self._camera.MaxNumBuffer.Value = 20
        self._setup_chunks()
        self._setup_exposure_event()
        self._camera.StartGrabbing(pylon.GrabStrategy_OneByOne)

    def _setup_chunks(self) -> None:
        try:
            if not genicam.IsWritable(self._camera.ChunkModeActive):
                print("[Camera] chunk mode not supported")
                return

            self._camera.StaticChunkNodeMapPoolSize.Value = self._camera.MaxNumBuffer.GetValue()
            self._camera.ChunkModeActive.Value = True

            # CRC — discard corrupted frames silently in grab_frame()
            try:
                self._camera.ChunkSelector.Value = "PayloadCRC16"
                self._camera.ChunkEnable.Value = True
            except Exception:
                pass

            # Timestamp — try both names since they vary by camera model
            for selector in ["Timestamp", "Time"]:
                try:
                    self._camera.ChunkSelector.Value = selector
                    self._camera.ChunkEnable.Value = True
                    self._has_chunk_ts = True
                    break
                except Exception:
                    continue

            if not self._camera.IsUsb():
                self._camera.ChunkSelector.Value = "Framecounter"
                self._camera.ChunkEnable.Value = True
                self._has_chunk_fc = True
            else:
                print("[Camera] USB camera — frame counter chunk not available")

            print(f"[Camera] chunks — timestamp={self._has_chunk_ts}, framecounter={self._has_chunk_fc}")

        except Exception as e:
            print(f"[Camera] chunk setup failed: {e}")

    def _setup_exposure_event(self) -> None:
        try:
            if not genicam.IsAvailable(self._camera.EventSelector):
                print("[Camera] camera events not supported")
                return

            self._camera.GrabCameraEvents.Value = True
            self._camera.EventSelector.Value = "ExposureEnd"
            self._camera.EventNotification.Value = "On"

            self._exp_handler = _ExposureEndHandler()
            self._camera.RegisterCameraEventHandler(
                self._exp_handler,
                "EventExposureEndData",
                0,
                pylon.RegistrationMode_ReplaceAll,
                pylon.Cleanup_None,
            )
            self._has_exp_event = True
            print("[Camera] exposure end event enabled")
        except Exception as e:
            print(f"[Camera] exposure end event setup failed: {e}")

    def grab_frame(self) -> tuple[np.ndarray, int | None, int | None, int | None] | None:
        try:
            grab = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

            # discard corrupted frames
            if grab.HasCRC() and not grab.CheckCRC():
                print("[Camera.grab_frame] CRC mismatch — frame discarded")
                grab.Release()
                return None

            frame = grab.Array.copy()

            cam_ts = None
            if self._has_chunk_ts and genicam.IsReadable(grab.ChunkTimestamp):
                cam_ts = grab.ChunkTimestamp.Value

            frame_counter = None
            if self._has_chunk_fc and genicam.IsReadable(grab.ChunkFramecounter):
                frame_counter = grab.ChunkFramecounter.Value

            # pop matching exposure end timestamp — event always arrives before frame
            exp_end_ts = None
            if self._has_exp_event and self._exp_handler._ts_queue:
                exp_end_ts = self._exp_handler._ts_queue.popleft()

            grab.Release()
            return frame, cam_ts, frame_counter, exp_end_ts

        except Exception as e:
            print(f"[Camera.grab_frame] {e}")
            return None

    def close(self) -> None:
        try:
            if self._has_exp_event:
                self._camera.EventSelector.Value = "ExposureEnd"
                self._camera.EventNotification.Value = "Off"
            if self._camera and self._camera.IsOpen():
                if self._camera.ChunkModeActive.Value:
                    self._camera.ChunkModeActive.Value = False
                self._camera.StopGrabbing()
                self._camera.Close()
        except Exception as e:
            print(f"[Camera.close] {e}")

    def set_gain(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            self._camera.Gain.Value = value

    def get_gain(self) -> float:
        if self._camera and self._camera.IsOpen():
            return self._camera.Gain.Value
        return 0.0

    def set_exposure_time(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            self._camera.ExposureTime.Value = value

    def get_exposure_time(self) -> float:
        if self._camera and self._camera.IsOpen():
            return self._camera.ExposureTime.Value
        return 0.0

    def get_tick_frequency_hz(self) -> int | None:
        if not self._camera or not self._camera.IsOpen():
            return None
        for node in ["GevTimestampTickFrequency", "BslTimestampFrequency"]:
            try:
                return int(getattr(self._camera, node).Value)
            except Exception:
                pass
        return None

    def has_camera_time(self) -> bool:
        return self._has_chunk_ts

    def has_exp_end_time(self) -> bool:
        return self._has_exp_event

    def has_frame_counter(self) -> bool:
        return self._has_chunk_fc

    def get_fps(self) -> float | None:
        if not self._camera or not self._camera.IsOpen():
            return None
        for node in [
            "BslResultingAcquisitionFrameRate",
            "ResultingAcquisitionFrameRate",
            "AcquisitionFrameRate",
            "AcquisitionFrameRateAbs",
        ]:
            try:
                return float(getattr(self._camera, node).Value)
            except Exception:
                pass
        return None
