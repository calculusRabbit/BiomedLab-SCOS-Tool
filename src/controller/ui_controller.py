
# UI Controller - wires UI events to hardware and state.

# Responsibilities:
# - Register dearpyGui callbacks
# - Drive the render loop (update called every frame)
# - Read from AppState, write to AppState
# - Delegate hardware operations to CameraManager
# - Push display data to the view (k2 images, plots)


import time

import dearpygui.dearpygui as dpg

from config import (
    TEXTURE_W, TEXTURE_H,
    PLOT_WINDOW_SEC,
    CAMERA_PIXEL_MAX,
    K2_TEXTURE_W, K2_TEXTURE_H,
)
from controller.camera_manager import CameraManager
from config import ROI_CONFIGS
from controller.roi_selector import ROISelector
from processing.scos_result import SCOSResult
from processing.utils import to_display_texture
from state.app_state import AppState
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

    # ── setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> None:
        w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self._ui.ROI_DRAWLIST)

        # Each key matches a name in ROISet, add more ROI boxes here as needed
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
        dpg.set_item_callback(self._ui.BTN_SCAN,self._on_scan)
        dpg.set_item_callback(self._ui.BTN_CONNECT,self._on_connect)
        dpg.set_item_callback(self._ui.BTN_PREVIEW,self._on_preview)
        dpg.set_item_callback(self._ui.BTN_STOP,self._on_stop)
        dpg.set_item_callback(self._ui.BTN_AUTOSCALE, self._on_autoscale)
        dpg.set_item_callback(self._ui.DEVICE_DROPDOWN, self._on_dropdown_change)
        dpg.set_item_callback(self._ui.SLD_GAIN, self._on_gain_change)
        dpg.set_item_callback(self._ui.SLD_EXPOSURE, self._on_exposure_change)

    def shutdown(self) -> None:
        self._manager.stop_all()

    ## render loop (called every frame from main.py) ##

    def update(self) -> None:
        # Pull latest data from every connected camera (all run in parallel)
        for cam_id in self._manager.connected_ids():
            session = self._manager.get_session(cam_id)
            result  = session.pipeline.get_latest()
            if result is None:
                continue

            full_frame, output = result
            session.last_frame = full_frame
            from processing.utils import crop_frame


            t = time.time() - session.data.start_time
            session.data.push(t, output)

        # Only the active camera display the display
        active = self._manager.get_session(self._state.active_cam_id)
        if active is None:
            return

        if active.last_frame is not None:
            self._push_frame(active.last_frame)

        if self._state.is_running and active.data:
            self._push_plots(active.data)

            latest = active.data.latest()
            if latest is not None:
                self._push_k2_maps(latest)

    ## button callbacks ##

    def _on_scan(self) -> None:
        names = self._manager.scan()
        if not names:
            return
        self._switch_to(names[0])

    def _on_connect(self) -> None:
        cam_id = self._selected_cam_id()
        if not cam_id:
            return
        self._manager.connect(cam_id)
        self._sync_dropdown(cam_id)

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
            session = self._manager.get_session(cam_id)
            session.data.clear()
            session.data.start_time = now
        self._state.is_running = True

    def _on_stop(self) -> None:
        self._state.is_running = False

    def _on_autoscale(self) -> None:
        for tag in self._ui.GRAPH_TAG:
            y_tag = dpg.get_item_children(tag, 1)[1]
            dpg.fit_axis_data(y_tag)

    # hardware(camera) parameter callbacks ##

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

    ## resize ##

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

    # mouse events (for like user click or drag ROI box) ##

    def _on_mouse_down(self, s, a) -> None:
        mx, my = self._local_mouse()
        if self._is_over_drawlist(mx, my):
            for roi in self._rois.values():
                roi.on_mouse_down(mx, my)

    def _on_mouse_move(self, s, a) -> None:
        mx, my = self._local_mouse()
        for roi in self._rois.values():
            roi.on_mouse_move(mx, my)
        # only sync ROI coords to session while actually dragging, not every mouse move
        if any(roi.is_dragging() for roi in self._rois.values()):
            self._save_rois_to_active()

    def _on_mouse_release(self, s, a) -> None:
        for roi in self._rois.values():
            roi.on_mouse_release()
        self._save_rois_to_active()  # final save when drag ends

    ## display helpers ##

    def _push_frame(self, frame) -> None:
        rgb = to_display_texture(frame / CAMERA_PIXEL_MAX, TEXTURE_W, TEXTURE_H)
        dpg.set_value(self._ui.LIVE_TEXTURE, rgb)

    def _push_plots(self, data: SCOSTimeSeries) -> None:
        t, k2, bfi, cc, od = data.as_lists()
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

    ## navigation helpers ##

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

    def _selected_cam_id(self) -> str | None:
        """Map the dropdown's current display value back to a raw cam_id."""
        scan_list = self._manager.scan_list
        connected = self._manager.connected_ids()
        selected  = dpg.get_value(self._ui.DEVICE_DROPDOWN)
        for i, name in enumerate(scan_list):
            display = f"{name} (connected)" if name in connected else name
            if display == selected:
                return scan_list[i]
        return None

    def _sync_dropdown(self, active_cam_id: str) -> None:
        """Rebuild dropdown items and set the displayed label in one call."""
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
