# quick camera debug script
# run this from the src folder:
# python testcam.py
#
# prints a bunch of info about the camera so we can see
# what features/nodes are actually supported

import sys
from pypylon import pylon, genicam

LINE = "=" * 60
SMALL = "-" * 40


def section(name):
    print(f"\n{SMALL}")
    print(name)
    print(SMALL)


def try_get(func, default="ERROR"):
    try:
        return func()
    except Exception as err:
        return f"{default}: {err}"


print(LINE)
print("CAMERA DEBUG")
print(LINE)

# --------------------------------------------------
# find cameras
# --------------------------------------------------

factory = pylon.TlFactory.GetInstance()
devices = factory.EnumerateDevices()

section("1. scanning for devices")

if len(devices) == 0:
    print("no cameras found")
    sys.exit(1)

for i, dev in enumerate(devices):
    print(
        f"[{i}] "
        f"{dev.GetModelName()} | "
        f"SN:{dev.GetSerialNumber()} | "
        f"{dev.GetDeviceClass()}"
    )

print(f"\nusing camera 0: {devices[0].GetModelName()}")

# --------------------------------------------------
# open camera
# --------------------------------------------------

cam = pylon.InstantCamera(factory.CreateDevice(devices[0]))
cam.Open()

section("2. camera capabilities")

print("SFNC version:", try_get(lambda: str(cam.GetSfncVersion())))
print("USB camera  :", try_get(lambda: cam.IsUsb()))
print("model       :", try_get(lambda: cam.GetDeviceInfo().GetModelName()))
print("serial      :", try_get(lambda: cam.GetDeviceInfo().GetSerialNumber()))

# chunk selector
print("\nChunkSelector:")
try:
    if genicam.IsAvailable(cam.ChunkSelector):
        for item in cam.ChunkSelector.Symbolics:
            print(" -", item)
except Exception as e:
    print(" error:", e)

# event selector
print("\nEventSelector:")
try:
    if genicam.IsAvailable(cam.EventSelector):
        for item in cam.EventSelector.Symbolics:
            print(" -", item)
except Exception as e:
    print(" error:", e)

# counters
print("\nCounterSelector:")
try:
    if genicam.IsAvailable(cam.CounterSelector):
        for item in cam.CounterSelector.Symbolics:
            print(" -", item)
except Exception as e:
    print(" error:", e)

# pixel formats
print("\nPixelFormat:")
try:
    for item in cam.PixelFormat.Symbolics:
        print(" -", item)
except Exception as e:
    print(" error:", e)

# trigger sources
print("\nTriggerSource:")
try:
    if genicam.IsAvailable(cam.TriggerSource):
        for item in cam.TriggerSource.Symbolics:
            print(" -", item)
except Exception as e:
    print(" error:", e)

# --------------------------------------------------
# timestamp / frequency nodes
# --------------------------------------------------

section("3. timestamp / clock nodes")

possible_nodes = [
    "GevTimestampTickFrequency",
    "BslTimestampFrequency",
    "BslTimestampResolution",
    "BslTimestampTickFrequency",
    "DeviceClockFrequency",
    "TimestampFrequency",
    "TimestampTickFrequency",
    "ChunkTimestampFrequency",
]

found = False

for name in possible_nodes:
    try:
        node = getattr(cam, name)

        if genicam.IsReadable(node):
            print(f"{name:40s} = {node.Value}")
        else:
            print(f"{name:40s} = not readable")

        found = True

    except Exception:
        pass

if not found:
    print("couldn't find any timestamp frequency nodes")
    print("will try to estimate timing later")

# --------------------------------------------------
# event stuff
# --------------------------------------------------

section("4. camera events")

print(
    "GrabCameraEvents available:",
    try_get(lambda: genicam.IsAvailable(cam.GrabCameraEvents))
)

print(
    "GrabCameraEvents writable :",
    try_get(lambda: genicam.IsWritable(cam.GrabCameraEvents))
)

print(
    "GrabCameraEvents current  :",
    try_get(lambda: cam.GrabCameraEvents.Value)
)

try:
    cam.GrabCameraEvents.Value = True
    print("enabled GrabCameraEvents")
except Exception as e:
    print("failed enabling GrabCameraEvents:", e)

# try enabling exposure end event
try:
    cam.EventSelector.Value = "ExposureEnd"
    cam.EventNotification.Value = "On"
    print("ExposureEnd event enabled")
except Exception as e:
    print("couldn't enable ExposureEnd:", e)

# --------------------------------------------------
# chunk data test
# --------------------------------------------------

section("5. chunk data test")

