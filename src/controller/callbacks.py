import dearpygui.dearpygui as dpg
from view.ui import SCOS_UI
import cv2 as cv
import numpy as np


class SCOSController:

    def __init__(self, ui: SCOS_UI):
        self.ui = ui
        self._last_size = (0, 0)

    def setup_callbacks(self):
        dpg.set_item_callback(SCOS_UI.BTN_PREVIEW, self._on_preview)


    def _on_preview(self):
        vid = cv.VideoCapture(0)
        while(True):
            ret, frame = vid.read()
            frame = cv.resize(frame, (230, 200))
            data = np.flip(frame,2)
            data = data.ravel()
            data = np.asanyarray(data, dtype='f')
            texture_data = np.true_divide(data, 255.0)

            dpg.set_value(self.ui.LIVE_TEXTURE, texture_data)



    def on_resize(self):
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) != self._last_size:
            self._last_size = (w, h)
            self.ui.resize(w, h)