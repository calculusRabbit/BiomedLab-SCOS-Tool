from pypylon import pylon

from hardware.base_camera import BaseCamera
from config import CAMERA_PIXEL_FORMAT


class Camera(BaseCamera):

    def __init__(self, index: int = 0):
        self._camera = None
        self._index = index

    @classmethod
    def scan(cls) -> list[str]:
        try:
            tl = pylon.TlFactory.GetInstance()
            devices = tl.EnumerateDevices()
            return [f"Basler [{i}] {d.GetModelName()}" for i, d in enumerate(devices)]
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
            print("EnumerateDevices failed, trying CreateFirstDevice...")
            self._camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())

        self._camera.Open()
        self._camera.PixelFormat.Value = CAMERA_PIXEL_FORMAT
        self._camera.ExposureTime.Value = 20000
        self._camera.Gain.Value = 10
        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    def grab_frame(self):
        try:
            grab = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                frame = grab.Array
                grab.Release()
                return frame
            grab.Release()
            return None
        except Exception as e:
            print(f"[Camera.grab_frame] {e}")
            return None

    def close(self) -> None:
        try:
            self._camera.StopGrabbing()
            self._camera.Close()
        except Exception as e:
            print(f"[Camera.close] {e}")

    def set_gain(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            self._camera.Gain.Value = value

    def set_exposure_time(self, value: float) -> None:
        if self._camera and self._camera.IsOpen():
            self._camera.ExposureTime.Value = value