try:
    cam.ChunkModeActive.Value = True

    enabled = []
    failed = []

    if genicam.IsAvailable(cam.ChunkSelector):
        for chunk in cam.ChunkSelector.Symbolics:

            try:
                cam.ChunkSelector.Value = chunk
                cam.ChunkEnable.Value = True
                enabled.append(chunk)

            except Exception:
                failed.append(chunk)

    print("enabled chunks:", enabled)

    if failed:
        print("failed chunks :", failed)

except Exception as e:
    print("chunk setup failed:", e)

cam.StartGrabbing(pylon.GrabStrategy_OneByOne)

grab = cam.RetrieveResult(
    5000,
    pylon.TimeoutHandling_ThrowException
)

if grab.GrabSucceeded():

    arr = grab.Array

    print(
        f"\ngrab ok | "
        f"shape={arr.shape} "
        f"dtype={arr.dtype} "
        f"mean={arr.mean():.2f}"
    )

    # chunk node map
    print("\nchunk node map:")

    try:
        nodemap = grab.GetChunkDataNodeMap()

        for node in nodemap._GetNodes():

            try:
                if genicam.IsReadable(node):
                    value = node.ToString()
                else:
                    value = "not readable"

            except Exception:
                value = "error"

            print(f"{node.Node.Name:35s} = {value}")

    except Exception as e:
        print("GetChunkDataNodeMap failed:", e)

    # direct attributes
    print("\ndirect chunk attributes:")

    attrs = [
        "ChunkTimestamp",
        "ChunkFrameID",
        "ChunkFrameId",
        "ChunkFramecounter",
        "ChunkCounterValue",
        "ChunkExposureTime",
        "ChunkGain",
        "ChunkPayloadCRC16",
        "ChunkLineStatusAll",
    ]

    for attr in attrs:

        try:
            node = getattr(grab, attr)

            if genicam.IsReadable(node):
                print(f"{attr:30s} = {node.Value}")
            else:
                print(f"{attr:30s} = not readable")

        except AttributeError:
            print(f"{attr:30s} = doesn't exist")

        except Exception as e:
            print(f"{attr:30s} = error: {e}")

else:
    print("grab failed")
    print("error code:", grab.ErrorCode)
    print("description:", grab.ErrorDescription)

grab.Release()

cam.StopGrabbing()
cam.Close()

print("\nraw camera closed")

# --------------------------------------------------
# test actual Camera class
# --------------------------------------------------

section("6. testing hardware.camera.Camera")

from hardware.camera import Camera

camera = Camera(index=0)
camera.open()

print("has_camera_time   :", camera.has_camera_time())
print("has_frame_counter :", camera.has_frame_counter())
print("has_exp_end_time  :", camera.has_exp_end_time())
print("fps               :", camera.get_fps())
print("tick freq         :", camera.get_tick_frequency_hz())
print("gain              :", camera.get_gain())
print("exposure          :", camera.get_exposure_time())

print("\n8 frame test")
print(
    f"{'#':>3} "
    f"{'cam_ts':>18} "
    f"{'dt':>12} "
    f"{'fc':>8} "
    f"{'gap':>6} "
    f"{'mean':>8}"
)

last_ts = None
last_fc = None

for i in range(8):

    result = camera.grab_frame()

    if result is None:
        print(f"[{i}] no frame returned")
        continue

    frame, cam_ts, frame_counter, exp_end_ts = result

    dt = None
    gap = None

    if last_ts is not None and cam_ts is not None:
        dt = cam_ts - last_ts

    if last_fc is not None and frame_counter is not None:
        gap = frame_counter - last_fc - 1

    print(
        f"[{i:>2}] "
        f"{str(cam_ts):>18} "
        f"{str(dt):>12} "
        f"{str(frame_counter):>8} "
        f"{str(gap):>6} "
        f"{frame.mean():>8.1f}"
    )

    last_ts = cam_ts
    last_fc = frame_counter

# estimate tick frequency if camera doesn't report it
if camera.get_tick_frequency_hz() is None:

    print("\nestimating tick frequency from frame timing...")

    samples = []
    prev = None

    fps = camera.get_fps()

    for _ in range(20):

        result = camera.grab_frame()

        if result and result[1] is not None:

            ts = result[1]

            if prev is not None:
                samples.append(ts - prev)

            prev = ts

    if samples and fps:

        avg_ticks = sum(samples) / len(samples)

        expected_period = 1.0 / fps

        estimated_hz = avg_ticks / expected_period

        print("avg dt ticks :", round(avg_ticks, 1))
        print("camera fps   :", round(fps, 3))
        print("estimated hz :", round(estimated_hz))

camera.close()

print("\n" + LINE)
print("DEBUG FINISHED")
print(LINE)