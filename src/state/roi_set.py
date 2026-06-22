from config import CAMERA_W, CAMERA_H, ROI_CONFIGS


class ROISet:
    # Stores ROI coordinates for one camera session.

    # Coordinates are stored as normalized values (0.0 to 1.0) so they are
    # independent of display resolution. Use to_pixels() to get actual sensor
    # pixel coordinates when needed for cropping or processing.

    # default normalized (x1, y1, x2, y2) positions for each ROI at startup
    _DEFAULTS = {
        "source": (0.25, 0.25, 0.75, 0.75),
        "detector": (0.10, 0.10, 0.40, 0.40),
    }

    def __init__(self):
        self._coords: dict[str, tuple[float, float, float, float]] = {
            name: self._DEFAULTS[name]
            for name in ROI_CONFIGS
        }

    def get(self, name: str) -> tuple[float, float, float, float]:
        return self._coords[name]

    def set(self, name: str, coords: tuple[float, float, float, float]) -> None:
        self._coords[name] = coords

    def names(self) -> list[str]:
        return list(self._coords.keys())

    def to_pixels(self, name: str) -> tuple[int, int, int, int]:
        # convert normalized coords to actual sensor pixel coords (x1, y1, x2, y2)
        # width and height are rounded from the normalized size first, not from x2-x1,
        # so that moving the ROI without resizing never causes a 1-pixel shape change
        nx1, ny1, nx2, ny2 = self._coords[name]
        x1 = round(nx1 * CAMERA_W)
        y1 = round(ny1 * CAMERA_H)
        w = round((nx2 - nx1) * CAMERA_W)
        h = round((ny2 - ny1) * CAMERA_H)
        return (x1, y1, x1 + w, y1 + h)
