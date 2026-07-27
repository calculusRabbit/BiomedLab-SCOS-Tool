import numpy as np
from pypylon import pylon, genicam

from hardware.base_camera import BaseCamera
from config import CAMERA_PIXEL_FORMAT, CAMERA_DEFAULT_GAIN, CAMERA_DEFAULT_EXPOSURE


class Camera(BaseCamera):
    # Handles opening/closing the camera, configuring pixel format and exposure,
    # and grabbing frames with hardware timestamps and frame counters via chunk data.
    # Chunk data gives us per-frame metadata directly from the camera hardware,
    # which is more accurate than relying on PC timestamps alone.

    def __init__(self, serial: str):
        self._camera = None
        self._serial = serial
        self._model = ""
        self._has_chunk_ts: bool = False
        self._has_chunk_fc: bool = False
        self._chunk_fc_attr: str | None = None

    @classmethod
    def scan(cls) -> list[tuple[str, str]]:
        try:
            tl = pylon.TlFactory.GetInstance()
            devices = tl.EnumerateDevices()
            if not devices:
                print("[Camera.scan] no cameras found")
                return []
            result = []
            for d in devices:
                result.append((d.GetSerialNumber(), d.GetModelName()))
            return result
        except Exception as e:
            print(f"[Camera.scan] {e}")
            return []

    def open(self) -> None:
        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if not devices:
            raise RuntimeError("No Basler cameras found")
        device = next((d for d in devices if d.GetSerialNumber() == self._serial), None)
        if device is None:
            raise RuntimeError(f"Camera SN:{self._serial} not found — may have been disconnected")
        self._model = device.GetModelName()
        self._camera = pylon.InstantCamera(tl_factory.CreateDevice(device))
        self._camera.Open()
        self._camera.PixelFormat.Value = CAMERA_PIXEL_FORMAT
        self._camera.ExposureTime.Value = CAMERA_DEFAULT_EXPOSURE
        self._camera.Gain.Value = CAMERA_DEFAULT_GAIN
        self._camera.MaxNumBuffer.Value = 20
        self._setup_chunks()
        self._camera.StartGrabbing(pylon.GrabStrategy_OneByOne)

    def _setup_chunks(self) -> None:
        # chunk data embeds extra info (timestamp, frame counter, CRC) into each frame
        # not all camera models support all chunk types, so we try each and skip on failure
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

            # Frame counter — USB cameras use "FrameID", GigE use "Framecounter"
            for selector, attr in [("FrameID", "ChunkFrameID"), ("Framecounter", "ChunkFramecounter")]:
                try:
                    self._camera.ChunkSelector.Value = selector
                    self._camera.ChunkEnable.Value = True
                    self._has_chunk_fc = True
                    self._chunk_fc_attr = attr
                    break
                except Exception:
                    continue

            print(f"[Camera] chunks — timestamp={self._has_chunk_ts}, framecounter={self._has_chunk_fc} ({self._chunk_fc_attr})")

        except Exception as e:
            print(f"[Camera] chunk setup failed: {e}")

    def grab_frame(self) -> tuple[np.ndarray, int | None, int | None, int | None] | None:
        try:
            grab = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

            if not grab.GrabSucceeded():
                print(f"[Camera.grab_frame] grab failed: {grab.ErrorDescription}")
                grab.Release()
                return None

            if grab.HasCRC() and not grab.CheckCRC():
                print("[Camera.grab_frame] CRC mismatch — frame discarded")
                grab.Release()
                return None

            frame = grab.Array.copy()

            cam_ts = None
            if self._has_chunk_ts and genicam.IsReadable(grab.ChunkTimestamp):
                cam_ts = grab.ChunkTimestamp.Value

            frame_counter = None
            if self._has_chunk_fc and self._chunk_fc_attr:
                node = getattr(grab, self._chunk_fc_attr)
                if genicam.IsReadable(node):
                    frame_counter = node.Value

            grab.Release()
            return frame, cam_ts, frame_counter, None

        except Exception as e:
            print(f"[Camera.grab_frame] {e}")
            return None

    def close(self) -> None:
        try:
            if self._camera and self._camera.IsOpen():
                if genicam.IsWritable(self._camera.ChunkModeActive):
                    self._camera.ChunkModeActive.Value = False
                self._camera.StopGrabbing()
                self._camera.Close()
        except Exception as e:
            print(f"[Camera.close] {e}")

    def get_serial(self) -> str:
        return self._serial

    def get_model(self) -> str:
        return self._model

    def set_gain(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            # clamp so a typed-in out-of-range value can't raise a GenICam error
            lo, hi = self.get_gain_range()
            self._camera.Gain.Value = min(max(value, lo), hi)

    def get_gain(self) -> float:
        if self._camera and self._camera.IsOpen():
            return self._camera.Gain.Value
        return 0.0

    def set_exposure_time(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            lo, hi = self.get_exposure_range()
            self._camera.ExposureTime.Value = min(max(value, lo), hi)

    def get_exposure_time(self) -> float:
        if self._camera and self._camera.IsOpen():
            return self._camera.ExposureTime.Value
        return 0.0

    def get_gain_range(self) -> tuple[float, float]:
        try:
            if self._camera and self._camera.IsOpen() and self._camera.Gain.IsReadable():
                return float(self._camera.Gain.Min), float(self._camera.Gain.Max)
        except Exception as e:
            print(f"[Camera.get_gain_range] {e}")
        return super().get_gain_range()

    def get_exposure_range(self) -> tuple[float, float]:
        try:
            if self._camera and self._camera.IsOpen() and self._camera.ExposureTime.IsReadable():
                return float(self._camera.ExposureTime.Min), float(self._camera.ExposureTime.Max)
        except Exception as e:
            print(f"[Camera.get_exposure_range] {e}")
        return super().get_exposure_range()

    def get_tick_frequency_hz(self) -> int | None:
        if not self._camera or not self._camera.IsOpen():
            return None
        return int(1e9)

    def has_camera_time(self) -> bool:
        return self._has_chunk_ts

    def has_frame_counter(self) -> bool:
        return self._has_chunk_fc

    def get_fps(self) -> float | None:
        if not self._camera or not self._camera.IsOpen():
            return None
        try:
            return float(self._camera.BslResultingAcquisitionFrameRate.Value)
        except Exception:
            return None














# ─────────────────────────────────────────────────────────────────────────────
# GigE / ExposureEnd event support (not available on USB cameras)
# from collections import deque
#
# class _ExposureEndHandler(pylon.CameraEventHandler):
#     def __init__(self):
#         super().__init__()
#         self._ts_queue: deque[int] = deque(maxlen=50)
#
#     def OnCameraEvent(self, camera, user_id, node):
#         try:
#             if genicam.IsReadable(camera.EventExposureEndTimestamp):
#                 self._ts_queue.append(camera.EventExposureEndTimestamp.Value)
#         except Exception:
#             pass
#
# In __init__:
#     self._has_exp_event: bool = False
#     self._exp_handler: _ExposureEndHandler | None = None
#
# In open(), after _setup_chunks():
#     self._setup_exposure_event()
#
# def _setup_exposure_event(self) -> None:
#     try:
#         if not genicam.IsAvailable(self._camera.EventSelector):
#             return
#         if not genicam.IsWritable(self._camera.GrabCameraEvents):
#             print("[Camera] GrabCameraEvents not writable — events unavailable on this camera")
#             return
#         self._camera.GrabCameraEvents.Value = True
#         self._camera.EventSelector.Value = "ExposureEnd"
#         self._camera.EventNotification.Value = "On"
#         self._exp_handler = _ExposureEndHandler()
#         self._camera.RegisterCameraEventHandler(
#             self._exp_handler, "EventExposureEndData", 0,
#             pylon.RegistrationMode_ReplaceAll, pylon.Cleanup_None,
#         )
#         self._has_exp_event = True
#         print("[Camera] exposure end event enabled")
#     except Exception as e:
#         print(f"[Camera] exposure end event setup failed: {e}")
#
# In grab_frame(), after frame_counter:
#     exp_end_ts = None
#     if self._has_exp_event and self._exp_handler._ts_queue:
#         exp_end_ts = self._exp_handler._ts_queue.popleft()
#     return frame, cam_ts, frame_counter, exp_end_ts
#
# In close(), before StopGrabbing:
#     if self._has_exp_event:
#         self._camera.EventSelector.Value = "ExposureEnd"
#         self._camera.EventNotification.Value = "Off"
#
# In has_exp_end_time():
#     return self._has_exp_event
# ─────────────────────────────────────────────────────────────────────────────
