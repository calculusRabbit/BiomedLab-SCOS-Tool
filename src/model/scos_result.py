
# Shared data contract between UI and processing

# Rules:
# frozen=True = immutable, safe to pass across threads
# Controller reads SCOSResult and updates the UI



from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    frame: np.ndarray
    k2: float = 0.0
    bfi: float = 0.0
    cc: float = 0.0
    od: float = 0.0
    heat_map: np.ndarray | None = None

