import dearpygui.dearpygui as dpg
import numpy as np
from dataclasses import dataclass

# Theme values keep in sync with main.py
PADDING = 8
ITEM_SPACING = 6

TEXTURE_W, TEXTURE_H = 320, 240

HEAT_BARS = ["K²_raw", "K²_1", "K²_2", "K²_3", "K²_4", "K²_5"]
PLOT_LABELS = ["K²", "BFI", "CC", "OD"]

ROI_BTN_HEIGHT = 32
CAM_HEIGHT_RATIO = 0.28
DEVICE_WIDTH_RATIO = 0.58


# Layout dataclass to stores computed sizes for different panels in the UI
@dataclass
class Layout:
    left_col_w: int
    heat_panel_h: int
    heat_bar_w: int
    device_panel_w: int
    trigger_bar_h: int
    plot_h: int
    roi_image_h: int
    roi_image_w: int


# Main SCOS_UI class
class SCOS_UI:
    # Widget tags
    MAIN_WINDOW = "main_window"
    PANEL_LEFT = "panel_left"
    PANEL_HEAT = "panel_heat"
    PANEL_DEVICE = "panel_device"
    DEVICE_DROPDOWN = "dd_device"
    BTN_CONNECT = "btn_connect"
    INPUT_STUDY = "inp_study_name"
    BTN_CREATE = "btn_create_study"
    STUDY_DROPDOWN = "dd_current_study"
    INPUT_SUBJECT = "inp_subject"
    INPUT_RUN = "inp_run"
    RATE_SLIDER = "sld_rate"
    LIVE_TEXTURE = "tex_live"
    LIVE_IMAGE = "img_live"
    BTN_PREVIEW = "btn_preview"
    BTN_START = "btn_start"
    BTN_PAUSE = "btn_pause"
    BTN_STOP = "btn_stop"


    # Tags for heat bars and plots
    HEAT_BARS_TAG = ["k_raw", "k_1", "k_2", "k_3", "k_4", "k_5"]
    HEAT_Y_AXIS_TAG = ["k_raw/y", "k_1/y", "k_2/y", "k_3/y", "k_4/y", "k_5/y"]

    PLOT_SERIES_TAG = ["K2", "BFI", "CC", "OD"]
    PLOT_Y_AXIS_TAG = ["K2/y", "BFI/y", "CC/y", "OD/y"]

    ROI_BUTTONS = [
        ("Preview", BTN_PREVIEW),
        ("Start",   BTN_START),
        ("Pause",   BTN_PAUSE),
        ("Stop",    BTN_STOP),
    ]



    # Layout computation
    # Calculate positions and sizes of all UI elements dynamically
    def compute_layout(self, window_w, window_h) -> Layout:
        # Left column is half the window
        left_col_w = window_w // 2 - ITEM_SPACING
        left_col_inner_w = left_col_w - 2 * PADDING  # subtract left column's own border

        # Heat bar panel height is a fixed ratio of window height
        heat_panel_h = int(window_h * CAM_HEIGHT_RATIO)

        # Divide the inner width evenly across all heat bars (account for gaps between them)
        num_bars = len(HEAT_BARS)
        heat_bar_w = (left_col_inner_w - 2 * PADDING - (num_bars - 1) * ITEM_SPACING) // num_bars

        # Device panel takes a ratio of the left inner width; ROI panel gets the rest
        device_panel_w = int(left_col_inner_w * DEVICE_WIDTH_RATIO)

        # Right column: fixed trigger bar at top, remaining height split equally across plots
        trigger_bar_h = 42
        trigger_total_cost = trigger_bar_h + 2 * PADDING + 4  # border + spacer below
        num_plots = len(PLOT_LABELS)
        plot_h = max(110, (window_h - 2 * PADDING - trigger_total_cost
                           - (num_plots - 1) * ITEM_SPACING) // num_plots)

        # ROI image height = ROI panel height minus title/spacers overhead and button area
        roi_panel_h = (window_h - heat_panel_h - 2 * PADDING - ITEM_SPACING) - 2 * PADDING
        num_btns = len(self.ROI_BUTTONS)
        btn_area_h = num_btns * (ROI_BTN_HEIGHT + 8) + (num_btns - 1) * ITEM_SPACING
        roi_image_h = max(80, roi_panel_h - 60 - btn_area_h)

        roi_panel_w = left_col_inner_w - device_panel_w - ITEM_SPACING
        roi_image_w = roi_panel_w - 2 * PADDING

        return Layout(
            left_col_w=left_col_w,
            heat_panel_h=heat_panel_h,
            heat_bar_w=heat_bar_w,
            device_panel_w=device_panel_w,
            trigger_bar_h=trigger_bar_h,
            plot_h=plot_h,
            roi_image_h=roi_image_h,
            roi_image_w=roi_image_w,
        )


    # Build the window and attach left/right columns
    def create_ui(self, window_w=1280, window_h=720):
        layout = self.compute_layout(window_w, window_h)

        with dpg.window(tag=self.MAIN_WINDOW, no_title_bar=True, no_collapse=True):
            with dpg.group(horizontal=True):
                self._left_column(layout)
                self._right_column(layout)

    # Resize everything when window change the size
    def resize(self, window_w, window_h):
        layout = self.compute_layout(window_w, window_h)

        dpg.configure_item(self.PANEL_LEFT, width=layout.left_col_w)
        dpg.configure_item(self.PANEL_HEAT, height=layout.heat_panel_h)
        dpg.configure_item(self.PANEL_DEVICE, width=layout.device_panel_w)
        dpg.configure_item(self.LIVE_IMAGE, width=layout.roi_image_w, height=layout.roi_image_h)

        for bar in self.HEAT_BARS_TAG:
            dpg.configure_item(bar, width=layout.heat_bar_w)
        for plot in self.PLOT_SERIES_TAG:
            dpg.configure_item(plot, height=layout.plot_h)

    # LEFT COLUMN
    def _left_column(self, layout: Layout):
        with dpg.child_window(tag=self.PANEL_LEFT, width=layout.left_col_w,
                              height=-1, border=False, no_scrollbar=True):
            self._heat_panel(layout)
            dpg.add_spacer(height=ITEM_SPACING)
            with dpg.group(horizontal=True):
                self._device_study_panel(layout)
                self._roi_panel(layout)

    #HEAT PANEL
    def _heat_panel(self, layout: Layout):
        with dpg.child_window(tag=self.PANEL_HEAT, width=-1,
                              height=layout.heat_panel_h, border=True, no_scrollbar=True):
            dpg.add_text("K² Heat Map")
            with dpg.group(horizontal=True):
                for i, bar in enumerate(self.HEAT_BARS_TAG):
                    with dpg.plot(tag=bar, label=bar, width=layout.heat_bar_w, height=-1):
                        dpg.add_plot_axis(dpg.mvXAxis, no_tick_labels=True, no_gridlines=True)
                        dpg.add_plot_axis(dpg.mvYAxis, no_tick_labels=True, no_gridlines=True,
                                          tag=self.HEAT_Y_AXIS_TAG[i])

    # Device and Study panel
    def _device_study_panel(self, layout: Layout):
        with dpg.child_window(tag=self.PANEL_DEVICE, width=layout.device_panel_w,
                              height=-1, border=True, no_scrollbar=True):

            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(width_stretch=True)
                dpg.add_table_column(width_fixed=True, init_width_or_weight=75)

                with dpg.table_row():
                    dpg.add_text("Device")
                    dpg.add_combo([], tag=self.DEVICE_DROPDOWN, width=-1)
                    dpg.add_button(label="Connect", tag=self.BTN_CONNECT, width=-1)

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
                    dpg.add_slider_float(tag=self.RATE_SLIDER, min_value=5,
                                         max_value=20, format="%.1f Hz", width=-1)

    #ROI panel
    def _roi_panel(self, layout: Layout):
        with dpg.child_window(width=-1, height=-1, border=True, no_scrollbar=True):
            dpg.add_text("ROI Selection")

            with dpg.texture_registry(show=False):
                blank = np.zeros(TEXTURE_W * TEXTURE_H * 3, dtype="f")
                dpg.add_raw_texture(width=TEXTURE_W, height=TEXTURE_H, tag=self.LIVE_TEXTURE,
                                    default_value=blank, format=dpg.mvFormat_Float_rgb)

            dpg.add_image(self.LIVE_TEXTURE, width=layout.roi_image_w, height=layout.roi_image_h,
                          tag=self.LIVE_IMAGE)

            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, pad_outerX=True):
                dpg.add_table_column()
                for label, tag in self.ROI_BUTTONS:
                    with dpg.table_row():
                        dpg.add_button(label=label, tag=tag, width=-1, height=ROI_BTN_HEIGHT)

    #  RIGHT COLUMN
    def _right_column(self, layout: Layout):
        with dpg.child_window(width=-1, height=-1, border=False, no_scrollbar=True):
            self._trigger_bar(layout)
            self._plots_panel(layout)

    # Trigger Bar
    def _trigger_bar(self, layout: Layout):
        with dpg.child_window(width=-1, height=layout.trigger_bar_h, border=True, no_scrollbar=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Trigger source:")
                dpg.add_combo([], width=100)
                dpg.add_button(label="Connect")
                dpg.add_text("Time scale:")
                dpg.add_input_int(default_value=0, width=100)
                dpg.add_checkbox(label="Autoscale")

    # Plot panel
    def _plots_panel(self, layout: Layout):
        for i, plot in enumerate(self.PLOT_SERIES_TAG):
            with dpg.plot(tag=plot, label=plot, height=layout.plot_h, width=-1, no_mouse_pos=True):
                dpg.add_plot_axis(dpg.mvXAxis, label="s", no_gridlines=True)
                dpg.add_plot_axis(dpg.mvYAxis, label=plot, tag=self.PLOT_Y_AXIS_TAG[i], no_gridlines=True)