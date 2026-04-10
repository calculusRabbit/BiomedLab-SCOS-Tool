import dearpygui.dearpygui as dpg

from config import HANDLE_RADIUS


class ROISelector:

    # Draggable, resizable ROI rectangle drawn on a real time Image

    # Each instance gets a unique tag prefix

    # The controller decides WHEN to show/hide — this class just obeys.
    # Coordinate data (normalized) is stored in ROISet (state layer),



    def __init__(
        self,
        drawlist: str,
        display_w: int,
        display_h: int,
        name: str = "roi",
        color: tuple = (255, 0, 0, 255),
    ):
        self._drawlist = drawlist
        self._display_w = float(display_w)
        self._display_h = float(display_h)
        self._visible = True
        self._color = color

        # unique DearPyGUI tags per instance = prevents collisions with multiple ROIs
        self._tag_rect = f"{name}_rect"
        self._tag_handles = {
            "tl": f"{name}_tl",
            "tr": f"{name}_tr",
            "bl": f"{name}_bl",
            "br": f"{name}_br",
        }

        self._x1 = display_w * 0.25
        self._y1 = display_h * 0.25
        self._x2 = display_w * 0.75
        self._y2 = display_h * 0.75

        self._mode = None   # None | "moving" | "resizing"
        self._drag_handle = None
        self._drag_offset = (0.0, 0.0)

        self._draw()

    # visibility ##

    def show(self) -> None:
        self._visible = True
        dpg.configure_item(self._tag_rect, show=True)
        for tag in self._tag_handles.values():
            dpg.configure_item(tag, show=True)

    def hide(self) -> None:
        self._visible = False
        dpg.configure_item(self._tag_rect, show=False)
        for tag in self._tag_handles.values():
            dpg.configure_item(tag, show=False)

    def is_visible(self) -> bool:
        return self._visible

    ## coordinates ##

    def get_coords_normalized(self) -> tuple[float, float, float, float]:
        return (
            self._x1 / self._display_w,
            self._y1 / self._display_h,
            self._x2 / self._display_w,
            self._y2 / self._display_h,
        )

    def set_coords_normalized(self, nx1: float, ny1: float, nx2: float, ny2: float) -> None:
        self._x1 = nx1 * self._display_w
        self._y1 = ny1 * self._display_h
        self._x2 = nx2 * self._display_w
        self._y2 = ny2 * self._display_h
        self._redraw()

    def update_display_size(self, display_w: int, display_h: int) -> None:
        sx = display_w / self._display_w
        sy = display_h / self._display_h
        self._x1 *= sx;  
        self._y1 *= sy
        self._x2 *= sx;  
        self._y2 *= sy
        self._display_w = float(display_w)
        self._display_h = float(display_h)
        self._redraw()

    ## mouse events (coords already in drawlist-local space) #

    def on_mouse_down(self, mx: float, my: float) -> None:
        if self._mode is not None:
            return
        handle = self._hit_handle(mx, my)
        if handle:
            self._mode = "resizing"
            self._drag_handle = handle
        elif self._x1 <= mx <= self._x2 and self._y1 <= my <= self._y2:
            self._mode = "moving"
            self._drag_offset = (mx - self._x1, my - self._y1)

    def on_mouse_move(self, mx: float, my: float) -> None:
        if self._mode is None:
            return
        mx = max(0.0, min(mx, self._display_w))
        my = max(0.0, min(my, self._display_h))
        if self._mode == "moving":
            self._move(mx, my)
        else:
            self._resize(mx, my)
        self._redraw()

    def on_mouse_release(self) -> None:
        self._mode = None
        self._drag_handle = None

    def is_dragging(self) -> bool:
        return self._mode is not None

    ## private ##

    def _draw(self) -> None:
        x1, y1, x2, y2 = self._x1, self._y1, self._x2, self._y2
        dpg.draw_rectangle(
            pmin=(x1, y1), pmax=(x2, y2),
            color=self._color, tag=self._tag_rect, parent=self._drawlist,
        )
        for key, (cx, cy) in self._corners().items():
            dpg.draw_circle(
                center=(cx, cy), radius=HANDLE_RADIUS,
                color=self._color, fill=self._color,
                tag=self._tag_handles[key], parent=self._drawlist,
            )

    def _redraw(self) -> None:
        dpg.configure_item(self._tag_rect, pmin=(self._x1, self._y1), pmax=(self._x2, self._y2))
        for key, (cx, cy) in self._corners().items():
            dpg.configure_item(self._tag_handles[key], center=(cx, cy))

    def _corners(self) -> dict:
        return {
            "tl": (self._x1, self._y1), "tr": (self._x2, self._y1),
            "bl": (self._x1, self._y2), "br": (self._x2, self._y2),
        }

    def _hit_handle(self, mx: float, my: float) -> str | None:
        for name, (cx, cy) in self._corners().items():
            if ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5 <= HANDLE_RADIUS + 5:
                return name
        return None

    def _move(self, mx: float, my: float) -> None:
        ox, oy = self._drag_offset
        w  = self._x2 - self._x1
        h  = self._y2 - self._y1
        self._x1 = max(0.0, min(mx - ox, self._display_w - w))
        self._y1 = max(0.0, min(my - oy, self._display_h - h))
        self._x2 = self._x1 + w
        self._y2 = self._y1 + h

    def _resize(self, mx: float, my: float) -> None:
        MIN = 10.0
        h   = self._drag_handle
        if h == "tl":
            self._x1 = min(mx, self._x2 - MIN);  self._y1 = min(my, self._y2 - MIN)
        elif h == "tr":
            self._x2 = max(mx, self._x1 + MIN);  self._y1 = min(my, self._y2 - MIN)
        elif h == "bl":
            self._x1 = min(mx, self._x2 - MIN);  self._y2 = max(my, self._y1 + MIN)
        elif h == "br":
            self._x2 = max(mx, self._x1 + MIN);  self._y2 = max(my, self._y1 + MIN)
