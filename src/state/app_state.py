from dataclasses import dataclass


@dataclass
class AppState:
    # Shared application state readable by any layer without importing the controller
    # Write here from the controller only; hardware/processing layers read only
    # this tell Who writes vs. reads — controller writes, others read

      is_running: bool = False   # True while a camera session is active
      active_cam_id: str | None = None # id of the currently selected camera

