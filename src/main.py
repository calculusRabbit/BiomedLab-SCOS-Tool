import dearpygui.dearpygui as dpg
from view.ui import SCOS_UI
from view.themes import create_theme
from controller.callbacks import SCOSController

VIEWPORT_W = 1280
VIEWPORT_H = 720


def main():
    dpg.create_context()
    dpg.bind_theme(create_theme())

    ui = SCOS_UI()
    ui.create_ui(VIEWPORT_W, VIEWPORT_H)

    controller = SCOSController(ui)
    controller.setup_callbacks()
    dpg.set_viewport_resize_callback(controller.on_resize)

    dpg.create_viewport(title="SCOS Data Acquisition",
                        width=VIEWPORT_W, height=VIEWPORT_H,
                        min_width=900, min_height=550)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(SCOS_UI.MAIN_WINDOW, True)

    while dpg.is_dearpygui_running():
        controller.update()
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    main()