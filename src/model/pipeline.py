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

        self.roi_pixels = None

    def start(self):
        if self._running:
            return
        self._camera.open()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
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

    def _run(self):
        while self._running:
            frame = self._camera.grab_frame()
            if frame is None:
                continue

            full_frame = frame  # always keep full frame for display
            roi = self.roi_pixels

            # crop only for processing
            if roi is not None:
                x1, y1, x2, y2 = roi   
                x1 = max(0, min(x1, frame.shape[1]))
                y1 = max(0, min(y1, frame.shape[0]))
                x2 = max(0, min(x2, frame.shape[1]))
                y2 = max(0, min(y2, frame.shape[0]))
                if x2 > x1 and y2 > y1:
                    frame = frame[y1:y2, x1:x2]

            output = process_all_data(frame)

            try:
                # put_nowait with full_frame for display, cropped already used for processing
                self._queue.put_nowait((full_frame, output))
            except queue.Full:
                pass


