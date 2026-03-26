# actual camera

import cv2
from pypylon import pylon
import numpy as np
from model.base_camera import BaseCamera


class Camera(BaseCamera):
    def __init__(self, device_num: int = 0):
        self._camera = None
        self._device_index = device_num
        

    def open(self):
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if len(devices) == 0:
                raise RuntimeError("No camera found")
            self._camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[self._device_index]))

        except Exception:
            print("EnumerateDevices failed, trying CreateFirstDevice...")
            self._camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
        
        self._camera.Open()
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