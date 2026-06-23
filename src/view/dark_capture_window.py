import dearpygui.dearpygui as dpg
import numpy as np

from config import DARK_THUMB_W, DARK_THUMB_H
from processing.utils import safe_filename


def _tex(cam_id: str) -> str:    return f"dk_tex_{safe_filename(cam_id)}"
def _label(cam_id: str) -> str:  return f"dk_lbl_{safe_filename(cam_id)}"
def _status(cam_id: str) -> str: return f"dk_stat_{safe_filename(cam_id)}"
def _row(cam_id: str) -> str:    return f"dk_row_{safe_filename(cam_id)}"


class DarkCaptureWindow:
    # """Builds and manages the dark image capture popup window.

    # Layout is two columns: left side shows a live preview thumbnail per camera,
    # right side has the controls (frame count, capture button, save path, apply).
    # Camera rows are created dynamically when the window opens and destroyed on close
    # so multiple scans with different camera counts work correctly.

    # widget tags
    WINDOW = "dark_cap_win"
    SCROLL_AREA = "dark_cap_scroll"
    TEX_REG = "dark_cap_tex_reg"
    INP_FRAMES  = "dark_cap_inp_frames"
    BTN_CAPTURE = "dark_cap_btn_capture"
    BTN_CANCEL = "dark_cap_btn_cancel"
    PROGRESS = "dark_cap_progress"
    INP_PATH = "dark_cap_inp_path"
    BTN_BROWSE  = "dark_cap_btn_browse"
    BTN_SAVE = "dark_cap_btn_save"
    BTN_APPLY = "dark_cap_btn_apply"
    STATUS = "dark_cap_status"

    _LEFT_W  = 360   # thumbnail (330) + padding
    _RIGHT_W = 360

    def __init__(self):
        self._built_cam_ids: list[str] = []

    def create(self, on_close) -> None:
        dpg.add_texture_registry(tag=self.TEX_REG, show=False)

        with dpg.window(
            tag=self.WINDOW,
            label="Dark Image Capture",
            width=770, height=520,
            show=False,
            no_resize=True,
            on_close=on_close,
        ):
            with dpg.group(horizontal=True):
                self._left_column()
                dpg.add_spacer(width=10)
                self._right_column()

    # two-column layout

    def _left_column(self) -> None:
        with dpg.child_window(
            tag=self.SCROLL_AREA,
            width=self._LEFT_W,
            height=-1,
            border=False,
        ):
            pass  # camera rows added dynamically in show()

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

            dpg.add_spacer(height=5)

            # capture / cancel
            with dpg.group(horizontal=True):
                dpg.add_button(label="Capture", tag=self.BTN_CAPTURE, width=100)
                dpg.add_button(label="Cancel",  tag=self.BTN_CANCEL,  width=100)

            dpg.add_spacer(height=5)

            # progress bar
            dpg.add_progress_bar(
                tag=self.PROGRESS,
                default_value=0.0,
                width=w,
                overlay="0 / 0",
            )

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # save path
            dpg.add_text("Save path")
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.INP_PATH,
                    default_value="./data/dark",
                    width=w - 65,
                )
                dpg.add_button(label="Browse", tag=self.BTN_BROWSE, width=60)

            dpg.add_spacer(height=5)

            # save / apply
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save to disk",      tag=self.BTN_SAVE,  width=175)
                dpg.add_button(label="Apply to cameras",  tag=self.BTN_APPLY, width=175)

            dpg.add_spacer(height=5)
            dpg.add_text("", tag=self.STATUS)

    # show / hide

    def show(self, cam_ids: list[str]) -> None:
        self._build_rows(cam_ids)
        dpg.set_value(self.STATUS, "Block all light sources, then click Capture.")
        dpg.configure_item(self.WINDOW, show=True)

    def hide(self) -> None:
        dpg.configure_item(self.WINDOW, show=False)
        self._destroy_rows()

    # per-camera rows

    def _build_rows(self, cam_ids: list[str]) -> None:
        self._destroy_rows()
        self._built_cam_ids = list(cam_ids)
        blank = np.zeros(DARK_THUMB_W * DARK_THUMB_H * 3, dtype="f")
        for cam_id in cam_ids:
            dpg.add_raw_texture(
                width=DARK_THUMB_W, height=DARK_THUMB_H,
                tag=_tex(cam_id), default_value=blank,
                format=dpg.mvFormat_Float_rgb,
                parent=self.TEX_REG,
            )
            with dpg.group(tag=_row(cam_id), parent=self.SCROLL_AREA):
                dpg.add_text(f"Camera: {cam_id}")
                dpg.add_text("Live Preview", tag=_label(cam_id))
                with dpg.drawlist(width=DARK_THUMB_W, height=DARK_THUMB_H):
                    dpg.draw_image(
                        texture_tag=_tex(cam_id),
                        pmin=(0, 0), pmax=(DARK_THUMB_W, DARK_THUMB_H),
                    )
                dpg.add_text("", tag=_status(cam_id))
                dpg.add_spacer(height=8)
                dpg.add_separator()
                dpg.add_spacer(height=8)

    def _destroy_rows(self) -> None:
        for cam_id in self._built_cam_ids:
            if dpg.does_item_exist(_row(cam_id)):
                dpg.delete_item(_row(cam_id))
            if dpg.does_item_exist(_tex(cam_id)):
                dpg.delete_item(_tex(cam_id))
        self._built_cam_ids = []

    # per-camera update API

    def update_preview(self, cam_id: str, flat_rgb: np.ndarray) -> None:
        if dpg.does_item_exist(_tex(cam_id)):
            dpg.set_value(_tex(cam_id), flat_rgb)

    def set_cam_label(self, cam_id: str, text: str) -> None:
        if dpg.does_item_exist(_label(cam_id)):
            dpg.set_value(_label(cam_id), text)

    def set_cam_status(self, cam_id: str, text: str) -> None:
        if dpg.does_item_exist(_status(cam_id)):
            dpg.set_value(_status(cam_id), text)

    # shared right-column API

    def set_progress(self, count: int, target: int) -> None:
        frac = count / target if target > 0 else 0.0
        dpg.set_value(self.PROGRESS, frac)
        dpg.configure_item(self.PROGRESS, overlay=f"{count} / {target}")

    def set_status(self, text: str) -> None:
        dpg.set_value(self.STATUS, text)

    def sync_buttons(self, capturing: bool, has_result: bool) -> None:
        dpg.configure_item(self.BTN_CAPTURE, enabled=not capturing)
        dpg.configure_item(self.BTN_CANCEL, enabled=capturing)
        dpg.configure_item(self.BTN_SAVE, enabled=(has_result and not capturing))
        dpg.configure_item(self.BTN_APPLY, enabled=(has_result and not capturing))
        dpg.configure_item(self.INP_FRAMES, enabled=not capturing)
