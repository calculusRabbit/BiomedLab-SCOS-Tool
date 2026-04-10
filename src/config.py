# All constants live here. Import from here everywhere else.

# Viewport
VIEWPORT_W = 1280
VIEWPORT_H = 720
VIEWPORT_MIN_W = 900
VIEWPORT_MIN_H = 550

# Real camera sensor resolution (used for ROI pixel calculations)
CAMERA_W = 1920
CAMERA_H = 1200
CAMERA_PIXEL_FORMAT = "Mono8" # Mono 8 => range(0-255)  ||  Mono 12 => range(0-4095) but 2x slower transfer, but also MOST DETAIL

# Derived from bit depth — used for normalization
CAMERA_BIT_DEPTH = 8  # change to 10 or 12 if needed but have to be match above CAMERA_PIXEL_FORMAT
CAMERA_PIXEL_MAX = float(2**CAMERA_BIT_DEPTH - 1) # 255.0, 1023.0, 4095.0

# Display texture resolution (used for live feed display)
TEXTURE_W = 1920
TEXTURE_H = 1200

#k2 6 map
K2_TEXTURE_W = 2**7 #128
K2_TEXTURE_H = 2**7

# Scrolling plot
MAX_PLOT_POINTS = 1000 # change to None for inifinity
PLOT_WINDOW_SEC = 10.0

# UI layout
PADDING = 8
ITEM_SPACING = 6
CAM_HEIGHT_RATIO = 0.28
DEVICE_WIDTH_RATIO = 0.58
ROI_BTN_HEIGHT = 32


HANDLE_RADIUS = 6

# Camera defaults
CAMERA_DEFAULT_GAIN = 10.0
CAMERA_DEFAULT_EXPOSURE = 20000.0

# Add a new ROI by adding one entry here — name: RGBA color tuple.
# The default position for each ROI lives in state/roi_set.py _DEFAULTS.
ROI_CONFIGS = {
    "source":   (255, 0,   0,   255),  # red
    "detector": (0,   120, 255, 255),  # blue
}
