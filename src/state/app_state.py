from dataclasses import dataclass


@dataclass
class AppState:
    # Controller writes; all other layers read only.
    is_running: bool = False # True while a camera session is active
    active_cam_id: str | None = None  # cam_id of the currently displayed camera

