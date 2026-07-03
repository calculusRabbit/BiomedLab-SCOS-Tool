# Writes trigger markers received during a recording to a two-column CSV
# (pc_time, marker), saved next to the camera .h5 files with the same
# study/subject/run naming.
#
# Unlike FrameWriter there is no background thread: markers are rare
# (human-scale events, not per-frame), so a synchronous append is enough.

import csv
from datetime import datetime
from pathlib import Path

from processing.utils import safe_filename
from recording.frame_writer import SessionMeta


class TriggerWriter:

    def __init__(self):
        self._file = None
        self._writer = None

    def start(self, session_meta: SessionMeta) -> None:
        folder = Path(session_meta.output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        safe_study = safe_filename(session_meta.study_name)
        safe_subject = safe_filename(session_meta.subject_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_study}_{safe_subject}_run_{session_meta.run_number}_markers_{timestamp}.csv"

        self._file = open(folder / filename, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["pc_time", "marker"])
        print(f"[TriggerWriter] marker log started: {filename}")

    def push(self, pc_time: float, marker: str) -> None:
        if self._writer is None:
            return
        self._writer.writerow([pc_time, marker])
        # flush every row so a crash never loses markers — rows are rare enough
        # that this costs nothing
        self._file.flush()

    def stop(self) -> None:
        if self._file:
            self._file.close()
            print("[TriggerWriter] marker log closed")
        self._file = None
        self._writer = None
