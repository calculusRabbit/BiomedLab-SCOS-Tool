# controller/dark_capture_controller.py
#
# Owns the dark image capture flow:
#   - open/close the capture window
#   - accumulate frames fed by UIController
#   - save result as .npy and apply to the camera pipeline

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg
import numpy as np
from tkinter import filedialog

from config import DARK_PREVIEW_W, DARK_PREVIEW_H
from controller.camera_manager import CameraManager
from processing.utils import crop_frame, to_preview_texture
from state.app_state import AppState
from view.dark_capture_window import DarkCaptureWindow


@dataclass
class _CaptureState:
    cam_id:      str
    target:      int
    count:       int               = 0
    running_sum: np.ndarray | None = None


class DarkCaptureController:

    def __init__(self, manager: CameraManager, app_state: AppState, on_path_saved: Callable[[str], None]):
        self._manager       = manager
        self._state         = app_state
        self._on_path_saved = on_path_saved
        self._window        = DarkCaptureWindow()

        self._cam_id:             str | None           = None
        self._capture:            _CaptureState | None = None
        self._result:             np.ndarray | None    = None
        self._last_preview_frame: np.ndarray | None    = None

    def setup(self) -> None:
        self._window.create(on_close=self._on_window_close)
        dpg.set_item_callback(DarkCaptureWindow.BTN_CAPTURE, self._on_capture_start)
        dpg.set_item_callback(DarkCaptureWindow.BTN_CANCEL,  self._on_capture_cancel)
        dpg.set_item_callback(DarkCaptureWindow.BTN_SAVE,    self._on_save)
        dpg.set_item_callback(DarkCaptureWindow.BTN_BROWSE,  self._on_browse)
        dpg.set_item_callback(DarkCaptureWindow.BTN_APPLY,   self._on_apply)

    def open(self, cam_id: str) -> None:
        self._cam_id             = cam_id
        self._capture            = None
        self._last_preview_frame = None

        session      = self._manager.get_session(cam_id)
        self._result = session.dark_image if session else None
        has_result   = self._result is not None

        self._window.set_progress(0, 1)
        if has_result:
            roi     = session.roi_set.to_pixels("source") if session else None
            display = crop_frame(self._result, roi) if roi else self._result
            self._window.update_preview(to_preview_texture(display, DARK_PREVIEW_W, DARK_PREVIEW_H))
            self._window.set_preview_label("Result — Averaged Dark Image")
            self._window.set_status("Previously captured dark image loaded.")
        else:
            self._window.set_preview_label("Live Preview")
            self._window.set_status("Block all light sources, then click Capture.")
        self._sync_buttons(capturing=False, has_result=has_result)
        self._window.show(cam_id)

    def feed_frame(self, frame: np.ndarray) -> None:
        if self._capture is None:
            return
        c = self._capture
        if c.running_sum is None:
            c.running_sum = frame.astype(np.float32)
        else:
            c.running_sum += frame.astype(np.float32)
        c.count += 1
        if c.count >= c.target:
            self._finish_capture()

    def is_capturing_for(self, cam_id: str) -> bool:
        return self._capture is not None and self._capture.cam_id == cam_id

    def update_ui(self) -> None:
        if self._cam_id is None:
            return
        if not dpg.is_item_shown(DarkCaptureWindow.WINDOW):
            return
        if self._capture is not None:
            self._window.set_progress(self._capture.count, self._capture.target)
        if self._result is None:
            self._refresh_live_preview()

    # private helpers

    def _sync_buttons(self, capturing: bool, has_result: bool) -> None:
        dpg.configure_item(DarkCaptureWindow.BTN_CAPTURE, enabled=not capturing)
        dpg.configure_item(DarkCaptureWindow.BTN_CANCEL,  enabled=capturing)
        dpg.configure_item(DarkCaptureWindow.BTN_SAVE,    enabled=(has_result and not capturing))
        dpg.configure_item(DarkCaptureWindow.BTN_APPLY,   enabled=(has_result and not capturing))
        dpg.configure_item(DarkCaptureWindow.INP_FRAMES,  enabled=not capturing)

    def _refresh_live_preview(self) -> None:
        session = self._manager.get_session(self._cam_id)
        if session is None or session.last_frame is None:
            return
        frame = session.last_frame
        if frame is self._last_preview_frame:
            return
        self._last_preview_frame = frame
        roi     = session.roi_set.to_pixels("source")
        cropped = crop_frame(frame, roi)
        self._window.update_preview(to_preview_texture(cropped, DARK_PREVIEW_W, DARK_PREVIEW_H))

    def _finish_capture(self) -> None:
        c             = self._capture
        self._result  = c.running_sum / c.count
        self._capture = None

        session = self._manager.get_session(self._cam_id)
        if session is not None:
            session.dark_image = self._result

        roi     = session.roi_set.to_pixels("source") if session else None
        display = crop_frame(self._result, roi) if roi else self._result
        self._window.update_preview(to_preview_texture(display, DARK_PREVIEW_W, DARK_PREVIEW_H))
        self._window.set_preview_label("Result — Averaged Dark Image")
        self._window.set_progress(c.target, c.target)
        self._window.set_status(f"Done: {c.target} frames averaged.")
        self._sync_buttons(capturing=False, has_result=True)

    # button callbacks

    def _on_capture_start(self) -> None:
        if self._cam_id is None:
            return
        target        = int(dpg.get_value(DarkCaptureWindow.INP_FRAMES))
        self._capture = _CaptureState(cam_id=self._cam_id, target=target)
        self._result  = None
        self._window.set_preview_label("Live Preview  (capturing…)")
        self._window.set_progress(0, target)
        self._window.set_status("")
        self._sync_buttons(capturing=True, has_result=False)

    def _on_capture_cancel(self) -> None:
        self._capture = None
        self._window.set_preview_label("Live Preview")
        self._window.set_progress(0, 1)
        self._window.set_status("Cancelled.")
        self._sync_buttons(capturing=False, has_result=self._result is not None)

    def _on_save(self) -> None:
        if self._result is None or self._cam_id is None:
            return
        folder = dpg.get_value(DarkCaptureWindow.INP_PATH).strip() or "./data/dark"
        Path(folder).mkdir(parents=True, exist_ok=True)

        safe_cam = "".join(c if c.isalnum() or c in "-_" else "_" for c in self._cam_id)
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = Path(folder) / f"dark_{safe_cam}_{ts}.npy"
        np.save(str(path), self._result)

        self._on_path_saved(str(path))
        self._window.set_status(f"Saved: {path.name}")

    def _on_browse(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            dpg.set_value(DarkCaptureWindow.INP_PATH, folder)

    def _on_apply(self) -> None:
        if self._result is None or self._cam_id is None:
            return
        session = self._manager.get_session(self._cam_id)
        if session is None:
            return
        session.pipeline.set_dark_image(self._result)
        self._window.set_status(f"Applied to {self._cam_id} — {time.strftime('%H:%M:%S')}")

    def _on_window_close(self, sender=None, app_data=None) -> None:
        self._capture            = None
        self._cam_id             = None
        self._last_preview_frame = None
