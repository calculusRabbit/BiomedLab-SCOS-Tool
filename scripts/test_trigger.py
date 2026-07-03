
from pylsl import StreamInlet, resolve_byprop

def main():
    print("Looking for a marker stream...")

    streams = resolve_byprop("type", "Markers")

    print(f"Found {len(streams)} stream(s)")

    if not streams:
        print("No marker streams found!")
        return

    print(f"Connecting to: {streams[0].name()}")

    inlet = StreamInlet(streams[0])

    print("Connected. Waiting for markers...")

    while True:
        sample, timestamp = inlet.pull_sample()
        print(f"Got marker: {sample} at {timestamp}")

if __name__ == "__main__":
    main()