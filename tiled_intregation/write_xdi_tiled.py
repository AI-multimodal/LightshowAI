#!/usr/bin/env python
"""
Sends XDI files to the Tiled server.

Usage:
    python write_xdi_to_tiled.py spectrum.xdi
    python write_xdi_to_tiled.py /path/to/folder/
"""

import sys
from pathlib import Path
from datetime import datetime

from tiled.client import from_uri

TILED_URL = "http://localhost:8000"
API_KEY = "secret"

# Reuse the parser from xdi_adapter
sys.path.insert(0, str(Path(__file__).parent))
from xdi_adapter import _parse_xdi


def send_file(client, xdi_path: Path):
    """Parse one XDI file and write it to Tiled."""
    key = xdi_path.stem
    print(f"\nProcessing {xdi_path.name} with key '{key}'...")
    now = datetime.now().strftime("%H:%M:%S")

    if key in client:
        print(f"  [{now}] {xdi_path.name} — already in Tiled, skipping")
        return

    df, metadata = _parse_xdi(str(xdi_path))

    if df.empty:
        print(f"  [{now}] {xdi_path.name} — no data found, skipping")
        return

    client.write_table(df, key=key, metadata=metadata)
    print(f"  [{now}] {xdi_path.name} — written to Tiled")


def main():
    if len(sys.argv) < 2:
        print("Usage: python write_xdi_to_tiled.py <file.xdi or folder>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_file() and target.suffix == ".xdi":
        files = [target]
    elif target.is_dir():
        files = sorted(target.glob("*.xdi"))
    else:
        print(f"Not a valid .xdi file or folder: {target}")
        sys.exit(1)

    if not files:
        print(f"No .xdi files found in {target}")
        sys.exit(1)

    print(f"Connecting to Tiled server at {TILED_URL}...")
    client = from_uri(TILED_URL, api_key=API_KEY)

    print(f"Sending {len(files)} file(s):\n")
    for f in files:
        send_file(client, f)

    print(f"\nDone. Tiled now has {len(list(client))} entries total.")


if __name__ == "__main__":
    main()