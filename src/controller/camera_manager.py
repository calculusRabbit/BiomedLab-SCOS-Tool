from hardware.base_camera import BaseCamera
from hardware.pipeline import Pipeline
from state.camera_session import CameraSession


class CameraManager:
    """
    Creates, tracks, and tears down camera sessions.

    Responsibility: hardware lifecycle only.
    Does NOT own application state (is_running, active_cam_id) — that lives in AppState.
    Does NOT mutate data buffers — that is the controller's job via session.data.
    """

    def __init__(self, camera_class: type[BaseCamera]):
        self._camera_cls                          = camera_class
        self._sessions: dict[str, CameraSession] = {}
        self._scan_list: list[str]               = []

    # ── public API ─────────────────────────────────────────────────────────────

    @property
    def scan_list(self) -> list[str]:
        return list(self._scan_list)

    def scan(self) -> list[str]:
        """Stop all existing sessions, discover devices, create fresh sessions."""
        for session in self._sessions.values():
            session.pipeline.stop()
        self._sessions  = {}
        self._scan_list = self._camera_cls.scan()

        for i, cam_id in enumerate(self._scan_list):
            pipeline = Pipeline(self._camera_cls(i))
            self._sessions[cam_id] = CameraSession(cam_id, pipeline)

        return self._scan_list

    def connect(self, cam_id: str) -> CameraSession | None:
        session = self._sessions.get(cam_id)
        if session and not session.is_connected:
            try:
                session.pipeline.start()
                session.is_connected = True
            except Exception as e:
                print(f"[CameraManager.connect] {cam_id}: {e}")
                return None
        return session

    def stop_all(self) -> None:
        for session in self._sessions.values():
            session.pipeline.stop()
            session.is_connected = False

    def get_session(self, cam_id: str | None) -> CameraSession | None:
        if cam_id is None:
            return None
        return self._sessions.get(cam_id)

    def connected_ids(self) -> list[str]:
        return [s.cam_id for s in self._sessions.values() if s.is_connected]
