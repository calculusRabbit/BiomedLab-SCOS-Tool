# Discovers and listens to LSL marker streams (the "trigger source").

# This class is the inlet side: scan() finds available "Markers" streams, connect() opens
# one, and poll() drains whatever markers arrived since the last call.
#
# Threading note: everything here is called from the main (UI) thread.
# ContinuousResolver resolves in the background inside liblsl, and
# pull_sample(timeout=0.0) never blocks, so no extra threads are needed.

import time

from pylsl import ContinuousResolver, StreamInfo, StreamInlet


class TriggerManager:
    # One trigger connection for the whole app — markers describe
    # experiment-level events, not per-camera ones.

    def __init__(self):
        self._resolver: ContinuousResolver | None = None  # created lazily, then kept forever
        self._streams: dict[str, StreamInfo] = {}  # name -> info from the last scan
        self._inlet: StreamInlet | None = None

    def scan(self) -> list[str]:
        # returns the names of all "Markers" streams currently visible.
        # The first scan right after the resolver is created may return [] while
        # it warms up (~1s) — clicking Scan again picks up the streams.
        if self._resolver is None:
            self._resolver = ContinuousResolver("type", "Markers")
        self._streams = {s.name(): s for s in self._resolver.results()}
        return list(self._streams.keys())

    def connect(self, name: str) -> bool:
        info = self._streams.get(name)
        if info is None:
            return False
        self._inlet = StreamInlet(info)  # replaces the previous inlet if any
        return True

    def is_connected(self) -> bool:
        return self._inlet is not None

    def poll(self) -> list[tuple[str, float]]:
        # Drain every marker queued since the last call, never blocking.
        # Returns [(marker_text, pc_time), ...] where pc_time is time.time()
        # at pull — the same wall-clock basis as FrameRecord.pc_time, so
        # markers and recorded frames share a timeline.
        events: list[tuple[str, float]] = []
        if self._inlet is None:
            return events
        while True:
            try:
                sample, _lsl_ts = self._inlet.pull_sample(timeout=0.0)
            except Exception as e:
                # LostError etc. — the source died; drop the inlet but keep
                # the app (and any active recording) running
                print(f"[TriggerManager] stream lost: {e}")
                self._inlet = None
                break
            if sample is None:
                break
            events.append((sample[0], time.time()))
        return events
