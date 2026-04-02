import dearpygui.dearpygui as dpg
from config import RECT_COLOR, HANDLE_COLOR, HANDLE_RADIUS


_TAG_RECT    = "roi_rect"
_TAG_HANDLES = {"tl": "roi_tl", "tr": "roi_tr", "bl": "roi_bl", "br": "roi_br"}


class ROISelector:

    def __init__(self, drawlist, display_w, display_h):
        self._drawlist  = drawlist
        self._display_w = display_w
        self._display_h = display_h

        self._x1 = display_w * 0.25
        self._y1 = display_h * 0.25
        self._x2 = display_w * 0.75
        self._y2 = display_h * 0.75

        self._mode = None
        self._drag_handle = None
        self._drag_offset = (0.0, 0.0)

        self._draw()

    def get_coords_normalized(self):
        return (
            self._x1 / self._display_w,
            self._y1 / self._display_h,
            self._x2 / self._display_w,
            self._y2 / self._display_h,
        )

    def set_coords_normalized(self, nx1, ny1, nx2, ny2):
        self._x1 = nx1 * self._display_w
        self._y1 = ny1 * self._display_h
        self._x2 = nx2 * self._display_w
        self._y2 = ny2 * self._display_h
        self._redraw()

    def update_display_size(self, display_w, display_h):
        sx = display_w / self._display_w
        sy = display_h / self._display_h
        self._x1 *= sx;  self._y1 *= sy
        self._x2 *= sx;  self._y2 *= sy
        self._display_w = display_w
        self._display_h = display_h
        self._redraw()

    # mouse events - called by AppController, mx/my already in drawlist local space
    def on_mouse_down(self, mx, my):
        if self._mode is not None:
            return
        handle = self._hit_handle(mx, my)
        if handle:
            self._mode = "resizing"
            self._drag_handle = handle
        elif self._x1 <= mx <= self._x2 and self._y1 <= my <= self._y2:
            self._mode = "moving"
            self._drag_offset = (mx - self._x1, my - self._y1)

    def on_mouse_move(self, mx, my):
        if self._mode is None:
            return
        mx = max(0.0, min(mx, float(self._display_w)))
        my = max(0.0, min(my, float(self._display_h)))
        if self._mode == "moving":
            self._move(mx, my)
        else:
            self._resize(mx, my)
        self._redraw()

    def on_mouse_release(self):
        self._mode        = None
        self._drag_handle = None

    # private
    def _draw(self):
        x1, y1, x2, y2 = self._x1, self._y1, self._x2, self._y2
        dpg.draw_rectangle(pmin=(x1, y1), pmax=(x2, y2),
                           color=RECT_COLOR, tag=_TAG_RECT, parent=self._drawlist)
        for key, (cx, cy) in self._corners().items():
            dpg.draw_circle(center=(cx, cy), radius=HANDLE_RADIUS,
                            color=HANDLE_COLOR, fill=HANDLE_COLOR,
                            tag=_TAG_HANDLES[key], parent=self._drawlist)

    def _redraw(self):
        dpg.configure_item(_TAG_RECT, pmin=(self._x1, self._y1), pmax=(self._x2, self._y2))
        for key, (cx, cy) in self._corners().items():
            dpg.configure_item(_TAG_HANDLES[key], center=(cx, cy))

    def _corners(self):
        return {
            "tl": (self._x1, self._y1), "tr": (self._x2, self._y1),
            "bl": (self._x1, self._y2), "br": (self._x2, self._y2),
        }

    def _hit_handle(self, mx, my):
        for name, (cx, cy) in self._corners().items():
            if ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5 <= HANDLE_RADIUS + 5:
                return name
        return None

    def _move(self, mx, my):
        ox, oy = self._drag_offset
        w, h   = self._x2 - self._x1, self._y2 - self._y1
        self._x1 = max(0.0, min(mx - ox, self._display_w - w))
        self._y1 = max(0.0, min(my - oy, self._display_h - h))
        self._x2 = self._x1 + w
        self._y2 = self._y1 + h

    def _resize(self, mx, my):
        MIN = 10.0
        h = self._drag_handle
        if h == "tl":
            self._x1 = min(mx, self._x2 - MIN);  self._y1 = min(my, self._y2 - MIN)
        elif h == "tr":
            self._x2 = max(mx, self._x1 + MIN);  self._y1 = min(my, self._y2 - MIN)
        elif h == "bl":
            self._x1 = min(mx, self._x2 - MIN);  self._y2 = max(my, self._y1 + MIN)
        elif h == "br":
            self._x2 = max(mx, self._x1 + MIN);  self._y2 = max(my, self._y1 + MIN)