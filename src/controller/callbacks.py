import threading
import queue
import dearpygui.dearpygui as dpg
import numpy as np

from view.ui import SCOS_UI, TEXTURE_W, TEXTURE_H
from model.testModel import TestModel


class SCOSController:

    def __init__(self, ui: SCOS_UI):
        self.ui    = ui
        self.model = TestModel(width=TEXTURE_W, height=TEXTURE_H)

        self._running = False
        self._thread = None
        self._result_queue = queue.Queue(maxsize=1)
        self._last_size = (0, 0)

        # plot buffers
        self._max_points = 500
        self._start_time = None
        self._plot_x     = []
        self._plot_y     = {"K2": [], "BFI": [], "CC": [], "OD": []}

        # track if series have been created yet
        self._plots_initialized = False
        self._heat_bars_initialized = False


    # Callback setup
    def setup_callbacks(self):
        dpg.set_item_callback(self.ui.BTN_PREVIEW, self._on_preview)

    
    # Button callbacks 
    def _on_preview(self):
        if self._running == True:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()


    # Worker thread 
    def _worker(self):
        self.model.start()
        while self._running:
            result = self.model.get_result()
            if result is None:
                continue
            try:
                self._result_queue.put_nowait(result)
            except queue.Full:
                pass

    # Main thread update 
    def update(self):
        try:
            result = self._result_queue.get_nowait()
            self._update_camera(result)
            self._update_heat_bars(result)
            #self._update_plots(result)
        except queue.Empty:
            pass


    def _update_camera(self, result):
        if result.frame is not None:
            dpg.set_value(self.ui.LIVE_TEXTURE, result.frame)


    def _update_heat_bars(self, result):
        # check output from backend
        if result.heat_maps is None:
            return

        # update 6 of heat bar on top left panel
        for i, heat_map in enumerate(result.heat_maps):
            heat_map = np.array(heat_map)
            data = heat_map.flatten().tolist()
            if not dpg.does_item_exist(self.ui.HEAT_SERIES_TAG[i]):
                rows, cols = heat_map.shape
                dpg.add_heat_series(x=data, rows=rows, cols=cols, format="", 
                                    parent=self.ui.HEAT_Y_AXIS_TAG[i], tag=self.ui.HEAT_SERIES_TAG[i])
            else:
                dpg.set_value(self.ui.HEAT_SERIES_TAG[i], [data])



    def _update_plots(self, result):
        if self._start_time is None:
            self._start_time = result.time

        t = result.time - self._start_time

        self._plot_x.append(t)
        self._plot_y["K2"].append(result.k2)
        self._plot_y["BFI"].append(result.bfi)
        self._plot_y["CC"].append(result.cc)
        self._plot_y["OD"].append(result.od)

        # rolling window
        if len(self._plot_x) > self._max_points:
            self._plot_x = self._plot_x[-self._max_points:]
            for key in self._plot_y:
                self._plot_y[key] = self._plot_y[key][-self._max_points:]

        if not self._plots_initialized:
            # create series once on first frame
            for tag, y_axis_tag in zip(SCOS_UI.PLOT_SERIES_TAG, SCOS_UI.PLOT_Y_AXIS_TAG):
                dpg.add_line_series(
                    x      = self._plot_x,
                    y      = self._plot_y[tag],
                    label  = tag,
                    parent = y_axis_tag,
                    tag    = tag + "_series"
                )
            self._plots_initialized = True
            return

        # already created — just update data
        for tag in SCOS_UI.PLOT_SERIES_TAG:
            dpg.set_value(tag + "_series", [self._plot_x, self._plot_y[tag]])





    # resize
    def on_resize(self):
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) != self._last_size:
            self._last_size = (w, h)
            self.ui.resize(w, h)