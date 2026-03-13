# controller/roi_selector.py
# Draws a draggable ROI rectangle on the live image drawlist.

import dearpygui.dearpygui as dpg
from config import TEXTURE_W, TEXTURE_H, RECT_COLOR, HANDLE_COLOR, HANDLE_RADIUS


_RECT_TAG     = "roi_rect"
_HANDLE_TAGS  = ["roi_tl", "roi_tr", "roi_bl", "roi_br"]


class ROISelector:

    def __init__(self, drawlist_tag: str, display_w: int, display_h: int):
        self._drawlist  = drawlist_tag
        self._display_w = display_w
        self._display_h = display_h

        # default rectangle — center 50% of image
        self._x1 = display_w * 0.25
        self._y1 = display_h * 0.25
        self._x2 = display_w * 0.75
        self._y2 = display_h * 0.75

        self._mode        = None   
        self._drag_handle = None
        self._drag_offset = (0, 0)

    def setup_handlers(self):
        # set up listeners and event
        with dpg.handler_registry():
            # trigger every time user press mouse button
            # we check if mouse is over rectangle, if yes start DRAG
            dpg.add_mouse_down_handler(callback=self._on_mouse_down)

            # trigger every time mouse moves
            # if currently dragging, UPDATE rectangle position
            dpg.add_mouse_move_handler(callback=self._on_mouse_move)

            # trigger when user lift finger out of mouse button
            # STOP dragging, clear mode
            dpg.add_mouse_release_handler(callback=self._on_mouse_release)
        self._draw_initial()


    def get_roi(self):
        #Returns ROI in real frame pixel coordinates
        sx = TEXTURE_W / self._display_w
        sy = TEXTURE_H / self._display_h
        return (int(self._x1*sx), int(self._y1*sy), int(self._x2*sx), int(self._y2*sy))
    

    def update_display_size(self, display_w, display_h):
        # after resize, how much my actual widh and height of main window changed
        sx = display_w / self._display_w
        sy = display_h / self._display_h

        # scale ROI rectangle to match new size
        self._x1 *= sx
        self._y1 *= sy
        self._x2 *= sx
        self._y2 *= sy

        # save new size
        self._display_w = display_w
        self._display_h = display_h

        self._redraw() #redraw my roi rectangle


    # drawing
    def _draw_initial(self):
        # Create rectangle and circle conner handles for the first time
        x1, y1, x2, y2 = self._x1, self._y1, self._x2, self._y2
        dpg.draw_rectangle(pmin=(x1,y1), pmax=(x2,y2),color=RECT_COLOR, tag=_RECT_TAG, parent=self._drawlist)
        dpg.draw_circle(center=(x1, y1), radius=HANDLE_RADIUS, color=HANDLE_COLOR, fill=HANDLE_COLOR, tag="roi_tl", parent=self._drawlist)
        dpg.draw_circle(center=(x2, y1), radius=HANDLE_RADIUS, color=HANDLE_COLOR, fill=HANDLE_COLOR, tag="roi_tr", parent=self._drawlist)
        dpg.draw_circle(center=(x1, y2), radius=HANDLE_RADIUS, color=HANDLE_COLOR, fill=HANDLE_COLOR, tag="roi_bl", parent=self._drawlist)
        dpg.draw_circle(center=(x2, y2), radius=HANDLE_RADIUS, color=HANDLE_COLOR, fill=HANDLE_COLOR, tag="roi_br", parent=self._drawlist)


    def _redraw(self):
        x1, y1, x2, y2 = self._x1, self._y1, self._x2, self._y2
        dpg.configure_item(_RECT_TAG,  pmin=(x1, y1), pmax=(x2, y2))
        dpg.configure_item("roi_tl", center=(x1, y1))
        dpg.configure_item("roi_tr", center=(x2, y1))
        dpg.configure_item("roi_bl", center=(x1, y2))
        dpg.configure_item("roi_br", center=(x2, y2))


    # mouse events 
    def _mouse_local(self):
        # Mouse position relative to drawlist top-left
        mx, my   = dpg.get_mouse_pos(local=False)
        rect_min = dpg.get_item_rect_min(self._drawlist)
        return mx - rect_min[0], my - rect_min[1]


    def _over_drawlist(self):
        mx, my = self._mouse_local()
        # check if mouse is within image boundaries
        return 0 <= mx <= self._display_w and 0 <= my <= self._display_h


    def _hit_handle(self, mx, my):
        corners = {"topLeft":(self._x1,self._y1), "topRight":(self._x2,self._y1),
                   "bottomLeft":(self._x1,self._y2), "bottomRight":(self._x2,self._y2)}
        
        for name, (cx, cy) in corners.items():
            #check distance from mouse to handle center using pythago sqrt( (mx-cx)^2 + (my-cy)^2)
            if ((mx-cx)**2 + (my-cy)**2)**0.5 <= HANDLE_RADIUS + 5: # + 5 adds extra invisible clicking area around it
                return name
        return None


    def _on_mouse_down(self, s, a):
        if self._mode is not None:   # already dragging, ignore
            return
        if not self._over_drawlist(): # mouse position not on roi rectangle
            return
        
        mx, my = self._mouse_local()
        handle = self._hit_handle(mx, my)
        if handle:
            self._mode = "resizing"
            self._drag_handle = handle
        elif self._x1 <= mx <= self._x2 and self._y1 <= my <= self._y2:
            self._mode = "moving"
            self._drag_offset = (mx - self._x1, my - self._y1)

    def _on_mouse_move(self, s, a):
        if self._mode is None:
            return
        
        mx, my = self._mouse_local()
        mx = max(0, min(mx, self._display_w))
        my = max(0, min(my, self._display_h))

        if self._mode == "moving":
            ox, oy = self._drag_offset
            w = self._x2 - self._x1 #width
            h = self._y2 - self._y1 #height
            # move top-left 
            self._x1 = max(0, min(mx - ox, self._display_w - w))
            self._y1 = max(0, min(my - oy, self._display_h - h))
            # move bottom right
            self._x2 = self._x1 + w
            self._y2 = self._y1 + h
        elif self._mode == "resizing":
            min_size = 10
            if self._drag_handle == "topLeft":
                self._x1 = min(mx, self._x2 - min_size)
                self._y1 = min(my, self._y2 - min_size)
            elif self._drag_handle == "topRight":
                self._x2 = max(mx, self._x1 + min_size)
                self._y1 = min(my, self._y2 - min_size)
            elif self._drag_handle == "bottomLeft":
                self._x1 = min(mx, self._x2 - min_size)
                self._y2 = max(my, self._y1 + min_size)
            elif self._drag_handle == "bottomRight":
                self._x2 = max(mx, self._x1 + min_size)
                self._y2 = max(my, self._y1 + min_size)
        self._redraw()

    def _on_mouse_release(self, s, a):
        self._mode = None
        self._drag_handle = None