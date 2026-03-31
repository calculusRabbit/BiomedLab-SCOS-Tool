import time
from collections import deque

import cv2
import dearpygui.dearpygui as dpg
import numpy as np

from config import MAX_PLOT_POINTS, PLOT_WINDOW_SEC, TEXTURE_W, TEXTURE_H
from model.pipeline import Pipeline
from view.ui import SCOS_UI
from controller.roi_selector import ROISelector


class SCOSController:

    def __init__(self, ui: SCOS_UI, pipeline: Pipeline):
        self.ui = ui
        self.pipeline = pipeline
        self._start_time = 0.0

        self._t_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._k2_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._bfi_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._cc_buf = deque(maxlen=MAX_PLOT_POINTS)
        self._od_buf = deque(maxlen=MAX_PLOT_POINTS)

        self._last_size = (0, 0)

        self._recording = False


    # set up call back 
    def setup_callbacks(self):
        self._roi = ROISelector(
            drawlist_tag = self.ui.ROI_DRAWLIST,
            display_w = dpg.get_item_width(self.ui.ROI_DRAWLIST),
            display_h = dpg.get_item_height(self.ui.ROI_DRAWLIST),
        )
        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_item_callback(self.ui.BTN_PREVIEW, self._on_preview)
        dpg.set_item_callback(self.ui.BTN_STOP, self._on_stop)
        dpg.set_item_callback(self.ui.BTN_AUTOSCALE, self._on_autoscale)
        dpg.set_item_callback(self.ui.BTN_SCAN, self._on_scan)
        self._roi.setup_handlers()

        
    # execute when close the whole app
    def shutdown(self):
        self.pipeline.stop()


    # main loop hook, keep updating for graph
    def update(self) -> None:
        result = self.pipeline.get_latest()
        if result is not None:
            full_frame, output = result
            self._push_frame(full_frame)   # always full frame
            self._push_plots(output)


    ## CallBack
    def _on_preview(self):
        self._start_time = time.time()
        self._recording = True  
        self.pipeline.set_roi_source(self._roi.get_roi)
        self.pipeline.start()

    def _on_start(self):
        pass

    def _on_pause(self):
        pass

    def _on_stop(self) -> None:
        self.pipeline.stop()
        self._recording = False


    def _on_scan(self):
        pass

    def _on_autoscale(self):
        for tag in self.ui.GRAPH_TAG:
            y_tag = dpg.get_item_children(tag, 1)[1]
            dpg.fit_axis_data(y_tag)

    ## UI updates
    def _push_frame(self, frame): # takes frame directly now
        h, w = frame.shape[:2]
        if h != TEXTURE_H or w != TEXTURE_W:
            frame = cv2.resize(frame, (TEXTURE_W, TEXTURE_H))
        norm = frame.astype(np.float32) / 255.0
        rgb  = np.stack([norm, norm, norm], axis=-1)
        dpg.set_value(self.ui.LIVE_TEXTURE, rgb.flatten())

    def _push_plots(self, output):
        t = time.time() - self._start_time
        self._t_buf.append(t)
        self._k2_buf.append(output.k2)
        self._bfi_buf.append(output.bfi)
        self._cc_buf.append(output.cc)
        self._od_buf.append(output.od)

        times = list(self._t_buf)
        for i, buf in enumerate([self._k2_buf, self._bfi_buf, self._cc_buf, self._od_buf]):
            dpg.set_value(self.ui.PLOT_SERIES_TAG[i], [times, list(buf)])

        if times:
            x_max = max(PLOT_WINDOW_SEC, times[-1]) + 0.5
            x_min = x_max - PLOT_WINDOW_SEC
            for x_tag in self.ui.GRAPH_X_TAG:
                if self._recording:
                    dpg.set_axis_limits(x_tag, x_min, x_max)


    def _push_K2_bars(self):
        pass


    def _clear_buffers(self):
        for buf in (self._t_buf, self._k2_buf, self._bfi_buf, self._cc_buf, self._od_buf):
            buf.clear()


    # resize(rescale) all UI(button, graph, space...)
    def _on_resize(self):
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) != self._last_size and w > 0 and h > 0:
            self._last_size = (w, h)
            self.ui.resize(w, h)
            self._roi.update_display_size(
                dpg.get_item_width(self.ui.ROI_DRAWLIST),
                dpg.get_item_height(self.ui.ROI_DRAWLIST),
            )