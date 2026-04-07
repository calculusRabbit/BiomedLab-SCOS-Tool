from dataclasses import dataclass


@dataclass
class AppState:
    """
    Single source of truth for global application state.

    The UI controller reads and writes this. Nothing else should own
    these two fields — they belong here, not scattered on the controller.
    """
    is_running:    bool       = False
    active_cam_id: str | None = None
