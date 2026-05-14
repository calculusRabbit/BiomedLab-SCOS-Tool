from dataclasses import dataclass, field
from enum import Enum


class CameraState(Enum):
    IDLE = "idle " # no camera connected
    CONNECTED  = "connected"  # camera open, not streaming
    PREVIEWING = "previewing" # live feed running
    RECORDING  = "recording"  # streaming + writing to disk


@dataclass
class AppState:
    # Controller writes; all other layers read only.
    camera_state: CameraState = CameraState.IDLE
    active_cam_id: str | None = None
    record_start_time: float = 0.0
    record_cam_ids: set[str] = field(default_factory=set)
