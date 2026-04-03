# actual camera
from pypylon import pylon
from model.base_camera import BaseCamera
from config import CAMERA_PIXEL_FORMAT


class Camera(BaseCamera):
    def __init__(self, index= 0):
        self._camera = None
        self._index = index
        

    def open(self):
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if len(devices) == 0:
                raise RuntimeError("No camera found")
            
            self._camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[self._index]))
            
        except Exception:
            print("EnumerateDevices failed, trying CreateFirstDevice...")
            self._camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
        
        self._camera.Open()
        self._camera.PixelFormat.Value  = CAMERA_PIXEL_FORMAT
        self._camera.ExposureTime.Value = 20000
        self._camera.Gain.Value = 10
        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    
    def grab_frame(self):
        try:
            # if no frame arrives in 5 seconds = timeout
            grabResult = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

            if grabResult.GrabSucceeded():
                frame = grabResult.Array
                grabResult.Release()
                return frame
            grabResult.Release()
            return None
        except Exception as e:
            print(f"Camera grab frame got error: {e}")
            return None

    def close(self):
        try:
            self._camera.StopGrabbing()
            self._camera.Close()
        except Exception as e:
            print(f"Camera close error: {e}")

    # setter func
    def set_exposure_time(self, value: float):
        #Set exposure time
        if self._camera and self._camera.IsOpen():
            self._camera.ExposureTime.Value = value

    def set_gain(self, value: float):
        #Set gain value
        if self._camera and self._camera.IsOpen():
            self._camera.Gain.Value = value


    @classmethod
    def scan(cls):
        try:
            tl = pylon.TlFactory.GetInstance()
            devs = tl.EnumerateDevices()
            
            result = []
            for i, d in enumerate(devs):
                name = f"Basler [{i}] {d.GetModelName()}"
                result.append(name)
            
            return result

        except Exception as e:
            print(f"[Camera.scan] {e}")
            return []