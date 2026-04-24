# FrameWriter, disk writer thread for raw frame recording.

# HDF5 attrs:
#   camera_id, chunk_timestamp_enabled, chunk_framecounter_enabled

import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from config import RECORD_QUEUE_SIZE


class FrameWriter:

    def __init__(self, queue_size=RECORD_QUEUE_SIZE):
        self._queue_size = queue_size
        self._queue = queue.Queue(maxsize=queue_size)

        self._thread: threading.Thread | None = None
        self._running = False
        self._interval_s = 0.0
        self._last_saved = 0.0

        self._dropped = 0
        self._file_path: Path | None = None
        self._cam_id: str = "cam"

    # public API 
    @property
    def queue_size(self) -> int:
        # Frames currently waiting in the RAM buffer
        return self._queue.qsize()

    @property
    def dropped(self) -> int:
        # Frames dropped because the queue was full
        return self._dropped

    @property
    def is_recording(self) -> bool:
        return self._running

    @property
    def file_path(self) -> Path | None:
        # Path of the HDF5 file currently being written.
        return self._file_path

    def start(self, output_folder: str, cam_id: str = "cam", interval_ms: float = 0.0) -> None:
        # Start recording.
        # output_folder: directory to save the HDF5 file
        # cam_id: camera identifier, used in filename and HDF5 attrs
        # interval_ms: save one frame every N ms (0 = every frame)

        # start recording
        if self._running:
            return

        folder = Path(output_folder)
        folder.mkdir(parents=True, exist_ok=True)

        self._cam_id = cam_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file_path = folder / f"session_{timestamp}_{cam_id}.h5"

        self._interval_s = interval_ms / 1000.0
        self._last_saved = 0.0
        self._dropped = 0
        self._running = True

        self._thread = threading.Thread(target=self._write_loop, daemon=False)
        self._thread.start()
        print(f"[FrameWriter] recording started → {self._file_path}")

    def stop(self) -> None:
        # Signal stop and block until the queue is fully drained and file is closed.
        if not self._running:
            return
        self._running = False
        self._queue.put(None)  # tell writer thread to exit after draining
        if self._thread:
            self._thread.join()
            self._thread = None
        print(f"[FrameWriter] recording stopped — {self._file_path}")

    def push_frame(self, frame: np.ndarray, host_ts: float, cam_ts: int | None, frame_counter: int | None) -> None:

        # Called by Pipeline on every grabbed frame (non-blocking).
        # Drops the frame if queue is full.
        # host_ts — time.time() taken at grab (always present)
        # cam_ts — camera hardware ticks, or None if unsupported
        # frame_counter — camera frame counter, or None if unsupported

        if not self._running:
            return

        if self._interval_s > 0 and (host_ts - self._last_saved) < self._interval_s:
            return

        try:
            self._queue.put_nowait((frame, host_ts, cam_ts, frame_counter))
            self._last_saved = host_ts
        except queue.Full:
            self._dropped += 1


    # writer thread 
    def _write_loop(self) -> None:
        with h5py.File(self._file_path, "w") as f:
            f.attrs["camera_id"] = self._cam_id

            frames_ds: h5py.Dataset = None
            host_ts_ds: h5py.Dataset = None
            cam_ts_ds: h5py.Dataset = None
            fc_ds: h5py.Dataset = None


            while True:
                item = self._queue.get()

                if item is None:
                    while not self._queue.empty():
                        item = self._queue.get_nowait()
                        if item is not None:
                            frames_ds, host_ts_ds, cam_ts_ds, fc_ds = self._write_frame(
                                f, item, frames_ds, host_ts_ds, cam_ts_ds, fc_ds
                            )
                    break

                frames_ds, host_ts_ds, cam_ts_ds, fc_ds = self._write_frame(
                    f, item, frames_ds, host_ts_ds, cam_ts_ds, fc_ds
                )

        print(f"[FrameWriter] file closed — {self._file_path}")



    def _write_frame(
        self,
        f: h5py.File,
        item: tuple[np.ndarray, float, int | None, int | None],
        frames_ds: "h5py.Dataset | None",
        host_ts_ds: "h5py.Dataset | None",
        cam_ts_ds: "h5py.Dataset | None",
        fc_ds: "h5py.Dataset | None",
    ):
        
        frame, host_ts, cam_ts, frame_counter = item

        if cam_ts is not None:
            cam_ts_val = cam_ts
        else:
            cam_ts_val = -1

        if frame_counter is not None:
            fc_val = frame_counter
        else:
            fc_val = -1


        if frames_ds is None:
            h, w = frame.shape
            frames_ds = f.create_dataset(
                "frames", shape=(1, h, w), maxshape=(None, h, w),
                dtype=frame.dtype, chunks=(1, h, w),
            )

            host_ts_ds = f.create_dataset(
                "host_ts", shape=(1,), maxshape=(None,), dtype=np.float64,
            )

            cam_ts_ds = f.create_dataset(
                "camera_ts_ticks", shape=(1,), maxshape=(None,), dtype=np.int64,
            )
            
            fc_ds = f.create_dataset(
                "frame_counter", shape=(1,), maxshape=(None,), dtype=np.int64,
            )

            frames_ds[0] = frame
            host_ts_ds[0] = host_ts
            cam_ts_ds[0] = cam_ts_val
            fc_ds[0] = fc_val

            if cam_ts is not None:
                f.attrs["chunk_timestamp_enabled"] = True
            else:
                f.attrs["chunk_timestamp_enabled"] = False

            if frame_counter is not None:
                f.attrs["chunk_framecounter_enabled"] = True
            else:
                f.attrs["chunk_framecounter_enabled"] = False

        else:
            # Append one frame record to the HDF5 datasets (file-backed writes)
            n = frames_ds.shape[0] + 1
            frames_ds.resize(n, axis=0)
            host_ts_ds.resize(n, axis=0)
            cam_ts_ds.resize(n, axis=0)
            fc_ds.resize(n, axis=0)
            frames_ds[n - 1]  = frame
            host_ts_ds[n - 1] = host_ts
            cam_ts_ds[n - 1]  = cam_ts_val
            fc_ds[n - 1] = fc_val

        return frames_ds, host_ts_ds, cam_ts_ds, fc_ds
