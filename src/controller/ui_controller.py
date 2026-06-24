# Central controller that connects the UI, hardware, and state together.
#
# Responsibilities:
#   - Register all button/slider/mouse callbacks at startup
#   - Drive the render loop (update() is called every frame from main.py)
#   - Manage the camera state machine (IDLE -> CONNECTED -> PREVIEWING -> RECORDING)
#   - Push new frames, plots, and K2 maps to the UI
#
# Threading note: all methods here run on the main (UI) thread.
# The pipeline grab and process threads only communicate back via queues.


import time

import cv2
import dearpygui.dearpygui as dpg
import numpy as np
from tkinter import filedialog

from pylsl import StreamInlet, resolve_byprop

from config import (
    TEXTURE_W, TEXTURE_H,
    PLOT_WINDOW_SEC,
    CAMERA_PIXEL_MAX,
    K2_TEXTURE_W, K2_TEXTURE_H,
    ROI_CONFIGS,
)
from controller.camera_manager import CameraManager
from controller.dark_capture_controller import DarkCaptureController
from controller.recording_guard import check as guard_check
from recording.frame_writer import SessionMeta
from controller.roi_selector import ROISelector
from processing.scos_result import SCOSResult
from processing.utils import crop_frame, to_display_texture
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
        self._rois: dict[str, ROISelector] = {}  # one ROISelector per ROI name (source, detector)

        # callback so dark controller can update the path field in the main UI after saving
        self._dark_ctrl = DarkCaptureController(
            manager, app_state,
            lambda p: dpg.set_value(self._ui.INP_DARKPATH, p),
        )

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
        dpg.set_item_callback(self._ui.BTN_START, self._on_rec_start)
        dpg.set_item_callback(self._ui.BTN_STOP, self._on_rec_stop)
        dpg.set_item_callback(self._ui.BTN_AUTOSCALE, self._on_autoscale)
        dpg.set_item_callback(self._ui.DEVICE_DROPDOWN, self._on_dropdown_change)
        dpg.set_item_callback(self._ui.SLD_GAIN, self._on_gain_change)
        dpg.set_item_callback(self._ui.SLD_EXPOSURE, self._on_exposure_change)
        dpg.set_item_callback(self._ui.BTN_REC_BROWSE, self._on_rec_browse)
        dpg.set_item_callback(self._ui.BTN_DARKIMG, self._on_dark_open)
        dpg.set_item_callback(self._ui.BTN_DARKBROWSE, self._on_dark_browse)
        dpg.set_item_callback(self._ui.BTN_DARKCLEAR, self._on_dark_clear)
        dpg.set_item_callback(self._ui.BTN_TRIGGER_CONNECT, self._on_trigger_connect)

        self._dark_ctrl.setup()
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

            result = session.pipeline.get_latest()
            if result is None:
                continue

            full_frame, output = result
            session.last_frame = full_frame  # store for dark capture preview

            # t is time since preview/recording started, used as the x-axis in plots
            t = time.time() - session.data.start_time
            session.data.push(t, output)

            # feed frames to dark capture controller if a capture is in progress
            if self._dark_ctrl.is_capturing_for(cam_id):
                self._dark_ctrl.feed_frame(cam_id, full_frame)

        # update dark capture window thumbnails if it is open
        self._dark_ctrl.update_ui()

        # only push display data for the camera currently selected in the dropdown
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
        # scan for connected cameras, rebuild the dropdown and checkboxes, reset state
        cameras = self._manager.scan()  # returns list of (serial, display_name)
        if not cameras:
            return
        self._rebuild_rec_checkboxes(cameras)
        self._switch_to(cameras[0][0])  # default to first camera found
        self._state.camera_state = CameraState.IDLE
        self._on_trigger_scan()
        self.sync_ui()

    def _on_trigger_scan(self) -> None:
        # placeholder: scan for available trigger sources and populate the trigger dropdown
        # Vu please create a scan button for this function
        streams = resolve_byprop("type", "Markers") # this will run until you find some streams
        # Vu please populate the dropdown with the streams, here is one example with the first name populated
        populate_dropdown(streams[0].name())
        
        

    def _on_trigger_connect(self) -> None:
        # create a new inlet to read from the stream
        inlet = StreamInlet(streams[0]) # Vu here I assumed the use selected the first stream but we need to listen to what the user select
        # for preview:
        while True:
            sample, timestamp = inlet.pull_sample()
            print("got %s at time %s" % (sample[0], timestamp))
        # for save/start:
        # once we press the start button, start button function should also listen to the sample but not the timestamp here. the Start button should have its own timestamp for saving the images and we should use those timestamps for each sample value, and save it in a two column table, first col is timestamp and second col is sample string 
        # something like this in start function: sample = inlet.pull_sample(); add_row_to_table(trigger_table, current_time_stamp, sample)
        pass

    def _on_trigger_received(self) -> None:
        # placeholder: called when a trigger signal arrives to start recording automatically
        # self._on_rec_start()
        # i don't think we need this function
        pass

    def _on_connect(self) -> None:
        cam_id = self._selected_cam_id()
        if not cam_id:
            return
        session = self._manager.connect(cam_id)
        if session is None:
            return
        # push the current ROI to the pipeline so it is ready before preview starts
        session.sync_pipeline_roi()
        self._sync_dropdown(cam_id)
        # only advance to CONNECTED if we are still in IDLE, do not override PREVIEWING or RECORDING
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
        # start live feed for all connected cameras and reset their data buffers
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
        # open the dark capture window for all currently connected cameras
        connected = self._manager.connected_ids()
        if not connected:
            return
        self._dark_ctrl.open(connected)

    def _on_dark_browse(self) -> None:
        # load a previously saved dark image from disk and apply it to the active camera
        # the file must be full sensor resolution (CAMERA_W x CAMERA_H) so it can be
        # cropped to the current ROI here
        path = filedialog.askopenfilename(
            title="Load dark image",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return
        session = self._manager.get_session(self._state.active_cam_id)
        if session is None:
            return
        roi = session.roi_set.to_pixels("source")
        roi_h, roi_w = roi[3] - roi[1], roi[2] - roi[0]
        cropped = crop_frame(img, roi)
        if cropped.shape != (roi_h, roi_w):
            # image is not full resolution or ROI is out of bounds, skip silently
            print(f"[DarkBrowse] bad image size {img.shape[1]}x{img.shape[0]}, skipping")
            return
        dpg.set_value(self._ui.INP_DARKPATH, path)
        session.dark_image = cropped.astype(np.float32)

    def _on_rec_start(self) -> None:
        study_name = dpg.get_value(self._ui.INPUT_STUDY).strip()
        subject_id = dpg.get_value(self._ui.INPUT_SUBJECT).strip()
        if not study_name or not subject_id:
            dpg.set_value(self._ui.REC_STATUS, "  Study Name and Subject ID required")
            return

        folder = dpg.get_value(self._ui.INP_REC_FOLDER) or "./data"
        interval_ms = float(dpg.get_value(self._ui.INP_REC_INTERVAL))
        buffer_size = int(dpg.get_value(self._ui.INP_REC_BUFFER))
        run_number = dpg.get_value(self._ui.INPUT_RUN)

        session_meta = SessionMeta(
            study_name=study_name,
            subject_id=subject_id,
            run_number=run_number,
            output_folder=folder,
            interval_ms=interval_ms,
            buffer_size=buffer_size,
        )

        # run pre-flight checks before starting, block on errors, print warnings
        result = guard_check(self._manager, self._state, session_meta)
        if not result.ok:
            dpg.set_value(self._ui.REC_STATUS, f"  {result.errors[0]}")
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
                session.pipeline.start_recording(session_meta)

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
        # fit the y-axis of every plot to its current data range
        for tag in self._ui.GRAPH_TAG:
            y_tag = dpg.get_item_children(tag, 1)[1]
            dpg.fit_axis_data(y_tag)

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
        self._state.camera_state = CameraState.IDLE
        dpg.set_value(self._ui.REC_STATUS, "  Camera error, please rescan")
        self.sync_ui()

    # state machine

    def sync_ui(self) -> None:
        # enable or disable buttons based on the current camera state
        # this is called after every state change so the UI always matches reality
        state = self._state.camera_state
        has_cameras = len(self._state.record_cam_ids) > 0

        is_idle = (state == CameraState.IDLE)
        is_connected = (state == CameraState.CONNECTED)
        is_previewing = (state == CameraState.PREVIEWING)
        is_recording = (state == CameraState.RECORDING)

        # recording requires at least one camera checkbox checked and live preview running
        can_record = (is_previewing and has_cameras)

        # connect button state depends on the currently selected camera in the dropdown
        active_session = self._manager.get_session(self._state.active_cam_id)
        active_connected = active_session is not None and active_session.is_connected

        dpg.configure_item(self._ui.BTN_SCAN, enabled=(not is_recording))
        dpg.configure_item(self._ui.BTN_CONNECT, enabled=(not active_connected and not is_recording))
        dpg.configure_item(self._ui.BTN_PREVIEW, enabled=is_connected)
        dpg.configure_item(self._ui.BTN_START, enabled=can_record)
        dpg.configure_item(self._ui.BTN_STOP, enabled=is_recording)
        dpg.configure_item(self._ui.BTN_DARKIMG, enabled=(not is_idle))
        dpg.configure_item(self._ui.BTN_DARKBROWSE, enabled=not is_recording)
        dpg.configure_item(self._ui.BTN_DARKCLEAR, enabled=not is_recording)
        dpg.configure_item(self._ui.SLD_GAIN, enabled=not is_recording)
        dpg.configure_item(self._ui.SLD_EXPOSURE, enabled=not is_recording)

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
            # if the writer stopped on its own (e.g. disk full), auto-stop and warn
            if not session.pipeline.writer.is_saving():
                self._on_rec_stop()
                dpg.set_value(self._ui.REC_STATUS, "  Recording stopped unexpectedly, check files")
                return
            elapsed = time.time() - self._state.record_start_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            dpg.set_value(self._ui.REC_STATUS, f"  Recording  {h:02d}:{m:02d}:{s:02d}")

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

    def _on_dark_clear(self) -> None:
        session = self._manager.get_session(self._state.active_cam_id)
        if session is None:
            return
        session.dark_image = None
        dpg.set_value(self._ui.INP_DARKPATH, "")

    def _on_mouse_down(self, s, a) -> None:
        if self._state.camera_state == CameraState.RECORDING:
            return
        session = self._manager.get_session(self._state.active_cam_id)
        if session and session.dark_image is not None:
            return  # ROI is locked while a dark image is applied to prevent shape mismatch
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
        # normalize to [0,1] then convert to flat RGB float32 for the DearPyGUI texture
        rgb = to_display_texture(frame / CAMERA_PIXEL_MAX, TEXTURE_W, TEXTURE_H)
        dpg.set_value(self._ui.LIVE_TEXTURE, rgb)

    def _push_plots(self, data: SCOSTimeSeries) -> None:
        t, k2, bfi, cc, od = data.as_lists()
        if not t:
            return
        for i, series in enumerate([k2, bfi, cc, od]):
            dpg.set_value(self._ui.PLOT_SERIES_TAG[i], [t, series])
        # keep the x-axis scrolling so the last PLOT_WINDOW_SEC of data is always visible
        t_max = max(PLOT_WINDOW_SEC, t[-1]) + 0.5
        for x_tag in self._ui.GRAPH_X_TAG:
            dpg.set_axis_limits(x_tag, t_max - PLOT_WINDOW_SEC, t_max)

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
                user_data=serial, callback=lambda s, a, u: self._on_rec_cam_toggle(u, a)
            )

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
