import dearpygui.dearpygui as dpg
import cv2
import numpy as np
from view.ui import SCOS_UI
from model.testLiveCamera import testLiveCamera
from model.getTestHeat import getTestHeat


class SCOSController:

    def __init__(self, ui: SCOS_UI):
        self.ui = ui
        self._last_size = (0, 0)
        self.camera = testLiveCamera()  # create it directly for testing

    def setup_callbacks(self):
        dpg.set_item_callback(SCOS_UI.BTN_PREVIEW, self._on_preview)



    ## TESING FOR NOW:
    def _on_preview(self):
        # test the look heat bar:
        for y_axis_tag in self.ui.HEAT_Y_AXIS_TAG:
            dpg.delete_item(y_axis_tag, children_only=True)
        rows, cols = 20, 10
        for i, y_axis_tag in enumerate(self.ui.HEAT_Y_AXIS_TAG):
            data = getTestHeat(rows, cols)
            dpg.add_heat_series(
                x=data,
                rows=rows,
                cols=cols,
                parent=y_axis_tag,
                scale_min=0.0,
                scale_max=1.0,
                format=""
            )

        for y_axis_tag in self.ui.PLOT_Y_AXIS_TAG:
            dpg.delete_item(y_axis_tag, children_only=True)
        for i, y_axis_tag in enumerate(self.ui.PLOT_Y_AXIS_TAG):
            x = np.linspace(0, 20, 500).tolist()
            t = np.array(x)
            y = (3 * np.sin(t * 2) + 1.5 * np.sin(t * 5) + 0.3 * np.random.randn(500)).tolist()
            dpg.add_line_series(
                x=x,
                y=y,
                parent=y_axis_tag
    )


        self.camera.start()

        


    def update(self):
        frame = self.camera.get_frame()
        if frame is None:
            return
        frame = cv2.resize(frame, (320, 240))
        data = np.flip(frame, 2).ravel().astype("f") / 255.0
        dpg.set_value(SCOS_UI.LIVE_TEXTURE, data)



    def on_resize(self):
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) != self._last_size:
            self._last_size = (w, h)
            self.ui.resize(w, h)