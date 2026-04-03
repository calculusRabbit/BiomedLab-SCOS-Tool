# controller/camera_manager.py
from collections import deque

from model.pipeline import Pipeline
from config import MAX_PLOT_POINTS, TEXTURE_W, TEXTURE_H, CAMERA_W, CAMERA_H


class CameraSession:
    # everything that belongs to one connected camera:
    # its pipeline, data buffers, ROI, and connection state.
    def __init__(self, cam_id, pipeline):
        self.cam_id = cam_id
        self.pipeline = pipeline
        self.is_connected = False
        self.roi_norm = (0.25, 0.25, 0.75, 0.75)  # normalized (x1,y1,x2,y2)
        self.start_time = 0.0
        self.last_frame = None
        self.t_buf = deque(maxlen=MAX_PLOT_POINTS)
        self.k2_buf = deque(maxlen=MAX_PLOT_POINTS)
        self.bfi_buf = deque(maxlen=MAX_PLOT_POINTS)
        self.cc_buf = deque(maxlen=MAX_PLOT_POINTS)
        self.od_buf = deque(maxlen=MAX_PLOT_POINTS)

    def clear_buffers(self):
        for buf in (self.t_buf, self.k2_buf, self.bfi_buf, self.cc_buf, self.od_buf):
            buf.clear()
        self.last_frame = None


class CameraManager:
    # creates, tracks, and tears down camera sessions.
    def __init__(self, camera_class):
        self._camera_cls = camera_class
        self._sessions = {} # cam_id -> CameraSession
        self._scan_list = []

    def scan(self):
        for session in self._sessions.values():
            session.pipeline.stop()
        self._sessions = {}
        self._scan_list = self._camera_cls.scan()
        for i, cam_id in enumerate(self._scan_list):
            camera = self._camera_cls(i)
            pipeline = Pipeline(camera)
            session = CameraSession(cam_id, pipeline)
            self._sessions[cam_id] = session
        return self._scan_list

    def connect(self, cam_id):
        session = self._sessions.get(cam_id)
        if session and not session.is_connected:
            try:
                session.pipeline.start()
                session.is_connected = True
            except Exception as e:
                print(f"[connect] failed to open {cam_id}: {e}")
                return None
        return session

    def stop_all(self):
        for session in self._sessions.values():
            session.pipeline.stop()
            session.is_connected = False

    def get_session(self, cam_id):
        return self._sessions.get(cam_id)

    def all_sessions(self):
        return list(self._sessions.values())

    def connected_ids(self):
        result = []
        for s in self._sessions.values():
            if s.is_connected:
                result.append(s.cam_id)
        return result


    def roi_to_pixels(self, session):
        nx1, ny1, nx2, ny2 = session.roi_norm
        return (
            int(nx1 * CAMERA_W), int(ny1 * CAMERA_H),
            int(nx2 * CAMERA_W), int(ny2 * CAMERA_H),
        )