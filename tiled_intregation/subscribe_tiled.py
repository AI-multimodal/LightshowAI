
import signal
import sys
import time
from datetime import datetime

from importlib_metadata import metadata

from tiled.client import from_uri

TILED_URL = "http://localhost:8000"
API_KEY = "secret"


def on_new_spectrum(update):
    print("=======", update)
    try:
        entry = update.child()
    

        now = datetime.now().strftime("%H:%M:%S")

        print(f"\n[{now}] New spectrum: {update.key}")

        metadata = entry.metadata
        # print("  Metadata:")
        # for k, v in metadata.items():
        #     print(f" Key   {k}: Value {v}")

        df = entry.read()
        print(f"  {len(df)} data points, columns: {list(df.columns)}")
        print(f"  Preview:")
        print(df.head(3).to_string(index=False))
    except Exception as e:
            print(f"Error occurred while processing update: {e}")
            return

def main():
    print("Connecting to Tiled server...")
    client = from_uri(TILED_URL, api_key=API_KEY)

    existing = list(client)
    print(f"Found {len(existing)} existing entries: {existing}")

    sub = client.subscribe()
    sub.child_created.add_callback(on_new_spectrum)
    sub.start_in_thread()

    print("\nWaiting for new spectra... (Ctrl+C to stop)\n")

    signal.signal(signal.SIGINT, lambda *_: (sub.disconnect(), sys.exit(0)))

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()