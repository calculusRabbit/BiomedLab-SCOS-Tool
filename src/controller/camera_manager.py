from hardware.base_camera import BaseCamera
from hardware.pipeline import Pipeline
from state.camera_session import CameraSession


class CameraManager:
    # Creates and tracks all camera sessions for the current scan.

    # Each call to scan() wipes the previous sessions and builds new ones
    # from whatever cameras are physically connected at that moment.
    # The controller talks to individual cameras through their sessions.

    def __init__(self, camera_class: type[BaseCamera]):
        self._camera_cls = camera_class
        self._sessions: dict[str, CameraSession]  = {}
        self._display_names: dict[str, str] = {}  # serial -> display_name

    ## public API
    @property
    def scan_list(self) -> list[tuple[str, str]]:
        result = []
        for serial in self._sessions:
            result.append((serial, self._display_names[serial]))
        return result

    def scan(self) -> list[tuple[str, str]]:
        for session in self._sessions.values():
            session.pipeline.stop()
        self._sessions = {}
        self._display_names = {}

        for serial, model in self._camera_cls.scan():
            display_name = f"{model} | SN:{serial}"
            pipeline = Pipeline(self._camera_cls(serial))
            self._sessions[serial] = CameraSession(serial, pipeline)
            self._display_names[serial] = display_name

        return self.scan_list

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
        result = []

        for session in self._sessions.values():
            if session.is_connected:
                result.append(session.cam_id)

        return result
