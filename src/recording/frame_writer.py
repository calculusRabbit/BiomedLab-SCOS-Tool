import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np


@dataclass
class WriteBuffers:
    frame_buf:         np.ndarray
    pc_time_buf:       np.ndarray
    camera_time_buf:   np.ndarray
    exp_end_time_buf:  np.ndarray
    frame_counter_buf: np.ndarray
    grab_index_buf:    np.ndarray


@dataclass
class FrameRecord:
    frame: np.ndarray
    grab_index: int           # monotonic counter of ALL grabbed frames — for gap detection
    pc_time: float            # time.time() at grab — wall clock
    camera_time: int | None   # ChunkTimestamp ticks — hardware clock
    exp_end_time: int | None  # ExposureEnd event ticks — hardware clock
    frame_counter: int | None # camera frame counter (None on USB cameras)


@dataclass
class RecordingMeta:
    # identity
    study_name: str
    subject_id: str
    run_number: str
    camera_id: str

    # camera hardware params at time of recording
    gain_db: float
    exposure_us: float
    pixel_format: str
    tick_frequency_hz: int | None  # for converting camera_time ticks → seconds

    # recording config
    interval_ms: float  # 0 = every frame

    # capability flags
    camera_time_enabled: bool
    exp_end_time_enabled: bool
    frame_counter_enabled: bool

    # session timing
    pc_start_time_unix: float  # time.time() at recording start


CHUNK = 128     # frames per HDF5 chunk and write batch
INITIAL_ALLOC = 50000  # initial pre-allocated frames (~8 min at 100 fps)
RESIZE_STEP = 10000  # grow by this many frames when buffer overflows


