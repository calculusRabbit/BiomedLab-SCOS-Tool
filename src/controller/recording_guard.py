# Validates recording conditions before the user clicks Start.
# Returns errors (hard blocks), warnings (soft alerts), and info messages (disk estimate).
# The controller checks the result and either blocks the recording or shows the message.

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from config import CAMERA_BIT_DEPTH
from controller.camera_manager import CameraManager
from recording.frame_writer import SessionMeta
from state.app_state import AppState


@dataclass
class GuardResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def check(manager: CameraManager, state: AppState, session_meta: SessionMeta) -> GuardResult:
    errors = []
    warnings = []
    info = []

    # at least one camera selected for recording
    recording_ids = []
    for cam_id in manager.connected_ids():
        if cam_id in state.record_cam_ids:
            recording_ids.append(cam_id)
    if not recording_ids:
        errors.append("No cameras selected for recording.")

    # output folder is writable
    folder = Path(session_meta.output_folder) if session_meta.output_folder else Path("./data")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        test_file = folder / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception:
        errors.append(f"Output folder is not writable: {folder}")

    # dark image loaded per recording camera (warning only)
    for cam_id in recording_ids:
        session = manager.get_session(cam_id)
        if session is not None and session.dark_image is None:
            warnings.append(f"No dark image for SN:{cam_id} — dark subtraction will be skipped.")

    # disk space estimate — tell operator how long they can record
    if recording_ids:
        info.append(_disk_estimate(manager, recording_ids, folder, session_meta.interval_ms))

    return GuardResult(ok=len(errors) == 0, errors=errors, warnings=warnings, info=info)


def _disk_estimate(manager: CameraManager, recording_ids: list[str], folder: Path, interval_ms: float) -> str:
    # pick ROI size from first recording camera
    roi_w, roi_h = 0, 0
    for cam_id in recording_ids:
        session = manager.get_session(cam_id)
        if session is not None:
            roi = session.roi_set.to_pixels("source")
            if roi:
                roi_w = roi[2] - roi[0]  # x2 - x1
                roi_h = roi[3] - roi[1]  # y2 - y1
            break

    if roi_w == 0 or roi_h == 0:
        return "Disk estimate unavailable — ROI not set."

    # bytes written per frame per camera
    # CAMERA_BIT_DEPTH // 8 = 1 for Mono8, 2 for Mono12/Mono16
    bytes_per_pixel = CAMERA_BIT_DEPTH // 8
    bytes_per_frame = roi_w * roi_h * bytes_per_pixel

    # effective fps: user-set interval or camera hardware fps
    if interval_ms > 0:
        fps = 1000.0 / interval_ms
    else:
        session = manager.get_session(recording_ids[0])
        fps = session.pipeline.get_camera_fps() or 30.0

    n_cameras = len(recording_ids)

    # total write rate across all cameras
    bytes_per_sec = bytes_per_frame * fps * n_cameras

    # free disk space on the output drive
    free_bytes = shutil.disk_usage(folder).free
    free_gb = free_bytes / 1_000_000_000

    if bytes_per_sec > 0:
        free_seconds = free_bytes / bytes_per_sec
        free_minutes = free_seconds / 60.0
        return (
            f"Free disk: {free_gb:.1f} GB — "
            f"enough for ~{free_minutes:.0f} min "
            f"({n_cameras} cam(s), {fps:.0f} fps, {roi_w}x{roi_h} ROI, "
            f"{bytes_per_sec / 1_000_000:.0f} MB/s)"
        )

    return f"Free disk: {free_gb:.1f} GB"
