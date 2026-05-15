# view/dark_capture_window.py
# Rule: no logic here — only widget construction and layout math.
#
# Layout: two columns side by side so everything is visible without scrolling.
#   Left  — live preview (fixed 320×200 texture)
#   Right — all controls (frame count, buttons, progress, save path, status)

import dearpygui.dearpygui as dpg
import numpy as np

from config import DARK_PREVIEW_W, DARK_PREVIEW_H


class DarkCaptureWindow:

    # widget tags
    WINDOW        = "dark_cap_win"
    BTN_CAPTURE   = "dark_cap_btn_capture"
    BTN_CANCEL    = "dark_cap_btn_cancel"
    BTN_SAVE      = "dark_cap_btn_save"
    BTN_BROWSE    = "dark_cap_btn_browse"
    BTN_APPLY     = "dark_cap_btn_apply"
    INP_FRAMES    = "dark_cap_inp_frames"
    INP_PATH      = "dark_cap_inp_path"
    PROGRESS      = "dark_cap_progress"
    STATUS        = "dark_cap_status"
    PREVIEW_TEX   = "dark_cap_preview_tex"
    PREVIEW_LABEL = "dark_cap_preview_label"

    # right column width drives all control widths
    _RIGHT_W = 270

    def create(self, on_close) -> None:
        blank = np.zeros(DARK_PREVIEW_W * DARK_PREVIEW_H * 3, dtype="f")
        with dpg.texture_registry(show=False):
            dpg.add_raw_texture(
                width=DARK_PREVIEW_W, height=DARK_PREVIEW_H,
                tag=self.PREVIEW_TEX, default_value=blank,
                format=dpg.mvFormat_Float_rgb,
            )

        with dpg.window(
            tag=self.WINDOW,
            label="Dark Image Capture",
            width=700, height=480,
            show=False,
            no_resize=True,
            on_close=on_close,
        ):
            with dpg.group(horizontal=True):
                self._left_column()
                dpg.add_spacer(width=10)
                self._right_column()

    # two columns

    def _left_column(self) -> None:
        with dpg.group():
            dpg.add_text("Live Preview", tag=self.PREVIEW_LABEL)
            with dpg.drawlist(width=DARK_PREVIEW_W, height=DARK_PREVIEW_H):
                dpg.draw_image(
                    self.PREVIEW_TEX,
                    pmin=(0, 0), pmax=(DARK_PREVIEW_W, DARK_PREVIEW_H),
                )

    def _right_column(self) -> None:
        w = self._RIGHT_W
        with dpg.group():
            # frame count
            with dpg.group(horizontal=True):
                dpg.add_text("Frames to average:")
                dpg.add_input_int(
                    tag=self.INP_FRAMES,
                    default_value=500,
                    min_value=1, min_clamped=True,
                    width=110,
                )

            dpg.add_spacer(height=4)

            # capture / cancel
            with dpg.group(horizontal=True):
                dpg.add_button(label="Capture", tag=self.BTN_CAPTURE, width=100)
                dpg.add_button(label="Cancel",  tag=self.BTN_CANCEL,  width=100)

            dpg.add_spacer(height=4)

            # progress bar
            dpg.add_progress_bar(
                tag=self.PROGRESS,
                default_value=0.0,
                width=w,
                overlay="0 / 0",
            )

            dpg.add_separator()
            dpg.add_spacer(height=4)

            # save path — input stretches, Browse is fixed
            dpg.add_text("Save path")
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.INP_PATH,
                    default_value="./data/dark",
                    width=w - 65,
                )
                dpg.add_button(label="Browse", tag=self.BTN_BROWSE, width=60)

            dpg.add_spacer(height=4)

            # save / apply
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save to disk",    tag=self.BTN_SAVE,  width=130)
                dpg.add_button(label="Apply to camera", tag=self.BTN_APPLY, width=130)

            dpg.add_spacer(height=6)

            # status line
            dpg.add_text("", tag=self.STATUS)

    # show / hide

    def show(self, cam_id: str) -> None:
        dpg.configure_item(self.WINDOW, label=f"Dark Image Capture — {cam_id}", show=True)

    def hide(self) -> None:
        dpg.configure_item(self.WINDOW, show=False)

    # per-tick updates

    def update_preview(self, flat_rgb: np.ndarray) -> None:
        dpg.set_value(self.PREVIEW_TEX, flat_rgb)

    def set_progress(self, count: int, target: int) -> None:
        frac = count / target if target > 0 else 0.0
        dpg.set_value(self.PROGRESS, frac)
        dpg.configure_item(self.PROGRESS, overlay=f"{count} / {target}")

    def set_preview_label(self, text: str) -> None:
        dpg.set_value(self.PREVIEW_LABEL, text)

    def set_status(self, text: str) -> None:
        dpg.set_value(self.STATUS, text)

