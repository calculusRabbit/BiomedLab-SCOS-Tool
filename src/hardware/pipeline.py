# Manages two background threads for one camera.
#
#   _grab_loop    — grabs every frame from the camera, timestamps it, sends to FrameWriter and _process_queue
#   _process_loop — pulls frames from _process_queue, runs the SCOS processor, puts result in _queue for the UI
#
# _process_queue has maxsize=1 so if processing is slower than grabbing, stale frames are dropped
# and the display always shows the most recent frame.
#
# FrameWriter receives every grabbed frame before processing so no frames are missed in the recording,
# even if the processor is falling behind.

import queue
import threading
import time

import numpy as np

from config import CAMERA_PIXEL_FORMAT, CAMERA_W, CAMERA_H
from hardware.base_camera import BaseCamera
from processing.processor import Processor
from processing.utils import crop_frame
from recording.frame_writer import FrameWriter, FrameRecord, SessionMeta, CameraMeta


class Pipeline:
    """Runs the grab and process threads for one camera and exposes results to the UI."""

    def __init__(self, camera: BaseCamera):
        self._camera = camera

        self._queue = queue.Queue(maxsize=1) # display queue: holds (full_frame, SCOSResult)
        self._process_queue = queue.Queue(maxsize=1)  # passes frames from grab thread to process thread

        self._grab_thread: threading.Thread | None = None
        self._process_thread: threading.Thread | None = None
        self._running = False

        self._processor = Processor()
        self._reset_requested: bool = False
        self._roi_pixels: tuple | None = None
        self._processing_enabled = False  # off until Preview is pressed; toggled via set_processing()

        # most recent grabbed frame, updated by the grab thread on every grab
        # (plain reference assignment, GIL-safe) — lets the UI show the live
        # image even while SCOS processing is paused
        self.latest_frame: np.ndarray | None = None

        self.writer = FrameWriter()

        self.crashed: bool = False  # set to True if a thread dies unexpectedly, UI polls this

        # FPS stats, updated every 2 seconds and read by the UI status panel
        self.fps_camera: float = 0.0
        self.fps_processed: float = 0.0
        self.total_processed: int = 0
        self.drop_processed: int = 0

        self._grabbed = 0    # frame count since last stats update
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

    def stop(self) -> None:
        # set flag first so threads know to exit, then close the camera
        # closing the camera causes grab_frame() to throw, which is caught and ignored
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
        # non-blocking, returns (full_frame, SCOSResult) or None, call from UI thread only
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def set_roi(self, roi_pixels: tuple | None) -> None:
        self._roi_pixels = roi_pixels

    def set_processing(self, enabled: bool) -> None:
        # turn SCOS processing on/off (Preview/Pause) — grabbing and recording
        # are unaffected, the grab loop just stops feeding the process thread
        self._processing_enabled = enabled

    def reset_processor(self) -> None:
        # sets a flag that the process thread checks at the start of its next iteration
        self._reset_requested = True

    def get_camera_fps(self) -> float | None:
        # hardware-reported FPS from the camera driver, None if not supported
        return self._camera.get_fps()

    def get_gain(self) -> float:
        return self._camera.get_gain()

    def set_gain(self, value: float) -> None:
        self._camera.set_gain(value)

    def get_exposure_time(self) -> float:
        return self._camera.get_exposure_time()

    def set_exposure_time(self, value: float) -> None:
        self._camera.set_exposure_time(value)

    # recording

    def start_recording(self, session_meta: SessionMeta) -> None:
        # collect per-camera metadata at the moment recording starts, then hand off to FrameWriter
        camera_meta = CameraMeta(
            camera_serial=self._camera.get_serial(),
            camera_model=self._camera.get_model(),
            gain_db=self._camera.get_gain(),
            exposure_us=self._camera.get_exposure_time(),
            pixel_format=CAMERA_PIXEL_FORMAT,
            tick_frequency_hz=self._camera.get_tick_frequency_hz(),
            pc_start_time_unix=time.time(),
        )
        self.writer.start(session_meta, camera_meta)

    def stop_recording(self) -> None:
        self.writer.stop()

    @property
    def recording(self) -> "FrameWriter":
        # exposes writer stats (queue size, dropped frames) to the UI status panel
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
                self.latest_frame = frame

                # send the FULL frame to FrameWriter before processing so every frame
                # is recorded, even if the process thread is backed up
                # (recordings are always full sensor size, ROI only affects SCOS math)
                self.writer.push_frame(FrameRecord(
                    frame=frame,
                    pc_time=host_ts,
                    camera_time=cam_ts,
                    frame_counter=frame_counter,
                ))

                # drop the previous frame if the process thread hasn't picked it up yet,
                # so processing always works on the most recent frame
                if self._processing_enabled:
                    try:
                        self._process_queue.get_nowait()
                        self.drop_processed += 1
                    except queue.Empty:
                        pass
                    self._process_queue.put_nowait((frame, host_ts))

                self._update_stats()

            except Exception as e:
                if self._running:  # suppress errors caused by camera.close() during a normal stop()
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

            # apply a processor reset if one was requested by the UI thread
            if self._reset_requested:
                self._processor.reset()
                self._reset_requested = False

            try:
                frame, _ts = item

                # snapshot roi into a local var to avoid a race condition
                # with the UI thread calling set_roi() mid-frame
                roi = self._roi_pixels

                cropped = crop_frame(frame, roi) if roi else frame
                output = self._processor.process(cropped)
                self._processed += 1
                self.total_processed += 1

                # drop the previous result if the UI thread hasn't read it yet
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
        # recalculate FPS every 2 seconds and print to console
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
