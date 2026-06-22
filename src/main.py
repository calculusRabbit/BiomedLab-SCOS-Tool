# Entry point for the SCOS data acquisition app.
#
# Usage:
#   python main.py                        # production (Basler camera)
#   python main.py --debug path/to/frames # debug mode, loops PNG frames from a folder
#
# Startup order matters: UI widgets must be created before the viewport is shown,
# then state and hardware objects are created, then everything is wired together.

import sys
import dearpygui.dearpygui as dpg

from view.ui import SCOS_UI
from view.themes import create_theme
from controller.ui_controller import UIController
from controller.camera_manager import CameraManager
from state.app_state import AppState
from config import VIEWPORT_W, VIEWPORT_H, VIEWPORT_MIN_W, VIEWPORT_MIN_H


def main():
    # swap in a fake camera that replays PNG files, useful for testing without hardware
    if "--debug" in sys.argv:
        from hardware.debug_cam import DebugCamera
        DebugCamera.folder_paths = sys.argv[2:]
        camera_class = DebugCamera
    else:
        from hardware.camera import Camera
        camera_class = Camera

    dpg.create_context()
    dpg.bind_theme(create_theme())

    ui = SCOS_UI()
    ui.create_ui(VIEWPORT_W, VIEWPORT_H)

    app_state = AppState()
    manager = CameraManager(camera_class)
    controller = UIController(ui, manager, app_state)
    controller.setup()

    dpg.create_viewport(
        title = "SCOS Data Acquisition",
        width = VIEWPORT_W,
        height = VIEWPORT_H,
        min_width = VIEWPORT_MIN_W,
        min_height= VIEWPORT_MIN_H,
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(SCOS_UI.MAIN_WINDOW, True)

    # main render loop, controller.update() pulls new frames and refreshes the UI each tick
    while dpg.is_dearpygui_running():
        controller.update()
        dpg.render_dearpygui_frame()

    controller.shutdown()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
