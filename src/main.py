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

VIEWPORT_W = 1280
VIEWPORT_H = 720


def main():
    # python main.py --debug output.avi
    if "--debug" in sys.argv:
        from model.debug_cam import DebugCamera
        video_path = sys.argv[2] 
        camera = DebugCamera(video_path)
    else:
        pass
        # later on actual camera will place here


    # ── build UI ──────────────────────────────────────────────
    dpg.create_context()
    dpg.bind_theme(create_theme())

    ui = SCOS_UI()
    ui.create_ui(VIEWPORT_W, VIEWPORT_H)

    # ── wire controller ───────────────────────────────────────
    controller = SCOSController(ui, camera)
    controller.setup_callbacks()

    # ── launch viewport ───────────────────────────────────────
    dpg.create_viewport(title="SCOS Data Acquisition",
                        width=VIEWPORT_W, height=VIEWPORT_H,
                        min_width=900, min_height=550)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(SCOS_UI.MAIN_WINDOW, True)

    # ── render loop ───────────────────────────────────────────
    while dpg.is_dearpygui_running():
        controller.update_UI()
        dpg.render_dearpygui_frame()

    # ── cleanup ───────────────────────────────────────────────
    controller._stop_acquisition()
    dpg.destroy_context()


if __name__ == "__main__":
    main()