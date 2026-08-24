# Central controller that connects the UI, hardware, and state together.
#
# Responsibilities:
#   - Register all button/slider/mouse callbacks at startup
#   - Drive the render loop (update() is called every frame from main.py)
#   - Manage the camera state machine (IDLE -> CONNECTED <-> RECORDING)
#     plus the independent preview_on flag (SCOS processing/visualization)
#   - Push new frames, plots, and K2 maps to the UI
#
# Threading note: all methods here run on the main (UI) thread.
# The pipeline grab and process threads only communicate back via queues.


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
from controller.recording_guard import check as guard_check
from controller.trigger_manager import TriggerManager
from recording.frame_writer import SessionMeta
from recording.trigger_writer import TriggerWriter
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
        self._rois: dict[str, ROISelector] = {}  # one ROISelector per ROI name ("1", "2")
        self._plot_window_sec = PLOT_WINDOW_SEC  # visible x-range, user-adjustable
        self._trigger = TriggerManager()
        self._trigger_writer = TriggerWriter()

    # setup

    def setup(self) -> None:
        # create ROI overlay rectangles on the live feed drawlist
        w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self._ui.ROI_DRAWLIST)

        default_coords = ROISet()
        for name, color in ROI_CONFIGS.items():
            roi = ROISelector(self._ui.ROI_DRAWLIST, w, h, name=f"roi_{name}", color=color)
            roi.set_coords_normalized(*default_coords.get(name))
            self._rois[name] = roi

        # mouse handlers are global so we filter by position inside the callback
        with dpg.handler_registry():
            dpg.add_mouse_down_handler(callback=self._on_mouse_down)
            dpg.add_mouse_move_handler(callback=self._on_mouse_move)
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_item_callback(self._ui.BTN_SCAN, self._on_scan)
        dpg.set_item_callback(self._ui.BTN_CONNECT, self._on_connect)
        dpg.set_item_callback(self._ui.BTN_PREVIEW, self._on_preview)
        dpg.set_item_callback(self._ui.BTN_PAUSE, self._on_pause)
        dpg.set_item_callback(self._ui.BTN_START, self._on_rec_start)
        dpg.set_item_callback(self._ui.BTN_STOP, self._on_rec_stop)
        dpg.set_item_callback(self._ui.BTN_AUTOSCALE, self._on_autoscale)
        dpg.set_item_callback(self._ui.INP_TIME_WINDOW, self._on_time_window_change)
        dpg.set_item_callback(self._ui.DEVICE_DROPDOWN, self._on_dropdown_change)
        dpg.set_item_callback(self._ui.SLD_GAIN, self._on_gain_change)
        dpg.set_item_callback(self._ui.SLD_EXPOSURE, self._on_exposure_change)
        dpg.set_item_callback(self._ui.BTN_REC_BROWSE, self._on_rec_browse)
        dpg.set_item_callback(self._ui.BTN_TRIGGER_SCAN, self._on_trigger_scan)
        dpg.set_item_callback(self._ui.BTN_TRIGGER_CONNECT, self._on_trigger_connect)

        self.sync_ui()

    def shutdown(self) -> None:
        self._manager.stop_all()

    # render loop (called every frame from main.py)

    def update(self) -> None:
        # pull new results from every connected camera pipeline
        for cam_id in self._manager.connected_ids():
            session = self._manager.get_session(cam_id)

            if session.pipeline.crashed:
                self._on_pipeline_crash(cam_id)
                continue

            # live image comes straight from the grab thread so it keeps
            # updating even while SCOS processing is paused
            session.last_frame = session.pipeline.latest_frame

            result = session.pipeline.get_latest()
            if result is None:
                continue

            _, output = result

            # t is time since preview/recording started, used as the x-axis in plots
            t = time.time() - session.data.start_time
            session.data.push(t, output)

        # drain trigger markers (non-blocking) — always print so receipt is
        # visible in the terminal; also log to file while recording
        for marker, pc_time in self._trigger.poll():
            print(f"[Trigger] {marker}")
            if self._state.camera_state == CameraState.RECORDING:
                self._trigger_writer.push(pc_time, marker)

        # only push display data for the camera currently selected in the dropdown
        active = self._manager.get_session(self._state.active_cam_id)
        if active is None:
            return

        if active.last_frame is not None:
            self._push_frame(active.last_frame)

        if self._state.preview_on:
            self._push_plots(active.data)
            latest = active.data.latest()
            if latest is not None:
                self._push_k2_maps(latest)
        # status panel must keep updating while recording even if preview is paused
        if self._state.preview_on or self._state.camera_state == CameraState.RECORDING:
            self._update_rec_status()

    # button callbacks

    def _on_scan(self) -> None:
        # scan for connected cameras, rebuild the dropdown and checkboxes, reset state
        cameras = self._manager.scan()  # returns list of (serial, display_name)
        if not cameras:
            return
        self._rebuild_rec_checkboxes(cameras)
        self._switch_to(cameras[0][0])  # default to first camera found
        self._state.camera_state = CameraState.IDLE
        self.sync_ui()

    def _on_trigger_scan(self) -> None:
        # refresh the trigger dropdown with the LSL marker streams currently
        # visible on the network (discovery runs continuously since app start)
        names = self._trigger.scan()
        dpg.configure_item(self._ui.TRIGGER_DROPDOWN, items=names)
        if names:
            dpg.set_value(self._ui.TRIGGER_DROPDOWN, names[0])
        print(f"[Trigger] scan found {len(names)} stream(s): {names}")

    def _on_trigger_connect(self) -> None:
        # connect to the marker stream selected in the dropdown; markers are then
        # drained every frame in update()
        name = dpg.get_value(self._ui.TRIGGER_DROPDOWN)
        if not name:
            print("[Trigger] no stream selected — click Scan first")
            return
        if self._trigger.connect(name):
            print(f"[Trigger] connected to '{name}'")
        else:
            print(f"[Trigger] stream '{name}' not found — rescan and try again")

    def _on_connect(self) -> None:
        cam_id = self._selected_cam_id()
        if not cam_id:
            return
        session = self._manager.connect(cam_id)
        if session is None:
            return
        # push the current ROI to the pipeline so it is ready before preview starts
        session.sync_pipeline_roi()
        # sliders now reflect this camera's true hardware limits
        self._sync_param_sliders(session)
        # connecting implies intent to use the camera — pre-check its recording
        # checkbox (the user can still uncheck it)
        if dpg.does_item_exist(self._rec_checkbox_tag(cam_id)):
            dpg.set_value(self._rec_checkbox_tag(cam_id), True)
        self._state.record_cam_ids.add(cam_id)
        # if preview is already running, the new camera joins it immediately
        if self._state.preview_on:
            session.reset(time.time())
            session.pipeline.set_processing(True)
        self._sync_dropdown(cam_id)
        # only advance to CONNECTED if we are still in IDLE, do not override RECORDING
        if self._state.camera_state == CameraState.IDLE:
            self._state.camera_state = CameraState.CONNECTED
        self.sync_ui()

    def _on_dropdown_change(self) -> None:
        # user switched the active camera in the dropdown, update the display
        cam_id = self._selected_cam_id()
        if cam_id and cam_id != self._state.active_cam_id:
            self._switch_to(cam_id)
            self.sync_ui()

    def _on_preview(self) -> None:
        # turn on SCOS processing + visualization for all connected cameras
        # does not touch camera_state — preview can be resumed mid-recording
        connected = self._manager.connected_ids()
        if not connected:
            return
        now = time.time()
        for cam_id in connected:
            session = self._manager.get_session(cam_id)
            session.reset(now)
            session.pipeline.set_processing(True)
        self._state.preview_on = True
        self.sync_ui()

    def _on_pause(self) -> None:
        # turn off SCOS processing + visualization to free CPU
        # recording (fed by the grab thread) continues untouched
        for cam_id in self._manager.connected_ids():
            self._manager.get_session(cam_id).pipeline.set_processing(False)
        self._state.preview_on = False
        self.sync_ui()

    def _on_rec_browse(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            dpg.set_value(self._ui.INP_REC_FOLDER, folder)

    def _on_rec_start(self) -> None:
        study_name = dpg.get_value(self._ui.INPUT_STUDY).strip()
        subject_id = dpg.get_value(self._ui.INPUT_SUBJECT).strip()
        if not study_name or not subject_id:
            self._set_rec_status("  Study Name and Subject ID required", error=True)
            return

        folder = dpg.get_value(self._ui.INP_REC_FOLDER) or "./data"
        interval_ms = float(dpg.get_value(self._ui.INP_REC_INTERVAL))
        buffer_size = int(dpg.get_value(self._ui.INP_REC_BUFFER))
        run_number = dpg.get_value(self._ui.INPUT_RUN)
        max_frames, max_seconds = self._read_rec_limit()

        session_meta = SessionMeta(
            study_name=study_name,
            subject_id=subject_id,
            run_number=run_number,
            output_folder=folder,
            interval_ms=interval_ms,
            buffer_size=buffer_size,
            max_frames=max_frames,
            max_seconds=max_seconds,
        )

        # run pre-flight checks before starting, block on errors, print warnings
        result = guard_check(self._manager, self._state, session_meta)
        if not result.ok:
            self._set_rec_status(f"  {result.errors[0]}", error=True)
            return
        for msg in result.info:
            print(f"[RecordingGuard] {msg}")
        for msg in result.warnings:
            print(f"[RecordingGuard] warning: {msg}")

        # start recording only for cameras that are checked in the recording panel
        for cam_id in self._manager.connected_ids():
            if cam_id in self._state.record_cam_ids:
                session = self._manager.get_session(cam_id)
                session.sync_pipeline_roi()
                # snapshot this camera's ROI boxes so they are saved in the h5 file
                # (ROIs cannot be moved while recording, so one snapshot is exact)
                rois = {
                    name: {
                        "normalized_xyxy": session.roi_set.get(name),
                        "pixels_xyxy": session.roi_set.to_pixels(name),
                    }
                    for name in session.roi_set.names()
                }
                session.pipeline.start_recording(session_meta, rois)

        # marker log opens/closes with the recording session
        self._trigger_writer.start(session_meta)

        self._state.camera_state = CameraState.RECORDING
        self._state.record_start_time = time.time()
        self.sync_ui()

    def _read_rec_limit(self) -> tuple[int, float]:
        # convert the "Stop after" value + unit into (max_frames, max_seconds)
        # 0 means no limit — recording runs until Stop is pressed
        value = int(dpg.get_value(self._ui.INP_REC_LIMIT_VALUE))
        unit = dpg.get_value(self._ui.DD_REC_LIMIT_UNIT)
        if unit == "frames":
            return value, 0.0
        if unit in ("seconds", "minutes", "hours"):
            factor = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0}[unit]
            return 0, value * factor
        return 0, 0.0  # manual

    def _on_rec_stop(self) -> None:
        for cam_id in self._manager.connected_ids():
            session = self._manager.get_session(cam_id)
            session.pipeline.stop_recording()
        self._trigger_writer.stop()
        self._state.camera_state = CameraState.CONNECTED
        self._set_rec_status("")
        self.sync_ui()

    def _on_time_window_change(self) -> None:
        self._plot_window_sec = float(dpg.get_value(self._ui.INP_TIME_WINDOW))

    def _on_autoscale(self) -> None:
        # fit the y-axis of every plot to the data currently visible in the
        # x-window. dpg.fit_axis_data is not used because it fits the whole
        # series history (including points scrolled off-screen) and breaks on
        # the inf/NaN samples that OD can produce.
        session = self._manager.get_session(self._state.active_cam_id)
        if session is None:
            return
        t, k2, bfi, cc, od = session.data.as_lists()
        if not t:
            return
        t = np.asarray(t)
        visible = t >= t[-1] - self._plot_window_sec
        for i, series in enumerate([k2, bfi, cc, od]):
            values = np.asarray(series)[visible]
            values = values[np.isfinite(values)]
            if values.size == 0:
                continue
            lo, hi = float(values.min()), float(values.max())
            pad = 0.05 * (hi - lo) or max(abs(hi) * 0.05, 1e-6)  # flat line: pad relative to magnitude
            dpg.set_axis_limits(self._ui.GRAPH_Y_TAG[i], lo - pad, hi + pad)

    def _on_rec_cam_toggle(self, cam_id: str, checked: bool) -> None:
        # called when user checks or unchecks a camera in the recording panel
        if checked:
            self._state.record_cam_ids.add(cam_id)
        else:
            self._state.record_cam_ids.discard(cam_id)
        self.sync_ui()

    def _on_pipeline_crash(self, cam_id: str) -> None:
        # a background thread died unexpectedly, stop everything and reset to IDLE
        print(f"[UIController] pipeline crash detected: {cam_id}")
        session = self._manager.get_session(cam_id)
        session.pipeline.stop()
        session.is_connected = False
        for cid in self._manager.connected_ids():
            s = self._manager.get_session(cid)
            if s:
                s.pipeline.stop_recording()
        self._trigger_writer.stop()
        self._state.camera_state = CameraState.IDLE
        self._state.preview_on = False
        self._set_rec_status("  Camera error, please rescan", error=True)
        self.sync_ui()

    # state machine

    def sync_ui(self) -> None:
        # enable or disable buttons based on the current camera state
        # this is called after every state change so the UI always matches reality
        state = self._state.camera_state
        preview_on = self._state.preview_on

        is_idle = (state == CameraState.IDLE)
        is_connected = (state == CameraState.CONNECTED)
        is_recording = (state == CameraState.RECORDING)

        # recording only requires a connected camera — missing checkboxes or
        # fields are reported by the guard when Start is clicked, so the user
        # always gets feedback instead of a silently dead button
        can_record = is_connected

        # connect button state depends on the currently selected camera in the dropdown
        active_session = self._manager.get_session(self._state.active_cam_id)
        active_connected = active_session is not None and active_session.is_connected

        dpg.configure_item(self._ui.BTN_SCAN, enabled=(not is_recording))
        dpg.configure_item(self._ui.BTN_CONNECT, enabled=(not active_connected and not is_recording))
        dpg.configure_item(self._ui.BTN_PREVIEW, enabled=(not is_idle and not preview_on))
        dpg.configure_item(self._ui.BTN_PAUSE, enabled=preview_on)
        dpg.configure_item(self._ui.BTN_START, enabled=can_record)
        dpg.configure_item(self._ui.BTN_STOP, enabled=is_recording)
        dpg.configure_item(self._ui.SLD_GAIN, enabled=not is_recording)
        dpg.configure_item(self._ui.SLD_EXPOSURE, enabled=not is_recording)

    def _set_rec_status(self, text: str, error: bool = False) -> None:
        # errors are shown in red so they cannot be missed
        # (-255, 0, 0, 255) is DearPyGui's sentinel for "use the theme's default color"
        dpg.set_value(self._ui.REC_STATUS, text)
        dpg.configure_item(self._ui.REC_STATUS, color=(255, 90, 90) if error else (-255, 0, 0, 255))

    # status update (called every frame while streaming)

    def _update_rec_status(self) -> None:
        # refresh the FPS and queue stats shown in the recording panel
        session = self._manager.get_session(self._state.active_cam_id)
        if session is None:
            return
        p = session.pipeline

        acq = p.get_camera_fps()
        dpg.set_value(self._ui.FPS_ACQUISITION, f"{acq:.1f} fps" if acq is not None else "--")
        dpg.set_value(self._ui.FPS_CAM, f"{p.fps_camera:.1f} fps")
        dpg.set_value(self._ui.FPS_PROCESSED, f"{p.fps_processed:.1f} fps")
        dpg.set_value(self._ui.TOTAL_PROCESSED, str(p.total_processed))
        dpg.set_value(self._ui.QUEUE_SAVING, str(p.recording.queue_size))
        dpg.set_value(self._ui.DROPPED_FRAMEs_SAVING, str(p.recording.dropped))

        if self._state.camera_state == CameraState.RECORDING:
            # the writer stops on its own when the frame/duration limit is reached
            # (completed) or on an error like disk full (not completed)
            writer = session.pipeline.writer
            if not writer.is_saving():
                self._on_rec_stop()
                if writer.completed:
                    self._set_rec_status(f"  Recording complete ({writer.accepted} frames)")
                else:
                    self._set_rec_status("  Recording stopped unexpectedly, check files", error=True)
                return
            elapsed = time.time() - self._state.record_start_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._set_rec_status(f"  Recording  {h:02d}:{m:02d}:{s:02d}")

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
        # after the drawlist resizes, update ROI display coordinates to match the new size
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
        if not self._is_over_drawlist(mx, my):
            return
        # mouse_down fires every frame while the button is held — once a drag is
        # in progress, ignore the repeats or the box being dragged over would grab too
        if any(roi.is_dragging() for roi in self._rois.values()):
            return
        # give the click to the topmost (last-drawn) ROI that hits, so overlapping
        # boxes never drag together; the hit ROI becomes the selected one
        hit = None
        for roi in reversed(list(self._rois.values())):
            roi.on_mouse_down(mx, my)
            if roi.is_dragging():
                hit = roi
                break
        for roi in self._rois.values():
            roi.set_selected(roi is hit)  # click on empty area deselects all

    def _on_mouse_move(self, s, a) -> None:
        mx, my = self._local_mouse()
        for roi in self._rois.values():
            roi.on_mouse_move(mx, my)
        if any(roi.is_dragging() for roi in self._rois.values()):
            self._save_rois_to_active()

    def _on_mouse_release(self, s, a) -> None:
        for roi in self._rois.values():
            roi.on_mouse_release()
            roi.set_selected(False)  # selection only shows while the mouse is held
        self._save_rois_to_active()

    # display helpers

    def _push_frame(self, frame) -> None:
        # scale to [0,1] by bit depth and show as-is (no auto-stretch), so screen
        # brightness is the absolute pixel value and matches the fixed color bar
        rgb = to_display_texture(frame / CAMERA_PIXEL_MAX, TEXTURE_W, TEXTURE_H, normalize=False)
        dpg.set_value(self._ui.LIVE_TEXTURE, rgb)

    def _push_plots(self, data: SCOSTimeSeries) -> None:
        t, k2, bfi, cc, od = data.as_lists()
        if not t:
            return
        for i, series in enumerate([k2, bfi, cc, od]):
            dpg.set_value(self._ui.PLOT_SERIES_TAG[i], [t, series])
        # keep the x-axis scrolling so the last _plot_window_sec of data is always visible
        window = self._plot_window_sec
        t_max = max(window, t[-1]) + 0.5
        for x_tag in self._ui.GRAPH_X_TAG:
            dpg.set_axis_limits(x_tag, t_max - window, t_max)

    def _push_k2_maps(self, output: SCOSResult) -> None:
        # update each of the 6 K2 spatial map images in the top panel
        for i, img in enumerate(output.k2_images):
            if img is None:
                continue
            rgb = to_display_texture(img, K2_TEXTURE_W, K2_TEXTURE_H)
            dpg.set_value(self._ui.K2_TEXTURE_TAG[i], rgb)

    # navigation helpers

    def _switch_to(self, cam_id: str) -> None:
        # save the current ROI before switching, then load the new camera's ROI
        self._save_rois_to_active()
        self._state.active_cam_id = cam_id
        session = self._manager.get_session(cam_id)
        if session:
            for name, roi in self._rois.items():
                if name in session.roi_set.names():
                    roi.set_coords_normalized(*session.roi_set.get(name))
        self._sync_dropdown(cam_id)
        self._on_autoscale()
        self._clear_live_feed()
        if session and session.is_connected:
            self._sync_param_sliders(session)

    def _sync_param_sliders(self, session) -> None:
        # show the connected camera's true hardware limits and current values
        gain_lo, gain_hi = session.pipeline.get_gain_range()
        exp_lo, exp_hi = session.pipeline.get_exposure_range()
        dpg.configure_item(self._ui.SLD_GAIN, min_value=gain_lo, max_value=gain_hi)
        dpg.configure_item(self._ui.SLD_EXPOSURE, min_value=exp_lo, max_value=exp_hi)
        dpg.set_value(self._ui.SLD_GAIN,     session.pipeline.get_gain())
        dpg.set_value(self._ui.SLD_EXPOSURE, session.pipeline.get_exposure_time())

    def _clear_live_feed(self) -> None:
        blank = np.zeros(TEXTURE_W * TEXTURE_H * 3, dtype=np.float32)
        dpg.set_value(self._ui.LIVE_TEXTURE, blank)

    def _save_rois_to_active(self) -> None:
        # read normalized coords from the ROI overlay and write them back to session state,
        # then push the updated pixel ROI to the pipeline
        session = self._manager.get_session(self._state.active_cam_id)
        if session:
            for name, roi in self._rois.items():
                session.roi_set.set(name, roi.get_coords_normalized())
            session.sync_pipeline_roi()

    def _rebuild_rec_checkboxes(self, cameras: list[tuple[str, str]]) -> None:
        # clear old checkboxes and create one per camera found in the last scan
        for child in dpg.get_item_children(self._ui.REC_CAM_GROUP, 1):
            dpg.delete_item(child)
        self._state.record_cam_ids = set()
        for serial, display_name in cameras:
            dpg.add_checkbox(
                label=display_name, default_value=False, parent=self._ui.REC_CAM_GROUP,
                tag=self._rec_checkbox_tag(serial),
                user_data=serial, callback=lambda s, a, u: self._on_rec_cam_toggle(u, a)
            )

    @staticmethod
    def _rec_checkbox_tag(serial: str) -> str:
        return f"rec_cb_{serial}"

    def _selected_cam_id(self) -> str | None:
        # reverse-lookup the camera serial from the currently selected dropdown label
        connected = self._manager.connected_ids()
        selected = dpg.get_value(self._ui.DEVICE_DROPDOWN)
        for serial, display_name in self._manager.scan_list:
            display = f"{display_name} (connected)" if serial in connected else display_name
            if display == selected:
                return serial
        return None

    def _sync_dropdown(self, active_cam_id: str) -> None:
        # rebuild dropdown items with "(connected)" suffix where appropriate,
        # then set the selected value to match the active camera
        connected = self._manager.connected_ids()
        names = []
        for serial, display in self._manager.scan_list:
            if serial in connected:
                names.append(f"{display} (connected)")
            else:
                names.append(display)
        dpg.configure_item(self._ui.DEVICE_DROPDOWN, items=names)
        active_display = active_cam_id
        for serial, display in self._manager.scan_list:
            if serial == active_cam_id:
                active_display = display
                break
        label = f"{active_display} (connected)" if active_cam_id in connected else active_display
        dpg.set_value(self._ui.DEVICE_DROPDOWN, label)

    def _local_mouse(self) -> tuple[float, float]:
        # convert global mouse position to coordinates local to the ROI drawlist
        mx, my = dpg.get_mouse_pos(local=False)
        rect_min = dpg.get_item_rect_min(self._ui.ROI_DRAWLIST)
        return mx - rect_min[0], my - rect_min[1]

    def _is_over_drawlist(self, mx: float, my: float) -> bool:
        w = dpg.get_item_width(self._ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self._ui.ROI_DRAWLIST)
        return 0 <= mx <= w and 0 <= my <= h
