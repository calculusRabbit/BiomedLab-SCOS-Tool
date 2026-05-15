
# UI Controller - wires UI events to hardware and state.

# Responsibilities:
# - Register dearpyGui callbacks
# - Drive the render loop (update called every frame)
# - Read from AppState, write to AppState
# - Delegate hardware operations to CameraManager
# - Push display data to the view (k2 images, plots)


import time

import dearpygui.dearpygui as dpg
import numpy as np
from tkinter import filedialog

from config import (
    TEXTURE_W, TEXTURE_H,
    PLOT_WINDOW_SEC,
    CAMERA_PIXEL_MAX,
    K2_TEXTURE_W, K2_TEXTURE_H,
    ROI_CONFIGS,
)
from controller.camera_manager import CameraManager
from controller.dark_capture_controller import DarkCaptureController
from controller.roi_selector import ROISelector
from processing.scos_result import SCOSResult
from processing.utils import to_display_texture
from state.app_state import AppState, CameraState
from state.roi_set import ROISet
from state.scos_timeseries import SCOSTimeSeries
from view.ui import SCOS_UI


class UIController:

    def __init__(self, ui: SCOS_UI, manager: CameraManager, app_state: AppState):
        self._ui = ui
        self._manager = manager
        self._state = app_state
        self._last_size = (0, 0)
        self._rois: dict[str, ROISelector] = {}
        self._dark_ctrl = DarkCaptureController(
            manager, app_state,
            lambda p: dpg.set_value(self._ui.INP_DARKPATH, p),
        )

    # setup

    def setup(self) -> None:
        w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self._ui.ROI_DRAWLIST)

        default_coords = ROISet()
        for name, color in ROI_CONFIGS.items():
            roi = ROISelector(self._ui.ROI_DRAWLIST, w, h, name=f"roi_{name}", color=color)
            roi.set_coords_normalized(*default_coords.get(name))
            self._rois[name] = roi

        with dpg.handler_registry():
            dpg.add_mouse_down_handler(callback=self._on_mouse_down)
            dpg.add_mouse_move_handler(callback=self._on_mouse_move)
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_item_callback(self._ui.BTN_SCAN,        self._on_scan)
        dpg.set_item_callback(self._ui.BTN_CONNECT,     self._on_connect)
        dpg.set_item_callback(self._ui.BTN_PREVIEW,     self._on_preview)
        dpg.set_item_callback(self._ui.BTN_START,       self._on_rec_start)
        dpg.set_item_callback(self._ui.BTN_STOP,        self._on_rec_stop)
        dpg.set_item_callback(self._ui.BTN_AUTOSCALE,   self._on_autoscale)
        dpg.set_item_callback(self._ui.DEVICE_DROPDOWN, self._on_dropdown_change)
        dpg.set_item_callback(self._ui.SLD_GAIN,        self._on_gain_change)
        dpg.set_item_callback(self._ui.SLD_EXPOSURE,    self._on_exposure_change)
        dpg.set_item_callback(self._ui.BTN_REC_BROWSE,  self._on_rec_browse)
        dpg.set_item_callback(self._ui.BTN_DARKIMG,     self._on_dark_open)
        dpg.set_item_callback(self._ui.BTN_DARKBROWSE,  self._on_dark_browse)

        self._dark_ctrl.setup()
        self.sync_ui()

    def shutdown(self) -> None:
        self._manager.stop_all()

    # render loop (called every frame from main.py)
    def update(self) -> None:
        for cam_id in self._manager.connected_ids():
            session = self._manager.get_session(cam_id)
            result  = session.pipeline.get_latest()
            if result is None:
                continue
            full_frame, output = result
            session.last_frame = full_frame
            t = time.time() - session.data.start_time
            session.data.push(t, output)

            if self._dark_ctrl.is_capturing_for(cam_id):
                self._dark_ctrl.feed_frame(full_frame)

        self._dark_ctrl.update_ui()

        active = self._manager.get_session(self._state.active_cam_id)
        if active is None:
            return

        if active.last_frame is not None:
            self._push_frame(active.last_frame)

        if self._state.camera_state in (CameraState.PREVIEWING, CameraState.RECORDING):
            self._push_plots(active.data)
            latest = active.data.latest()
            if latest is not None:
                self._push_k2_maps(latest)
            self._update_rec_status()

    # button callbacks

    def _on_scan(self) -> None:
        names = self._manager.scan()
        if not names:
            return
        self._rebuild_rec_checkboxes(names)
        self._switch_to(names[0])
        self._state.camera_state = CameraState.IDLE
        self.sync_ui()

    def _on_connect(self) -> None:
        cam_id = self._selected_cam_id()
        if not cam_id:
            return
        self._manager.connect(cam_id)
        self._sync_dropdown(cam_id)
        self._state.camera_state = CameraState.CONNECTED
        self.sync_ui()

    def _on_dropdown_change(self) -> None:
        cam_id = self._selected_cam_id()
        if cam_id and cam_id != self._state.active_cam_id:
            self._switch_to(cam_id)

    def _on_preview(self) -> None:
        connected = self._manager.connected_ids()
        if not connected:
            return
        now = time.time()
        for cam_id in connected:
            self._manager.get_session(cam_id).reset(now)
        self._state.camera_state = CameraState.PREVIEWING
        self.sync_ui()

    def _on_rec_browse(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            dpg.set_value(self._ui.INP_REC_FOLDER, folder)

    def _on_dark_open(self) -> None:
        cam_id = self._state.active_cam_id
        if cam_id is None:
            return
        self._dark_ctrl.open(cam_id)

    def _on_dark_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Load dark image",
            filetypes=[("NumPy array", "*.npy"), ("All files", "*.*")],
        )
        if not path:
            return
        img = np.load(path)
        dpg.set_value(self._ui.INP_DARKPATH, path)
        session = self._manager.get_session(self._state.active_cam_id)
        if session is not None:
            session.dark_image = img
            session.pipeline.set_dark_image(img)

    def _on_rec_start(self) -> None:
        folder = dpg.get_value(self._ui.INP_REC_FOLDER) or "./data"
        buffer_size = int(dpg.get_value(self._ui.INP_REC_BUFFER))
        interval_ms = float(dpg.get_value(self._ui.INP_REC_INTERVAL))
        study_name = dpg.get_value(self._ui.INPUT_STUDY)
        subject_id = dpg.get_value(self._ui.INPUT_SUBJECT)
        run_number = dpg.get_value(self._ui.INPUT_RUN)

        for cam_id in self._manager.connected_ids():
            if cam_id in self._state.record_cam_ids:
                self._manager.get_session(cam_id).pipeline.start_recording(
                    folder, cam_id, interval_ms, buffer_size,
                    study_name=study_name,
                    subject_id=subject_id,
                    run_number=run_number,
                )

        self._state.camera_state = CameraState.RECORDING
        self._state.record_start_time = time.time()
        self.sync_ui()

    def _on_rec_stop(self) -> None:
        for cam_id in self._manager.connected_ids():
            session = self._manager.get_session(cam_id)
            session.pipeline.stop_recording()
        self._state.camera_state = CameraState.PREVIEWING
        dpg.set_value(self._ui.REC_STATUS, "")
        self.sync_ui()

    def _on_autoscale(self) -> None:
        for tag in self._ui.GRAPH_TAG:
            y_tag = dpg.get_item_children(tag, 1)[1]
            dpg.fit_axis_data(y_tag)

    def _on_rec_cam_toggle(self, cam_id: str, checked: bool) -> None:
        if checked:
            self._state.record_cam_ids.add(cam_id)
        else:
            self._state.record_cam_ids.discard(cam_id)
        self.sync_ui()

    # state machine
    def sync_ui(self) -> None:
        state = self._state.camera_state
        has_cameras = len(self._state.record_cam_ids) > 0

        is_idle = (state == CameraState.IDLE)
        is_connected = (state == CameraState.CONNECTED)
        is_previewing = (state == CameraState.PREVIEWING)
        is_recording = (state == CameraState.RECORDING)

        can_record = (is_previewing and has_cameras)

        dpg.configure_item(self._ui.BTN_SCAN,     enabled=(not is_recording))
        dpg.configure_item(self._ui.BTN_CONNECT,  enabled=is_idle)
        dpg.configure_item(self._ui.BTN_PREVIEW,  enabled=is_connected)
        dpg.configure_item(self._ui.BTN_START,    enabled=can_record)
        dpg.configure_item(self._ui.BTN_STOP,     enabled=is_recording)
        dpg.configure_item(self._ui.BTN_DARKIMG,  enabled=(not is_idle))



    # status update (called every frame while streaming)

    def _update_rec_status(self) -> None:
        session = self._manager.get_session(self._state.active_cam_id)
        if session is None:
            return
        p = session.pipeline

        dpg.set_value(self._ui.FPS_CAM, f"{p.fps_camera:.1f} fps")
        dpg.set_value(self._ui.FPS_PROCESSED, f"{p.fps_processed:.1f} fps")
        dpg.set_value(self._ui.TOTAL_PROCESSED,str(p.total_processed))
        dpg.set_value(self._ui.DROP_FRAME_PROCESSING, str(p.drop_processed))
        dpg.set_value(self._ui.QUEUE_SAVING, str(p.recording.queue_size))
        dpg.set_value(self._ui.DROPPED_FRAMEs_SAVING, str(p.recording.dropped))

        if self._state.camera_state == CameraState.RECORDING:
            elapsed = time.time() - self._state.record_start_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            dpg.set_value(self._ui.REC_STATUS, f"  ● Recording  {h:02d}:{m:02d}:{s:02d}")

    # hardware parameter callbacks

    def _on_gain_change(self) -> None:
        value = float(dpg.get_value(self._ui.SLD_GAIN))
        active = self._manager.get_session(self._state.active_cam_id)
        if active and active.is_connected:
            active.pipeline.set_gain(value)

    def _on_exposure_change(self) -> None:
        value = float(dpg.get_value(self._ui.SLD_EXPOSURE))
        active = self._manager.get_session(self._state.active_cam_id)
        if active and active.is_connected:
            active.pipeline.set_exposure_time(value)

    # resize

    def _on_resize(self) -> None:
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) == self._last_size or w <= 0 or h <= 0:
            return
        self._last_size = (w, h)
        self._ui.resize(w, h)
        new_w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        new_h = dpg.get_item_height(self._ui.ROI_DRAWLIST)
        for roi in self._rois.values():
            roi.update_display_size(new_w, new_h)
        self._save_rois_to_active()

    # mouse events

    def _on_mouse_down(self, s, a) -> None:
        if self._state.camera_state == CameraState.RECORDING:
            return
        mx, my = self._local_mouse()
        if self._is_over_drawlist(mx, my):
            for roi in self._rois.values():
                roi.on_mouse_down(mx, my)

    def _on_mouse_move(self, s, a) -> None:
        mx, my = self._local_mouse()
        for roi in self._rois.values():
            roi.on_mouse_move(mx, my)
        if any(roi.is_dragging() for roi in self._rois.values()):
            self._save_rois_to_active()

    def _on_mouse_release(self, s, a) -> None:
        for roi in self._rois.values():
            roi.on_mouse_release()
        self._save_rois_to_active()

    # display helpers

    def _push_frame(self, frame) -> None:
        rgb = to_display_texture(frame / CAMERA_PIXEL_MAX, TEXTURE_W, TEXTURE_H)
        dpg.set_value(self._ui.LIVE_TEXTURE, rgb)

    def _push_plots(self, data: SCOSTimeSeries) -> None:
        t, k2, bfi, cc, od = data.as_lists()
        if not t:
            return
        for i, series in enumerate([k2, bfi, cc, od]):
            dpg.set_value(self._ui.PLOT_SERIES_TAG[i], [t, series])
        t_max = max(PLOT_WINDOW_SEC, t[-1]) + 0.5
        for x_tag in self._ui.GRAPH_X_TAG:
            dpg.set_axis_limits(x_tag, t_max - PLOT_WINDOW_SEC, t_max)

    def _push_k2_maps(self, output: SCOSResult) -> None:
        for i, img in enumerate(output.k2_images):
            if img is None:
                continue
            rgb = to_display_texture(img, K2_TEXTURE_W, K2_TEXTURE_H)
            dpg.set_value(self._ui.K2_TEXTURE_TAG[i], rgb)

    # navigation helpers

    def _switch_to(self, cam_id: str) -> None:
        self._save_rois_to_active()
        self._state.active_cam_id = cam_id
        session = self._manager.get_session(cam_id)
        if session:
            for name, roi in self._rois.items():
                if name in session.roi_set.names():
                    roi.set_coords_normalized(*session.roi_set.get(name))
        self._sync_dropdown(cam_id)
        self._on_autoscale()

    def _save_rois_to_active(self) -> None:
        session = self._manager.get_session(self._state.active_cam_id)
        if session:
            for name, roi in self._rois.items():
                session.roi_set.set(name, roi.get_coords_normalized())
            session.sync_pipeline_roi()

    def _rebuild_rec_checkboxes(self, cam_ids: list[str]) -> None:
        for child in dpg.get_item_children(self._ui.REC_CAM_GROUP, 1):
            dpg.delete_item(child)
        self._state.record_cam_ids = set()
        for cam_id in cam_ids:
            dpg.add_checkbox(
                label=cam_id, default_value=False, parent=self._ui.REC_CAM_GROUP,
                user_data=cam_id, callback=lambda s, a, u: self._on_rec_cam_toggle(u, a)
            )

    def _selected_cam_id(self) -> str | None:
        scan_list = self._manager.scan_list
        connected = self._manager.connected_ids()
        selected  = dpg.get_value(self._ui.DEVICE_DROPDOWN)
        for i, name in enumerate(scan_list):
            display = f"{name} (connected)" if name in connected else name
            if display == selected:
                return scan_list[i]
        return None

    def _sync_dropdown(self, active_cam_id: str) -> None:
        connected = self._manager.connected_ids()
        names = [
            f"{n} (connected)" if n in connected else n
            for n in self._manager.scan_list
        ]
        dpg.configure_item(self._ui.DEVICE_DROPDOWN, items=names)
        label = f"{active_cam_id} (connected)" if active_cam_id in connected else active_cam_id
        dpg.set_value(self._ui.DEVICE_DROPDOWN, label)

    def _local_mouse(self) -> tuple[float, float]:
        mx, my = dpg.get_mouse_pos(local=False)
        rect_min = dpg.get_item_rect_min(self._ui.ROI_DRAWLIST)
        return mx - rect_min[0], my - rect_min[1]

    def _is_over_drawlist(self, mx: float, my: float) -> bool:
        w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self._ui.ROI_DRAWLIST)
        return 0 <= mx <= w and 0 <= my <= h
