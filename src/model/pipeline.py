#  Worker thread - grabs frames, runs processing, feeds the display queue.
#  Queue is maxsize=1 (always latest frame, old ones dropped) because i think live monitors want current data, not a backlog.


import queue
import threading

from model.processor import process_all_data


class Pipeline:

    def __init__(self, camera):
        self._camera = camera
        self._queue = queue.Queue(maxsize=1)
        self._running = False
        self._thread = None

    def start(self) -> None:
        if self._running:
            return
        self._camera.open()
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._camera.close()

    def get_latest(self):
        # Non-blocking. Call from the main/UI thread every render frame
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None


    def _run(self) -> None:
        while self._running:
            frame = self._camera.grab_frame()
            if frame is None:
                continue
            output = process_all_data(frame)
            try:
                self._queue.put_nowait(output)
            except queue.Full:
                pass    # UI busy - drop this frame, show next one



