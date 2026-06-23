# Writes grabbed frames to an HDF5 file on a background thread.
#
# HDF5 layout per recording file:
#   attrs:          study_name, subject_id, run_number, camera_id, gain_db,
#                   exposure_us, pixel_format, tick_frequency_hz,
#                   pc_start_time_unix, pc_end_time_unix, interval_ms
#   frames          (N, H, W) uint8   ROI-cropped raw frames
#   pc_time         (N,)      float64 PC wall-clock time at grab (seconds)
#   camera_time     (N,)      int64   hardware timestamp in ticks (-1 if unavailable)
#   frame_counter   (N,)      int64   hardware frame ID (-1 if unavailable)
#   dark_image      (H, W)    float32 dark image used during this recording (optional)
#
# Datasets are pre-allocated and resized down to the actual frame count on close.

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from processing.utils import safe_filename


@dataclass
class WriteBuffers:
    frame_buf: np.ndarray
    pc_time_buf: np.ndarray
    camera_time_buf: np.ndarray
    frame_counter_buf: np.ndarray


@dataclass
class FrameRecord:
    frame: np.ndarray
    pc_time: float  # time.time() at grab — wall clock
    camera_time: int | None  # ChunkTimestamp ticks — hardware clock
    frame_counter: int | None # ChunkFrameID — detect dropped frames


@dataclass
class SessionMeta:
    # global — one per recording session, same for all cameras
    study_name: str
    subject_id: str
    run_number: str
    output_folder: str
    interval_ms: float   # 0 = every frame
    buffer_size: int


@dataclass
class CameraMeta:
    # per-camera — unique to each physical camera
    camera_serial: str
    camera_model: str
    gain_db: float
    exposure_us: float
    pixel_format: str
    tick_frequency_hz: int | None
    pc_start_time_unix: float


CHUNK = 128
INITIAL_ALLOC = 50000
RESIZE_STEP = 10000


