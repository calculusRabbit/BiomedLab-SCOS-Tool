import dearpygui.dearpygui as dpg
from view.ui import SCOS_UI
from view.themes import create_theme

from controller.callbacks import SCOSController
from dearpygui_ext import themes

VIEWPORT_W = 1280
VIEWPORT_H = 720


def main():
    dpg.create_context()
    #dpg.set_global_font_scale(1.25)

    dpg.bind_theme(create_theme())

    # BUILD UI
    ui = SCOS_UI()
    ui.create_ui(VIEWPORT_W, VIEWPORT_H)

    # BUILD CONTRONLLER
    controller = SCOSController(ui)
    controller.setup_callbacks()

    dpg.set_viewport_resize_callback(controller.on_resize)

    # Viewport 
    dpg.create_viewport(title="SCOS Data Acquisition",
                        width=VIEWPORT_W, height=VIEWPORT_H,
                        min_width=900, min_height=550)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(SCOS_UI.MAIN_WINDOW, True)

    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()