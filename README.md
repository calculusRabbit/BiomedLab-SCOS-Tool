# BiomedLab SCOS Tool

A application for speckle contrast optical spectroscopy (SCOS) data acquisition, live visualization, and real-time processing.

## Features

- Real-time desktop GUI built with Dear PyGui
- Basler camera integration through `pypylon`
- Debug mode for development without physical hardware
- Threaded acquisition and processing pipeline
- Interactive ROI selection with draggable, resizable overlays
- Real-time display of acquisition outputs
- Ex: Live plots for `K²`, `BFI`, `CC`, and `OD`
- Modular architecture separating UI, control logic, hardware, state, and processing

## Architecture

The repository is organized into clear layers:

- `src/view/`  
  GUI layout and theming

- `src/controller/`  
  Event handling, UI coordination, and session control

- `src/hardware/`  
  Camera backends and threaded frame pipeline

- `src/state/`  
  Application state, per-camera sessions, ROI state, and time-series buffers

- `src/processing/`  
  Frame processing utilities and SCOS result generation

This separation keeps the interface responsive while allowing processing and hardware logic to evolve independently.

## Installation

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

If you want to use a real Basler camera, you will also need:

- Basler camera drivers/runtime
- the `pypylon` package
- a connected Basler device

## Usage

Run the application in production mode:

```bash
python src/main.py
```

Run in debug mode using a video file instead of a physical camera:

```bash
python src/main.py --debug src/debug_data/debug_1.avi
```

## Typical Workflow

1. Scan for available devices.
2. Connect to a camera.
3. Adjust gain and exposure settings.
4. Select the region of interest.
5. Start preview to begin live acquisition and visualization.
6. Monitor the live image, time-series plots, and `K²` spatial maps.

## Tech Stack

- Python
- Dear PyGui
- OpenCV
- NumPy
- Basler `pypylon`
