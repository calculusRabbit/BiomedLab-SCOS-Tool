# controller/callbacks.py
import time

import cv2
import dearpygui.dearpygui as dpg
import numpy as np

from config import TEXTURE_W, TEXTURE_H, PLOT_WINDOW_SEC, CAMERA_PIXEL_MAX
from controller.roi_selector import ROISelector


class SCOSController:
    # Wire UI events to the camera manager and drives the render loop
    # One instance own the single ROI selector and the current active camera

    def __init__(self, ui, manager):
        self.ui = ui
        self.manager = manager

        self._active_cam_id = None # which camera is shown on screen right now
        self._is_running = False # true = preview or recording in progress
        self._last_size = (0, 0)    # track viewport size to resize
        self._roi = None    # the draggable ROI box/rectangle

    def setup_callbacks(self):
        # create ROI rectangle
        self._roi = ROISelector(
            self.ui.ROI_DRAWLIST,
            dpg.get_item_width(self.ui.ROI_DRAWLIST),
            dpg.get_item_height(self.ui.ROI_DRAWLIST),
        )

        # these for any mouse event anywhere in the window
        # the callbacks for check if the mouse if over the ROI box
        with dpg.handler_registry():
            dpg.add_mouse_down_handler(callback=self._on_mouse_down)
            dpg.add_mouse_move_handler(callback=self._on_mouse_move)
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)

        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.set_item_callback(self.ui.BTN_SCAN, self._on_scan)
        dpg.set_item_callback(self.ui.BTN_CONNECT, self._on_connect)
        dpg.set_item_callback(self.ui.BTN_PREVIEW, self._on_preview)
        dpg.set_item_callback(self.ui.BTN_STOP, self._on_stop)
        dpg.set_item_callback(self.ui.BTN_AUTOSCALE, self._on_autoscale)
        dpg.set_item_callback(self.ui.DEVICE_DROPDOWN, self._on_dropdown_change)


    def shutdown(self):
        self.manager.stop_all()


    # main loop 
    def update(self):
        # called every frame - pull lastest data from all CONNECTED CAMERAS
        for cam_id in self.manager.connected_ids():
            session = self.manager.get_session(cam_id)

            # tell the pipeline where to crop before processing
            session.pipeline.roi_pixels = self.manager.roi_to_pixels(session)

            result = session.pipeline.get_latest()
            if result is None:
                continue # no new frame yet
            
            full_frame, output = result
            session.last_frame = full_frame

            t = time.time() - session.start_time
            session.t_buf.append(t)
            session.k2_buf.append(output.k2)
            session.bfi_buf.append(output.bfi)
            session.cc_buf.append(output.cc)
            session.od_buf.append(output.od)

        # only the active camera updates the display and plots
        active = self.manager.get_session(self._active_cam_id)
        if active is None:
            return
        if active.last_frame is not None:
            self._push_frame(active.last_frame) # camera connected and running

        if self._is_running and active.t_buf:
            self._push_plots(active)
            self._push_k2_images()


    # callbacks
    def _on_scan(self):
        # find all cameras and auto-switch to the first one
        names = self.manager.scan()
        if not names:
            return
        self._refresh_dropdown()
        self._switch_to(names[0])


    def _on_connect(self):
        # start the pipeline for the selected camera
        # and start display image from camera
        cam_id = self._selected_cam_id()
        if not cam_id:
            return
        self.manager.connect(cam_id)
        self._refresh_dropdown()
        connected = self.manager.connected_ids()
        display = f"{cam_id} (connected)" if cam_id in connected else cam_id
        dpg.set_value(self.ui.DEVICE_DROPDOWN, display)
        


    def _on_dropdown_change(self):
        # user picked a differnt camera from the Cameras dropdown
        cam_id = self._selected_cam_id()
        if cam_id and cam_id != self._active_cam_id:
            self._switch_to(cam_id)


    def _on_preview(self):
        if not self.manager.connected_ids():
            return
        now = time.time()
        for cam_id in self.manager.connected_ids():
            session = self.manager.get_session(cam_id)
            session.start_time = now
            session.clear_buffers()
        self._is_running = True


    def _on_stop(self):
        self._is_running = False


    def _on_autoscale(self):
        # fit all Y axes to whatever data is currently on screen
        for tag in self.ui.GRAPH_TAG:
            y_tag = dpg.get_item_children(tag, 1)[1]
            dpg.fit_axis_data(y_tag)


    # resize 
    def _on_resize(self):
        # reflow the layout and rescale the ROI rectangle to fit the new size
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if (w, h) == self._last_size or w <= 0 or h <= 0:
            return
        self._last_size = (w, h)
        self.ui.resize(w, h)
        self._roi.update_display_size(
            dpg.get_item_width(self.ui.ROI_DRAWLIST),
            dpg.get_item_height(self.ui.ROI_DRAWLIST),
        )
        self._save_roi_to_active_session()


    # mouse event
    def _on_mouse_down(self, s, a):
        if self._over_drawlist():
            mx, my = self._local_mouse()
            self._roi.on_mouse_down(mx, my)


    def _on_mouse_move(self, s, a):
        mx, my = self._local_mouse()
        self._roi.on_mouse_move(mx, my)
        # save the updated ROI position every move so the pipeline stays in sync
        self._save_roi_to_active_session()


    def _on_mouse_release(self, s, a):
        self._roi.on_mouse_release()


    # helpers
    def _selected_cam_id(self):
        # get the raw cam_id from the dropdown's current selection
        # using index lookup
        scan_list = self.manager._scan_list #Get the raw list of camera IDs from the manager,
        if not scan_list:
            return None
        display_names = self._display_names()
        selected = dpg.get_value(self.ui.DEVICE_DROPDOWN)
        if selected in display_names:
            return scan_list[display_names.index(selected)]
        return None


    def _display_names(self):
        # connected cameras get "(connected)" appended to their name
        connected = self.manager.connected_ids()
        return [
            f"{name} (connected)" if name in connected else name
            for name in self.manager._scan_list
        ]


    def _refresh_dropdown(self):
        dpg.configure_item(self.ui.DEVICE_DROPDOWN, items=self._display_names())


    def _switch_to(self, cam_id):
        # save current ROI, swap active camera, restore that camera's saved ROI
        self._save_roi_to_active_session()
        self._active_cam_id = cam_id
        session = self.manager.get_session(cam_id)
        if session:
            self._roi.set_coords_normalized(*session.roi_norm)
        self._refresh_dropdown()
        connected = self.manager.connected_ids()
        display = f"{cam_id} (connected)" if cam_id in connected else cam_id
        dpg.set_value(self.ui.DEVICE_DROPDOWN, display)
        self._on_autoscale()


    def _save_roi_to_active_session(self):
        # snapshot the ROI into the session
        session = self.manager.get_session(self._active_cam_id)
        if session:
            session.roi_norm = self._roi.get_coords_normalized()


    def _local_mouse(self):
        # convert global mouse position to coords relative to the drawlist
        mx, my = dpg.get_mouse_pos(local=False)
        rect_min = dpg.get_item_rect_min(self.ui.ROI_DRAWLIST)
        return mx - rect_min[0], my - rect_min[1]


    def _over_drawlist(self):
        # To check whether the mouse currently inside the ROI drawlist
        mx, my = self._local_mouse()
        w = dpg.get_item_width(self.ui.ROI_DRAWLIST)
        h = dpg.get_item_height(self.ui.ROI_DRAWLIST)
        return 0 <= mx <= w and 0 <= my <= h


    def _clear_display(self):
        # blank out the live image and all plots
        blank = np.zeros(TEXTURE_W * TEXTURE_H * 3, dtype=np.float32)
        dpg.set_value(self.ui.LIVE_TEXTURE, blank)
        for tag in self.ui.PLOT_SERIES_TAG:
            dpg.set_value(tag, [[], []])


    def _push_frame(self, frame):
        if frame.shape[:2] != (TEXTURE_H, TEXTURE_W):
            frame = cv2.resize(frame, (TEXTURE_W, TEXTURE_H))
        # convert grayscale (H,W) into float normalized to 0.0-1.0 because dpg only take this type
        norm = frame.astype(np.float32) / CAMERA_PIXEL_MAX
        # DPG raw texture requires RGB float format - stack grayscale into 3 channels
        # shape: (H, W) => (H, W, 3) => flatten to 1D for dpg.set_value
        rgb = np.repeat(norm[:, :, np.newaxis], 3, axis=2).flatten()
        # update live image
        dpg.set_value(self.ui.LIVE_TEXTURE, rgb)


    def _push_plots(self, session):
        times = list(session.t_buf)
        for i, buf in enumerate([session.k2_buf, session.bfi_buf,
                                  session.cc_buf, session.od_buf]):
            dpg.set_value(self.ui.PLOT_SERIES_TAG[i], [times, list(buf)])
        t_max = max(PLOT_WINDOW_SEC, times[-1]) + 0.5
        t_min = t_max - PLOT_WINDOW_SEC
        for x_tag in self.ui.GRAPH_X_TAG:
            dpg.set_axis_limits(x_tag, t_min, t_max)


    def _push_k2_images(self, output):
        for i, img in enumerate(output.k2_images):
            if img is None:
                continue
            # resize to fixed texture size — ROI can be any size but texture is always fixed
            img_resized = cv2.resize(img.astype(np.float32), (K2_TEXTURE_W, K2_TEXTURE_H))
            # normalize to 0.0-1.0 for DPG texture
            mn, mx = img_resized.min(), img_resized.max()
            if mx > mn:
                img_resized = (img_resized - mn) / (mx - mn)
            # expand grayscale to RGB and flatten for dpg.set_value
            rgb = np.repeat(img_resized[:, :, np.newaxis], 3, axis=2).flatten()
            dpg.set_value(self.ui.K2_TEXTURE_TAG[i], rgb)