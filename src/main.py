#
# SCOS Data Acquisition — Entry Point

# How to use:
#   python main.py # production (Basler camera)
#   python main.py --debug output.avi # debug (loops video file)
#

import sys
import dearpygui.dearpygui as dpg
from view.ui import SCOS_UI
from view.themes import create_theme
from controller.callbacks import SCOSController
from controller.camera_manager import CameraManager
from config import VIEWPORT_W, VIEWPORT_H, VIEWPORT_MIN_W, VIEWPORT_MIN_H


def main():
    # python main.py --debug output.avi
    camera_class = None
    if "--debug" in sys.argv:
        from model.debug_cam import DebugCamera
        DebugCamera.video_paths = sys.argv[2:]
        camera_class = DebugCamera
    else:
        from model.camera import Camera
        camera_class = Camera #actual camera class

    # build UI
    dpg.create_context()
    dpg.bind_theme(create_theme())

    ui = SCOS_UI()
    ui.create_ui(VIEWPORT_W, VIEWPORT_H)

    # wire controller 
    manager = CameraManager(camera_class)
    controller = SCOSController(ui, manager)
    controller.setup_callbacks()

    # lauch
    dpg.create_viewport(title="SCOS Data Acquisition",
                        width=VIEWPORT_W, height=VIEWPORT_H,
                        min_width=VIEWPORT_MIN_W, min_height=VIEWPORT_MIN_H)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(SCOS_UI.MAIN_WINDOW, True)

    # render loop
    while dpg.is_dearpygui_running():
        controller.update()
        dpg.render_dearpygui_frame()

    # cleanup
    controller.shutdown()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
