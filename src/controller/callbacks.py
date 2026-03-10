# Controller — glue between model (camera + processor) and view (UI).

import threading
import time
from collections import deque
import queue

import dearpygui.dearpygui as dpg
import numpy as np

from view.ui import SCOS_UI, TEXTURE_W, TEXTURE_H
from model.scos_result import SCOSResult
from model.processor import process_all_data


class SCOSController:

    def __init__(self, ui: SCOS_UI, camera):
        self.ui = ui
        self.camera = camera

        # threading
        self._running = False
        self._thread = None
        self._queue = queue.Queue(maxsize=1)

        self._timestamp = 0.0

        # plot history buffers
        self._max_points = 500
        self._time_buf = deque(maxlen=self._max_points)
        self._k2_buf  = deque(maxlen=self._max_points)
        self._bfi_buf = deque(maxlen=self._max_points)
        self._cc_buf  = deque(maxlen=self._max_points)
        self._od_buf  = deque(maxlen=self._max_points)

        # resize tracking
        self._last_size = (0, 0)



    def setup_callbacks(self):
        dpg.set_item_callback(self.ui.BTN_PREVIEW, self._on_preview)
        dpg.set_item_callback(self.ui.BTN_STOP, self._on_stop)
        dpg.set_item_callback(self.ui.INPUT_AUTOSCALE, self._on_autoFit)


    def update_UI(self):
        self._handle_resize()
        self._drain_queue()


    # button callbacks
    def _on_autoFit(self):
        # auto fit y axis
        for plot_tag in self.ui.GRAPH_TAG:
            dpg.fit_axis_data(dpg.get_item_children(plot_tag, 1)[1])  # y-axis is second child


    def _on_preview(self):
        self._start_acquisition()


    def _on_stop(self):
        self._stop_acquisition()
        self._clear_buffers()


    # acquisition (start / stop / worker thread)
    def _start_acquisition(self):
        if self._running:
            return
        self.camera.open()
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()


    def _stop_acquisition(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.camera.close()


    def _worker(self):
        start = time.time()
        while self._running:
            frame = self.camera.grab_frame()
            if frame is None:
                continue

            self.timestamp = time.time() - start
            result = process_all_data(frame)

            try:
                self._queue.put_nowait(result)
            except queue.Full:
                pass


    # UI updates (main thread only)

    def _drain_queue(self):
        try:
            result = self._queue.get_nowait()
        except queue.Empty:
            return
        self._update_frame(result)
        self._update_plots(result)


    def _update_frame(self, result: SCOSResult):
        frame = result.frame
        h, w = frame.shape[:2]

        if h != TEXTURE_H or w != TEXTURE_W:
            import cv2
            frame = cv2.resize(frame, (TEXTURE_W, TEXTURE_H))

        norm = frame.astype(np.float32) / 255.0
        rgb = np.stack([norm, norm, norm], axis=-1).flatten()
        dpg.set_value(self.ui.LIVE_TEXTURE, rgb)


    def _update_plots(self, result: SCOSResult):
        self._time_buf.append(self.timestamp)
        self._k2_buf.append(result.k2)
        self._bfi_buf.append(result.bfi)
        self._cc_buf.append(result.cc)
        self._od_buf.append(result.od)

        t = list(self._time_buf)
        bufs = [self._k2_buf, self._bfi_buf, self._cc_buf, self._od_buf]

        for i, buf in enumerate(bufs):
            dpg.set_value(self.ui.PLOT_SERIES_TAG[i], [t, list(buf)])

        if t:
            window = 10.0
            x_max = max(window, t[-1]) + 0.5
            x_min = x_max - window
            for x_tag in self.ui.GRAPH_X_TAG:
                dpg.set_axis_limits(x_tag, x_min, x_max)


    def _clear_buffers(self):
        self._time_buf.clear()
        self._k2_buf.clear()
        self._bfi_buf.clear()
        self._cc_buf.clear()
        self._od_buf.clear()


    # resize

    def _handle_resize(self):
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) != self._last_size and w > 0 and h > 0:
            self._last_size = (w, h)
            self.ui.resize(w, h)