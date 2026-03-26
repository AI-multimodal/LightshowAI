#!/usr/bin/env python
"""
Manage Tiled catalog entries.

Usage:
    python manage_catalog.py              # list all entries
    python manage_catalog.py delete key1  # delete one entry
    python manage_catalog.py delete --all # delete everything
"""

import sys
from tiled.client import from_uri

TILED_URL = "http://localhost:8000"
API_KEY = "secret"


def main():
    client = from_uri(TILED_URL, api_key=API_KEY)
    entries = list(client)

    # No arguments — just list
    if len(sys.argv) < 2:
        print(f"Catalog has {len(entries)} entries:\n")
        for key in entries:
            try:
                meta = client[key].metadata
                element = meta.get("Element.symbol", "")
                edge = meta.get("Element.edge", "")
                label = f"  ({element} {edge})" if element or edge else ""
                print(f"  {key}{label}")
            except Exception:
                print(f"  {key}  (cannot read)")
        return

    command = sys.argv[1]

    if command == "delete":
        if "--all" in sys.argv:
            if not entries:
                print("Catalog is already empty.")
                return
            confirm = input(f"Delete all {len(entries)} entries? (yes/no): ")
            if confirm.strip().lower() != "yes":
                print("Cancelled.")
                return
            for key in entries:
                client[key].delete()
                print(f"  Deleted: {key}")
            print(f"\nDone. Removed {len(entries)} entries.")

        elif len(sys.argv) >= 3:
            keys_to_delete = sys.argv[2:]
            for key in keys_to_delete:
                if key in entries:
                    client[key].delete()
                    print(f"  Deleted: {key}")
                else:
                    print(f"  Not found: {key}")

        else:
            print("Usage:")
            print("  python manage_catalog.py delete key1 key2")
            print("  python manage_catalog.py delete --all")

    else:
        print(f"Unknown command: {command}")
        print("Commands: delete")


if __name__ == "__main__":
    main()