class FrameWriter:

    def __init__(self):
        self.queue = queue.Queue(maxsize=512)
        self.thread = None
        self.running = False
        self.dropped_frames = 0

        self.meta = None
        self.output_folder  = None
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

    def start(self, output_folder: str, meta: RecordingMeta, buffer_size: int) -> None:
        if self.running:
            return

        self.meta = meta
        self.output_folder = Path(output_folder) / meta.study_name / meta.subject_id
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self.interval_ms = meta.interval_ms
        self.tick_freq_hz = meta.tick_frequency_hz
        self.last_cam_ts = 0
        self.last_pc_ts = 0.0
        self.dropped_frames = 0

        self.queue = queue.Queue(maxsize=buffer_size)
        self.running = True
        self.thread  = threading.Thread(target=self.write_loop, daemon=False)
        self.thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.queue.put(None)  # tells write loop to drain and exit
        if self.thread:
            self.thread.join()
            self.thread = None
        print("[FrameWriter] stopped")

    def push_frame(self, record: FrameRecord) -> None:
        if not self.running:
            return

        if self.interval_ms > 0:
            if record.camera_time is not None and self.tick_freq_hz is not None:
                time_since_last_frame_ms = (record.camera_time - self.last_cam_ts) *( 1000 / self.tick_freq_hz)
            else:
                time_since_last_frame_ms = (record.pc_time - self.last_pc_ts) * 1000
                
            if time_since_last_frame_ms < self.interval_ms:
                return

        self.last_cam_ts = record.camera_time if record.camera_time is not None else 0
        self.last_pc_ts  = record.pc_time

        try: # or should i just put everythng in queue and filter at saving part
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
        return first  # None means sentinel arrived before any real frame

    def write_loop(self):
        first = self.wait_for_first_frame()
        if first is None:
            return

        frame_shape = first.frame.shape
        frame_dtype = first.frame.dtype

        # pre-allocate write buffers once for the entire session
        h, w = frame_shape
        bufs = WriteBuffers(
            frame_buf = np.empty((CHUNK, h, w), dtype=frame_dtype),
            pc_time_buf = np.empty(CHUNK, dtype="float64"),
            camera_time_buf = np.empty(CHUNK, dtype="int64"),
            exp_end_time_buf = np.empty(CHUNK, dtype="int64"),
            frame_counter_buf = np.empty(CHUNK, dtype="int64"),
            grab_index_buf = np.empty(CHUNK, dtype="int64"),
        )

        batch = []
        file, ds = self.open_file(frame_shape, frame_dtype)

        while True:
            try:
                item = self.queue.get(timeout=0.1)
            except queue.Empty:
                if not self.running:
                    if batch:
                        self.flush(file, ds, batch, bufs)
                    break
                continue

            if item is None:  # sentinel from stop()
                if batch:
                    self.flush(file, ds, batch, bufs)
                break

            batch.append(item)

            if len(batch) >= CHUNK:
                self.flush(file, ds, batch, bufs)
                batch = []

        self.close_file(file, ds)

    def open_file(self, frame_shape, frame_dtype):
        self.write_pos = 0
        self.allocated = INITIAL_ALLOC

        path = self.recording_path()
        file = h5py.File(path, "w")
        self.write_attrs(file)
        ds = self.create_datasets(file, frame_shape, frame_dtype)

        print(f"[FrameWriter] recording started: {path.name}")
        return file, ds

    def close_file(self, file, ds):
        actual = self.write_pos
        ds["frames"].resize(actual, axis=0)
        for name in ("pc_time", "camera_time", "exp_end_time", "frame_counter", "grab_index"):
            ds[name].resize(actual, axis=0)
        file.close()
        print(f"[FrameWriter] recording saved ({actual} frames)")

    def grow_datasets(self, ds, new_size):
        ds["frames"].resize(new_size, axis=0)
        for name in ("pc_time", "camera_time", "exp_end_time", "frame_counter", "grab_index"):
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
            bufs.exp_end_time_buf[i] = r.exp_end_time if r.exp_end_time is not None else -1
            bufs.frame_counter_buf[i] = r.frame_counter if r.frame_counter is not None else -1
            bufs.grab_index_buf[i] = r.grab_index

        ds["frames"][pos:pos+n] = bufs.frame_buf[:n]
        ds["pc_time"][pos:pos+n] = bufs.pc_time_buf[:n]
        ds["camera_time"][pos:pos+n] = bufs.camera_time_buf[:n]
        ds["exp_end_time"][pos:pos+n] = bufs.exp_end_time_buf[:n]
        ds["frame_counter"][pos:pos+n] = bufs.frame_counter_buf[:n]
        ds["grab_index"][pos:pos+n] = bufs.grab_index_buf[:n]

        self.write_pos += n
        file.flush()

    def write_attrs(self, file):
        m = self.meta
        file.attrs["study_name"] = m.study_name
        file.attrs["subject_id"] = m.subject_id
        file.attrs["run_number"] = m.run_number
        file.attrs["camera_id"] = m.camera_id
        file.attrs["gain_db"] = m.gain_db
        file.attrs["exposure_us"] = m.exposure_us
        file.attrs["pixel_format"] = m.pixel_format
        file.attrs["tick_frequency_hz"] = m.tick_frequency_hz if m.tick_frequency_hz is not None else -1
        file.attrs["interval_ms"] = m.interval_ms
        file.attrs["camera_time_enabled"] = m.camera_time_enabled
        file.attrs["exp_end_time_enabled"] = m.exp_end_time_enabled
        file.attrs["frame_counter_enabled"] = m.frame_counter_enabled
        file.attrs["pc_start_time_unix"] = m.pc_start_time_unix

    def create_datasets(self, file, frame_shape, frame_dtype):
        h, w = frame_shape
        n = INITIAL_ALLOC

        scalar = dict(shape=(n,), maxshape=(None,), chunks=(CHUNK,))
        return {
            "frames": file.create_dataset("frames", shape=(n, h, w), maxshape=(None, h, w),
                                          chunks=(CHUNK, h, w), dtype=frame_dtype),
            "pc_time": file.create_dataset("pc_time", dtype="float64", **scalar),
            "camera_time": file.create_dataset("camera_time", dtype="int64", **scalar),
            "exp_end_time": file.create_dataset("exp_end_time", dtype="int64", **scalar),
            "frame_counter": file.create_dataset("frame_counter", dtype="int64", **scalar),
            "grab_index": file.create_dataset("grab_index", dtype="int64", **scalar),
        }

    def recording_path(self):
        m = self.meta

        chars = []
        for char in m.camera_id:
            if char.isalnum() or char in "-_":
                chars.append(char)
            else:
                chars.append("_")
        safe_cam = "".join(chars)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"run_{m.run_number}_{safe_cam}_{timestamp}.h5"
        return self.output_folder / filename
