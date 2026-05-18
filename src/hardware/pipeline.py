# Two-thread pipeline:
#   _grab_loop    — grabs every frame (OneByOne), timestamps it, feeds FrameWriter + _process_queue
#   _process_loop — drains _process_queue, runs Processor, feeds display _queue
#
# _process_queue maxsize=1: display always gets the most recent frame, stale ones are dropped.
# FrameWriter receives every grabbed frame before any processing happens.

import queue
import threading
import time

import numpy as np

from config import DARK_IMAGE_PATH, CAMERA_PIXEL_FORMAT, CAMERA_W, CAMERA_H
from hardware.base_camera import BaseCamera
from processing.processor import Processor
from processing.utils import crop_frame
from recording.frame_writer import FrameWriter, FrameRecord, RecordingMeta


class Pipeline:

    def __init__(self, camera: BaseCamera):
        self._camera = camera

        self._queue = queue.Queue(maxsize=1)  # display: (full_frame, SCOSResult)
        self._process_queue = queue.Queue(maxsize=1)  # grab → process thread

        self._grab_thread: threading.Thread | None = None
        self._process_thread: threading.Thread | None = None
        self._running = False

        self._processor = Processor()
        self._roi_pixels: tuple | None      = None
        self._dark_image: np.ndarray | None = None

        self.writer  = FrameWriter()
        self._grab_index: int = 0

        self.crashed: bool = False

        # FPS stats — updated every 2 s, readable by the UI
        self.fps_camera: float = 0.0
        self.fps_processed: float = 0.0
        self.total_processed: int = 0
        self.drop_processed: int = 0

        self._grabbed = 0
        self._processed = 0
        self._log_time = 0.0
        self._start_time = 0.0

    # lifecycle 
    def start(self) -> None:
        if self._running:
            return
        self._camera.open()
        self._running = True
        self._grab_thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._grab_thread.start()
        self._process_thread.start()
        if DARK_IMAGE_PATH:
            self.load_dark_image_from_file(DARK_IMAGE_PATH)

    def stop(self) -> None:
        self._running = False
        self._camera.close()
        if self._grab_thread:
            self._grab_thread.join(timeout=3.0)
            self._grab_thread = None
        if self._process_thread:
            self._process_thread.join(timeout=3.0)
            self._process_thread = None
        self.writer.stop()

    # public API 
    def get_latest(self):
        # Non-blocking. Returns (full_frame, SCOSResult) or None. Call from UI thread
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def set_roi(self, roi_pixels: tuple | None) -> None:
        self._roi_pixels = roi_pixels

    def set_dark_image(self, img: np.ndarray | None) -> None:
        # Pass a full-frame dark image array for subtraction. None disables subtraction
        self._dark_image = img.astype(np.float64) if img is not None else None

    def load_dark_image_from_file(self, path: str) -> None:
        import cv2
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            self.set_dark_image(img)
            print(f"[Pipeline] dark image loaded: {path}")
        else:
            print(f"[Pipeline] dark image not found: {path}")

    def reset_processor(self) -> None:
        # Reset all processing state - call when starting a new recording session.
        self._processor.reset()

    def get_camera_fps(self) -> float | None:
        # Camera-reported FPS from hardware node. None if unavailable
        return self._camera.get_fps()

    def set_gain(self, value: float) -> None:
        self._camera.set_gain(value)

    def set_exposure_time(self, value: float) -> None:
        self._camera.set_exposure_time(value)

    # RECORDING
    def start_recording(
        self,
        output_folder: str,
        cam_id: str = "cam",
        interval_ms: float = 0.0,
        buffer_size: int = 500,
        study_name: str = "",
        subject_id: str = "",
        run_number: str = "",
    ) -> None:
        meta = RecordingMeta(
            study_name=study_name,
            subject_id=subject_id,
            run_number=run_number,
            camera_id=cam_id,
            gain_db=self._camera.get_gain(),
            exposure_us=self._camera.get_exposure_time(),
            pixel_format=CAMERA_PIXEL_FORMAT,
            tick_frequency_hz=self._camera.get_tick_frequency_hz(),
            interval_ms=interval_ms,
            camera_time_enabled=self._camera.has_camera_time(),
            exp_end_time_enabled=self._camera.has_exp_end_time(),
            frame_counter_enabled=self._camera.has_frame_counter(),
            pc_start_time_unix=time.time(),
        )
        self.writer.start(output_folder, meta, buffer_size)

    def stop_recording(self) -> None:
        self.writer.stop()

    @property
    def recording(self) -> "FrameWriter":
        """Expose writer stats to the UI."""
        return self.writer

    # grab thread
    def _grab_loop(self) -> None:
        self._start_time = self._log_time = time.time()
        while self._running:
            try:
                result = self._camera.grab_frame()
                if result is None:
                    continue

                frame, cam_ts, frame_counter, exp_end_ts = result
                host_ts = time.time()
                self._grabbed += 1
                self._grab_index += 1

                # record before processing — every frame, lowest latency
                self.writer.push_frame(FrameRecord(
                    frame=frame,
                    grab_index=self._grab_index,
                    pc_time=host_ts,
                    camera_time=cam_ts,
                    exp_end_time=exp_end_ts,
                    frame_counter=frame_counter,
                ))

                # replace stale frame — process thread always gets the latest
                try:
                    self._process_queue.get_nowait()
                    self.drop_processed += 1
                except queue.Empty:
                    pass
                self._process_queue.put_nowait((frame, host_ts))

                self._update_stats()

            except Exception as e:
                if self._running:  # ignore exceptions caused by intentional camera.close() in stop()
                    print(f"[Pipeline._grab_loop] {e}")
                    self.crashed = True
                    self._running = False

    # process thread 
    def _process_loop(self) -> None:
        while self._running:
            try:
                item = self._process_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                frame, _ts = item

                # snapshot shared state to avoid race with UI thread calling set_roi/set_dark_image
                roi = self._roi_pixels
                dark = self._dark_image

                if roi:
                    cropped = crop_frame(frame, roi)
                    dark_cropped = crop_frame(dark, roi) if dark is not None else None
                else:
                    cropped = frame
                    dark_cropped = dark

                output = self._processor.process(cropped, dark_cropped)
                self._processed += 1
                self.total_processed += 1

                # replace stale display result - UI always gets the latest
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._queue.put_nowait((frame, output))

            except Exception as e:
                print(f"[Pipeline._process_loop] {e}")
                self.crashed = True
                self._running = False

    # stats 

    def _update_stats(self) -> None:
        now = time.time()
        interval = now - self._log_time
        if interval < 2.0:
            return

        self.fps_camera = self._grabbed / interval
        self.fps_processed = self._processed / interval

        print(
            f"[Pipeline] t={now - self._start_time:.1f}s | "
            f"camera: {self.fps_camera:.1f} fps | "
            f"processed: {self.fps_processed:.1f} fps | "
            f"total: {self.total_processed} | "
            f"dropped: {self.drop_processed}"
        )

        self._grabbed = self._processed = 0
        self._log_time = now
