# view/ui.py
# Rule: no logic here — only widget construction and layout math.

from dataclasses import dataclass

import dearpygui.dearpygui as dpg
import numpy as np

from config import (
    PADDING, ITEM_SPACING,
    TEXTURE_W, TEXTURE_H,
    CAM_HEIGHT_RATIO, DEVICE_WIDTH_RATIO, ROI_BTN_HEIGHT,
)


@dataclass
class _Layout:
    left_col_w: int
    k2_map_panel_h: int
    k2_map_bar_w: int
    device_panel_w: int
    trigger_bar_h: int
    plot_h: int
    roi_image_h: int
    roi_image_w: int


class SCOS_UI:

    # 
    MAIN_WINDOW = "main_window"
    PANEL_LEFT = "panel_left"
    PANEL_K2_MAP = "panel_k2_map"
    PANEL_DEVICE = "panel_device"
    DEVICE_DROPDOWN = "dd_device"
    BTN_SCAN = "btn_scan"
    BTN_CONNECT = "btn_connect"
    INPUT_STUDY = "inp_study"
    BTN_CREATE = "btn_create"
    STUDY_DROPDOWN = "dd_study"
    INPUT_SUBJECT = "inp_subject"
    INPUT_RUN = "inp_run"
    RATE_SLIDER = "sld_rate"
    LIVE_TEXTURE = "tex_live"
    LIVE_IMAGE = "img_live"
    BTN_PREVIEW = "btn_preview"
    BTN_START = "btn_start"
    BTN_PAUSE = "btn_pause"
    BTN_STOP = "btn_stop"
    BTN_AUTOSCALE = "btn_fit_y"


    K2_MAP_TAG = ["k2_raw", "k2_1", "k2_2", "k2_3", "k2_4", "k2_5"]
    K2_Y_AXIS_TAG = ["k2_raw/y", "k2_1/y", "k2_2/y", "k2_3/y", "k2_4/y", "k2_5/y"]

    # Right-side time series plots
    GRAPH_TAG = ["K2", "BFI", "CC", "OD"]
    GRAPH_X_TAG = ["K2_x", "BFI_x", "CC_x", "OD_x"]
    PLOT_SERIES_TAG = ["K2_s", "BFI_s", "CC_s", "OD_s"]

    _ROI_BUTTONS = [
        ("Preview", BTN_PREVIEW),
        ("Start", BTN_START),
        ("Pause", BTN_PAUSE),
        ("Stop", BTN_STOP),
    ]

    ROI_DRAWLIST = "roi_drawlist"

    # layout math

    def _compute_layout(self, win_w: int, win_h: int) -> _Layout:
        left_col_w = win_w // 2 - ITEM_SPACING
        inner_w = left_col_w - 2 * PADDING
        k2_map_panel_h = int(win_h * CAM_HEIGHT_RATIO)
        n_k2_maps = len(self.K2_MAP_TAG)
        k2_map_bar_w = (inner_w - 2 * PADDING - (n_k2_maps - 1) * ITEM_SPACING) // n_k2_maps
        device_panel_w = int(inner_w * DEVICE_WIDTH_RATIO)
        trigger_bar_h = 42
        n_plots = len(self.GRAPH_TAG)
        plot_h = max(110, (win_h - 2 * PADDING - trigger_bar_h - 2 * PADDING - 4
                                    - (n_plots - 1) * ITEM_SPACING) // n_plots)
        roi_panel_h = win_h - k2_map_panel_h - 2 * PADDING - ITEM_SPACING - 2 * PADDING
        n_btns = len(self._ROI_BUTTONS)
        btn_area_h = n_btns * (ROI_BTN_HEIGHT + 8) + (n_btns - 1) * ITEM_SPACING
        roi_image_h = max(80, roi_panel_h - 60 - btn_area_h)
        roi_image_w = inner_w - device_panel_w - ITEM_SPACING - 2 * PADDING

        return _Layout(
            left_col_w = left_col_w,
            k2_map_panel_h = k2_map_panel_h,
            k2_map_bar_w = k2_map_bar_w,
            device_panel_w = device_panel_w,
            trigger_bar_h = trigger_bar_h,
            plot_h = plot_h,
            roi_image_h = roi_image_h,
            roi_image_w = roi_image_w,
        )

    # public

    def create_ui(self, win_w: int = 1280, win_h: int = 720) -> None:
        layout = self._compute_layout(win_w, win_h)
        with dpg.window(tag=self.MAIN_WINDOW, no_title_bar=True, no_collapse=True):
            with dpg.group(horizontal=True):
                self._left_column(layout)
                self._right_column(layout)

    def resize(self, win_w: int, win_h: int) -> None:
        lo = self._compute_layout(win_w, win_h)
        dpg.configure_item(self.PANEL_LEFT,   width=lo.left_col_w)
        dpg.configure_item(self.PANEL_K2_MAP, height=lo.k2_map_panel_h)
        dpg.configure_item(self.PANEL_DEVICE, width=lo.device_panel_w)
        dpg.configure_item(self.ROI_DRAWLIST, width=lo.roi_image_w, height=lo.roi_image_h)
        dpg.configure_item(self.LIVE_IMAGE,   pmax=(lo.roi_image_w, lo.roi_image_h))
        for tag in self.K2_MAP_TAG:
            dpg.configure_item(tag, width=lo.k2_map_bar_w)
        for tag in self.GRAPH_TAG:
            dpg.configure_item(tag, height=lo.plot_h)


    ## LEFT COLUMN
    def _left_column(self, lo: _Layout) -> None:
        with dpg.child_window(tag=self.PANEL_LEFT, width=lo.left_col_w,
                               height=-1, border=False, no_scrollbar=True):
            self._k2_map_panel(lo)
            dpg.add_spacer(height=ITEM_SPACING)
            with dpg.group(horizontal=True):
                self._device_panel(lo)
                self._roi_panel(lo)

    def _k2_map_panel(self, lo: _Layout) -> None:
        with dpg.child_window(tag=self.PANEL_K2_MAP, width=-1,
                               height=lo.k2_map_panel_h, border=True, no_scrollbar=True):
            dpg.add_text("K^2 Spatial Map")
            with dpg.group(horizontal=True):
                for i, tag in enumerate(self.K2_MAP_TAG):
                    with dpg.plot(tag=tag, label=tag, width=lo.k2_map_bar_w, height=-1):
                        dpg.add_plot_axis(dpg.mvXAxis, no_tick_labels=True, no_gridlines=True)
                        dpg.add_plot_axis(dpg.mvYAxis, no_tick_labels=True, no_gridlines=True,
                                          tag=self.K2_Y_AXIS_TAG[i])
                    dpg.bind_colormap(tag, dpg.mvPlotColormap_Jet)

    # ROI rectangle


    def _device_panel(self, lo: _Layout) -> None:
        with dpg.child_window(tag=self.PANEL_DEVICE, width=lo.device_panel_w,
                               height=-1, border=True, no_scrollbar=True):
            
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=55)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=65)

                with dpg.table_row():
                    dpg.add_text("Device")
                    dpg.add_combo([], tag=self.DEVICE_DROPDOWN, width=-1)
                    dpg.add_button(label="Scan", tag=self.BTN_SCAN, width=-1)
                    dpg.add_button(label="Connect", tag=self.BTN_CONNECT, width=-1)

            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=75)
                with dpg.table_row():
                    dpg.add_text("Study Name")
                    dpg.add_input_text(tag=self.INPUT_STUDY, width=-1)
                    dpg.add_button(label="Create", tag=self.BTN_CREATE, width=-1)

            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(width_stretch=True)
                with dpg.table_row():
                    dpg.add_text("Current Study")
                    dpg.add_combo([], tag=self.STUDY_DROPDOWN, width=-1,
                                  height_mode=dpg.mvComboHeight_Largest)
                with dpg.table_row():
                    dpg.add_text("Subject ID")
                    dpg.add_input_text(tag=self.INPUT_SUBJECT, width=-1)
                with dpg.table_row():
                    dpg.add_text("Run Number")
                    dpg.add_input_text(tag=self.INPUT_RUN, width=-1)
                with dpg.table_row():
                    dpg.add_text("Sampling Rate")
                    dpg.add_slider_int(tag=self.RATE_SLIDER, min_value=10, max_value=100, default_value=30,
                                       format="%d Hz", width=-1)

    def _roi_panel(self, lo: _Layout) -> None:
        with dpg.child_window(width=-1, height=-1, border=True, no_scrollbar=True):
            dpg.add_text("ROI Selection")
            with dpg.texture_registry(show=False):
                blank = np.zeros(TEXTURE_W * TEXTURE_H * 3, dtype="f")
                dpg.add_raw_texture(width=TEXTURE_W, height=TEXTURE_H, tag=self.LIVE_TEXTURE,
                                    default_value=blank, format=dpg.mvFormat_Float_rgb)
            # drawlist = canvas, draw image first then ROI rectangle on top
            with dpg.drawlist(tag=self.ROI_DRAWLIST,
                            width=lo.roi_image_w, height=lo.roi_image_h):
                dpg.draw_image(self.LIVE_TEXTURE,
                            pmin=(0, 0),
                            pmax=(lo.roi_image_w, lo.roi_image_h),
                            tag=self.LIVE_IMAGE)
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column()
                for label, tag in self._ROI_BUTTONS:
                    with dpg.table_row():
                        dpg.add_button(label=label, tag=tag, width=-1, height=ROI_BTN_HEIGHT)

                        
    # right column
    def _right_column(self, lo: _Layout) -> None:
        with dpg.child_window(width=-1, height=-1, border=False, no_scrollbar=True):
            self._trigger_bar(lo)
            self._plots_panel(lo)


    def _trigger_bar(self, lo: _Layout) -> None:
        with dpg.child_window(width=-1, height=lo.trigger_bar_h, border=True, no_scrollbar=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Trigger source:")
                dpg.add_combo([], width=100)
                dpg.add_button(label="Connect")
                dpg.add_text("Time scale:")
                dpg.add_input_int(default_value=0, width=100)
                dpg.add_button(label="Auto Scale (Fit Y)", tag=self.BTN_AUTOSCALE)

    def _plots_panel(self, lo: _Layout) -> None:
        labels = ["K²", "BFI", "CC", "OD"]
        for i, label in enumerate(labels):
            with dpg.plot(tag=self.GRAPH_TAG[i], label=label,
                          height=lo.plot_h, width=-1, no_mouse_pos=True):
                dpg.add_plot_axis(dpg.mvXAxis, label="time (s)",
                                  no_gridlines=True, tag=self.GRAPH_X_TAG[i])
                y = dpg.add_plot_axis(dpg.mvYAxis, label=label, no_gridlines=True)
                dpg.add_line_series([], [], parent=y, tag=self.PLOT_SERIES_TAG[i])