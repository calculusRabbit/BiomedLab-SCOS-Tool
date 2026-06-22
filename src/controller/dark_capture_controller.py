import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import dearpygui.dearpygui as dpg
import numpy as np
from tkinter import filedialog

from config import DARK_THUMB_W, DARK_THUMB_H
from controller.camera_manager import CameraManager
from processing.utils import crop_frame, safe_filename, to_preview_texture
from state.app_state import AppState
from view.dark_capture_window import DarkCaptureWindow


@dataclass
class _CaptureState:
    # tracks accumulation progress for one camera during a capture
    cam_id: str
    target: int          # number of frames to average
    count: int = 0
    running_sum: np.ndarray | int = 0


class DarkCaptureController:
    # Controls the dark image capture window and the frame accumulation logic.

    # Dark images are captured as full-frame averages over N frames,
    # then cropped to the current source ROI before being applied to each camera session.
    # The full-frame average is also saved to disk so it can be reloaded later
    # even if the ROI changes.


    def __init__(self, manager: CameraManager, app_state: AppState, on_path_saved: Callable[[str], None]):
        self._manager = manager
        self._state = app_state
        self._on_path_saved = on_path_saved
        self._window = DarkCaptureWindow()

        self._cam_ids: list[str] = []
        self._captures: dict[str, _CaptureState] = {}
        self._results: dict[str, np.ndarray] = {}
        self._last_preview_frames: dict[str, np.ndarray | None] = {}

    def setup(self) -> None:
        self._window.create(on_close=self._on_window_close)
        dpg.set_item_callback(DarkCaptureWindow.BTN_CAPTURE, self._on_capture_start)
        dpg.set_item_callback(DarkCaptureWindow.BTN_CANCEL,  self._on_capture_cancel)
        dpg.set_item_callback(DarkCaptureWindow.BTN_SAVE,    self._on_save_all)
        dpg.set_item_callback(DarkCaptureWindow.BTN_BROWSE,  self._on_browse)
        dpg.set_item_callback(DarkCaptureWindow.BTN_APPLY,   self._on_apply_all)

    def open(self, cam_ids: list[str]) -> None:
        self._cam_ids = list(cam_ids)
        self._captures = {}
        self._results = {}
        self._last_preview_frames = {c: None for c in cam_ids}

        self._window.set_progress(0, int(dpg.get_value(DarkCaptureWindow.INP_FRAMES)))
        self._window.sync_buttons(capturing=False, has_result=False)
        self._window.show(cam_ids)

    def feed_frame(self, cam_id: str, frame: np.ndarray) -> None:
        if cam_id not in self._captures:
            return
        c = self._captures[cam_id]
        c.running_sum += frame.astype(np.float32)
        c.count += 1
        if c.count >= c.target:
            self._finish_capture(cam_id)

    def is_capturing_for(self, cam_id: str) -> bool:
        return cam_id in self._captures

    def update_ui(self) -> None:
        if not self._cam_ids:
            return
        if not dpg.is_item_shown(DarkCaptureWindow.WINDOW):
            return

        # update shared progress bar with slowest camera
        if self._captures:
            min_count = min(c.count for c in self._captures.values())
            target = next(iter(self._captures.values())).target
            self._window.set_progress(min_count, target)

        for cam_id in self._cam_ids:
            self._refresh_preview(cam_id)

    # private helpers

    def _refresh_preview(self, cam_id: str) -> None:
        session = self._manager.get_session(cam_id)
        if session is None or session.last_frame is None:
            return
        frame = session.last_frame
        if frame is self._last_preview_frames.get(cam_id):
            return
        self._last_preview_frames[cam_id] = frame
        roi = session.roi_set.to_pixels("source")
        cropped = crop_frame(frame, roi)
        self._window.update_preview(cam_id, to_preview_texture(cropped, DARK_THUMB_W, DARK_THUMB_H))

    def _finish_capture(self, cam_id: str) -> None:
        c = self._captures.pop(cam_id)
        result = c.running_sum / c.count
        self._results[cam_id] = result

        self._window.set_cam_label(cam_id, "Result — Averaged Dark Image")
        self._window.set_cam_status(cam_id, f"Done: {c.target} frames averaged.")

        # all cameras finished
        if not self._captures:
            self._window.set_progress(c.target, c.target)
            self._window.set_status(f"All cameras done.")
            self._window.sync_buttons(capturing=False, has_result=True)

    # button callbacks

    def _on_capture_start(self) -> None:
        target = int(dpg.get_value(DarkCaptureWindow.INP_FRAMES))
        self._results = {}
        for cam_id in self._cam_ids:
            self._captures[cam_id] = _CaptureState(cam_id=cam_id, target=target)
            self._window.set_cam_label(cam_id, "Live Preview  (capturing…)")
            self._window.set_cam_status(cam_id, "")
        self._window.set_progress(0, target)
        self._window.set_status("")
        self._window.sync_buttons(capturing=True, has_result=False)

    def _on_capture_cancel(self) -> None:
        self._captures.clear()
        for cam_id in self._cam_ids:
            self._window.set_cam_label(cam_id, "Live Preview")
            self._window.set_cam_status(cam_id, "Cancelled.")
        self._window.set_progress(0, 1)
        self._window.set_status("Cancelled.")
        self._window.sync_buttons(capturing=False, has_result=bool(self._results))

    def _save_results(self, folder: str) -> None:
        Path(folder).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        last_path = ""
        for cam_id, result in self._results.items():
            path = Path(folder) / f"dark_{safe_filename(cam_id)}_{ts}.png"
            cv2.imwrite(str(path), result.clip(0, 255).astype(np.uint8))
            last_path = str(path)
        if last_path:
            self._on_path_saved(last_path)

    def _on_save_all(self) -> None:
        if not self._results:
            self._window.set_status("No results to save.")
            return
        folder = dpg.get_value(DarkCaptureWindow.INP_PATH).strip() or "./data/dark"
        self._save_results(folder)
        self._window.set_status(f"Saved {len(self._results)} file(s) to {folder}")

    def _on_browse(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            dpg.set_value(DarkCaptureWindow.INP_PATH, folder)

    def _on_apply_all(self) -> None:
        if not self._results:
            self._window.set_status("No results to apply.")
            return

        # auto-save full-frame result so it can be reloaded in a future session
        folder = dpg.get_value(DarkCaptureWindow.INP_PATH).strip() or "./data/dark"
        self._save_results(folder)

        applied = 0
        for cam_id, result in self._results.items():
            session = self._manager.get_session(cam_id)
            if session is None:
                continue
            roi = session.roi_set.to_pixels("source")
            cropped = crop_frame(result, roi) if roi else result
            session.dark_image = cropped.astype(np.float32)
            applied += 1
        self._window.set_status(f"Applied to {applied} camera(s) — {time.strftime('%H:%M:%S')}")

    def _on_window_close(self, sender=None, app_data=None) -> None:
        self._captures.clear()
        self._cam_ids = []
        self._last_preview_frames.clear()
        self._window.hide()
