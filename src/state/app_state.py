from dataclasses import dataclass, field
from enum import Enum


# CameraState drives which buttons are enabled in the UI.
# The only valid transitions are:
#   IDLE -> CONNECTED <-> RECORDING
# Scanning always resets back to IDLE.
# SCOS processing/visualization (preview) is an independent flag (preview_on),
# it can be toggled on/off at any time, including while recording.
class CameraState(Enum):
    IDLE = "idle" # no camera connected yet
    CONNECTED  = "connected"  # camera is open and streaming, not recording
    RECORDING  = "recording"  # writing frames to disk


@dataclass
class AppState:
    # Shared state that the UI controller reads and writes.
    # Only the controller should modify these fields.
    camera_state: CameraState = CameraState.IDLE
    preview_on: bool = False  # SCOS processing + plots/K2 maps running (independent of recording)
    active_cam_id: str | None = None # serial of the camera currently shown in the UI
    record_start_time: float = 0.0   # time.time() when recording started, used for elapsed timer
    record_cam_ids: set[str] = field(default_factory=set)  # serials of cameras selected for recording