class FrameWriter:
    # Receives frames from the grab thread and writes them to an HDF5 file.

    # Runs on a non-daemon thread so the file is always finalized properly
    # even if the app is closed while recording is active.
    # Frames are queued and flushed in batches of CHUNK frames for efficiency.

    def __init__(self):
        self.queue = queue.Queue(maxsize=512)
        self.thread = None
        self.running = False
        self.dropped_frames = 0

        self.session_meta: SessionMeta | None = None
        self.camera_meta: CameraMeta | None = None
        self.output_folder: Path | None = None
        self._dark_image: np.ndarray | None = None
        self.interval_ms = 0.0
        self.tick_freq_hz = None
        self.last_cam_ts = 0
        self.last_pc_ts = 0.0
        self.write_pos = 0
        self.allocated = 0

    # public API

    @property
    def queue_size(self):
        return self.queue.qsize()

    @property
    def dropped(self):
        return self.dropped_frames

    def is_saving(self):
        return self.running

    def start(self, session_meta: SessionMeta, camera_meta: CameraMeta,
              dark_image: np.ndarray | None = None) -> None:
        if self.running:
            return

        self.session_meta = session_meta
        self.camera_meta = camera_meta
        self._dark_image = dark_image

        self.output_folder = Path(session_meta.output_folder) / session_meta.study_name / session_meta.subject_id
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self.interval_ms = session_meta.interval_ms
        self.tick_freq_hz = camera_meta.tick_frequency_hz
        self.last_cam_ts = 0
        self.last_pc_ts = 0.0
        self.dropped_frames = 0

        self.queue = queue.Queue(maxsize=session_meta.buffer_size)
        self.running = True
        self.thread = threading.Thread(target=self.write_loop, daemon=False)
        self.thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.queue.put(None)
        if self.thread:
            self.thread.join(timeout=10.0)
            if self.thread.is_alive():
                print("[FrameWriter] warning: write thread did not exit cleanly")
            self.thread = None
        print("[FrameWriter] stopped")

    def push_frame(self, record: FrameRecord) -> None:
        if not self.running:
            return

        if self.interval_ms > 0:
            if record.camera_time is not None and self.tick_freq_hz is not None:
                time_since_last_frame_ms = (record.camera_time - self.last_cam_ts) * (1000 / self.tick_freq_hz)
            else:
                time_since_last_frame_ms = (record.pc_time - self.last_pc_ts) * 1000

            if time_since_last_frame_ms < self.interval_ms:
                return

        self.last_cam_ts = record.camera_time if record.camera_time is not None else 0
        self.last_pc_ts = record.pc_time

        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped_frames += 1

    # write thread

    def wait_for_first_frame(self) -> FrameRecord | None:
        while True:
            try:
                first = self.queue.get(timeout=0.1)
                break
            except queue.Empty:
                if not self.running:
                    return None
        return first

    def write_loop(self):
        first = self.wait_for_first_frame()
        if first is None:
            return

        frame_shape = first.frame.shape
        frame_dtype = first.frame.dtype

        h, w = frame_shape
        bufs = WriteBuffers(
            frame_buf = np.empty((CHUNK, h, w), dtype=frame_dtype),
            pc_time_buf = np.empty(CHUNK, dtype="float64"),
            camera_time_buf = np.empty(CHUNK, dtype="int64"),
            frame_counter_buf = np.empty(CHUNK, dtype="int64"),
        )

        batch = []
        try:
            file, ds = self.open_file(frame_shape, frame_dtype)
        except Exception as e:
            print(f"[FrameWriter] failed to open file: {e}")
            self.running = False
            return

        try:
            while True:
                try:
                    item = self.queue.get(timeout=0.1)
                except queue.Empty:
                    if not self.running:
                        if batch:
                            self.flush(file, ds, batch, bufs)
                        break
                    continue

                if item is None:
                    if batch:
                        self.flush(file, ds, batch, bufs)
                    break

                batch.append(item)

                if len(batch) >= CHUNK:
                    self.flush(file, ds, batch, bufs)
                    batch = []

        except Exception as e:
            print(f"[FrameWriter] write error: {e}")
            self.running = False
        finally:
            self.close_file(file, ds)

    def open_file(self, frame_shape, frame_dtype):
        self.write_pos = 0
        self.allocated = INITIAL_ALLOC

        path = self.recording_path()
        file = h5py.File(path, "w")
        self.write_attrs(file)
        if self._dark_image is not None:
            file.create_dataset("dark_image", data=self._dark_image.astype(np.float32))
        ds = self.create_datasets(file, frame_shape, frame_dtype)

        print(f"[FrameWriter] recording started: {path.name}")
        return file, ds

    def close_file(self, file, ds):
        if file is None:
            return
        actual = self.write_pos
        ds["frames"].resize(actual, axis=0)
        for name in ("pc_time", "camera_time", "frame_counter"):
            ds[name].resize(actual, axis=0)
        file.attrs["pc_end_time_unix"] = time.time()
        file.close()
        print(f"[FrameWriter] recording saved ({actual} frames)")

    def grow_datasets(self, ds, new_size):
        ds["frames"].resize(new_size, axis=0)
        for name in ("pc_time", "camera_time", "frame_counter"):
            ds[name].resize(new_size, axis=0)
        self.allocated = new_size
        print(f"[FrameWriter] buffer extended to {new_size} frames")

    def flush(self, file, ds, batch, bufs: WriteBuffers):
        n = len(batch)
        pos = self.write_pos

        if pos + n > self.allocated:
            self.grow_datasets(ds, self.allocated + RESIZE_STEP)

        for i, r in enumerate(batch):
            bufs.frame_buf[i] = r.frame
            bufs.pc_time_buf[i] = r.pc_time
            bufs.camera_time_buf[i] = r.camera_time if r.camera_time is not None else -1
            bufs.frame_counter_buf[i] = r.frame_counter if r.frame_counter is not None else -1

        ds["frames"][pos:pos+n] = bufs.frame_buf[:n]
        ds["pc_time"][pos:pos+n] = bufs.pc_time_buf[:n]
        ds["camera_time"][pos:pos+n] = bufs.camera_time_buf[:n]
        ds["frame_counter"][pos:pos+n] = bufs.frame_counter_buf[:n]

        self.write_pos += n
        file.flush()

    def write_attrs(self, file):
        s = self.session_meta
        c = self.camera_meta
        file.attrs["study_name"] = s.study_name
        file.attrs["subject_id"] = s.subject_id
        file.attrs["run_number"] = s.run_number
        file.attrs["interval_ms"] = s.interval_ms
        file.attrs["camera_id"] = f"{c.camera_model} | SN:{c.camera_serial}"
        file.attrs["gain_db"] = c.gain_db
        file.attrs["exposure_us"] = c.exposure_us
        file.attrs["pixel_format"] = c.pixel_format
        file.attrs["tick_frequency_hz"] = c.tick_frequency_hz if c.tick_frequency_hz is not None else -1
        file.attrs["pc_start_time_unix"] = c.pc_start_time_unix

    def create_datasets(self, file, frame_shape, frame_dtype):
        h, w = frame_shape
        n = INITIAL_ALLOC

        scalar = dict(shape=(n,), maxshape=(None,), chunks=(CHUNK,))
        return {
            "frames": file.create_dataset("frames", shape=(n, h, w), maxshape=(None, h, w),
                                                 chunks=(CHUNK, h, w), dtype=frame_dtype),
            "pc_time": file.create_dataset("pc_time", dtype="float64", **scalar),
            "camera_time": file.create_dataset("camera_time", dtype="int64", **scalar),
            "frame_counter": file.create_dataset("frame_counter", dtype="int64", **scalar),
        }

    def recording_path(self):
        safe_cam = safe_filename(self.camera_meta.camera_serial)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{self.session_meta.run_number}_{safe_cam}_{timestamp}.h5"
        return self.output_folder / filename
