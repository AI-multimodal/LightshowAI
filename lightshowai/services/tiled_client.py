import os
import queue
import threading
import atexit
import json
import pandas as pd
from tiled.client import from_uri

TILED_URL = os.getenv("TILED_URL")
TILED_API_KEY = os.environ.get("TILED_API_KEY")
XAS_SANDBOX_URL = os.environ.get("XAS_SANDBOX_URL")

if not TILED_URL:
    raise RuntimeError("TILED_URL is not set")
if not TILED_API_KEY:
    raise RuntimeError("API_KEY is not set")
if not XAS_SANDBOX_URL:
    raise RuntimeError("XAS_SANDBOX_URL is not set")

_tiled_queue = queue.Queue()
_tiled_listener_started = False
_tiled_listener_lock = threading.Lock()
_tiled_subscription = None
_tiled_client = None
_tiled_sandbox = None
_tiled_client_lock = threading.Lock()

_tiled_spectra_cache = {}
_tiled_spectra_cache_lock = threading.Lock()

def get_tiled_sandbox():
    """
    Return the shared Tiled sandbox object.
    Falls back to creating it only if the listener did not initialize it.
    """
    global _tiled_client, _tiled_sandbox

    with _tiled_client_lock:
        if _tiled_sandbox is not None:
            return _tiled_sandbox

    client = from_uri(TILED_URL, api_key=TILED_API_KEY)
    sandbox = client[XAS_SANDBOX_URL]

    with _tiled_client_lock:
        _tiled_client = client
        _tiled_sandbox = sandbox

    return sandbox

def on_new_tiled_spectrum(update):
    print("Tiled update received:", update)
    try:
        entry = update.child()
        md = getattr(entry, "metadata", {}) or {}
        md = dict(md)
        df = entry.read()
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                raise ValueError("Tiled entry did not produce a pandas DataFrame")

        spectrum_dict = df.to_dict("list")
        key = str(update.key)

        # Cache the full spectrum server-side, keyed by Tiled key.
        with _tiled_spectra_cache_lock:
            _tiled_spectra_cache[key] = {
                "metadata": md,
                "spectrum": spectrum_dict,
            }

        # Put a lightweight marker in the queue — just key + metadata,
        # NOT the spectrum itself.
        event = {
            "key": key,
            "metadata": md,
        }

        _tiled_queue.put(event)
        print(f"Queued new spectrum from Tiled: {key}")

    except Exception as e:
        print(f"Error processing Tiled update: {e}")
        import traceback
        traceback.print_exc()

def update_tiled_lightshowai_metadata(exp_data, metadata):
    """
    Update Tiled metadata for the experimental spectrum.
    """
    if exp_data is None:
        raise ValueError("No experimental spectrum loaded")

    tiled_key = exp_data.get("filename")
    if not tiled_key:
        raise ValueError("Experimental spectrum filename/key is missing")

    sandbox = get_tiled_sandbox()

    if tiled_key not in sandbox:
        raise ValueError(
            f"Could not find Tiled entry '{tiled_key}'. "
            "Metadata update only works for spectra loaded from Tiled."
        )

    src = sandbox[tiled_key]

    payload = {
        "lightshowai_analysis": metadata
    }

    print("=== Updating Tiled metadata ===")
    print(f"Tiled key: {tiled_key}")
    print(json.dumps(payload, indent=2))
    print("===============================")

    src.update_metadata(payload)

    return payload

def start_tiled_listener():
    global _tiled_listener_started, _tiled_subscription, _tiled_client, _tiled_sandbox

    with _tiled_listener_lock:
        if _tiled_listener_started:
            return

        print("Starting Tiled listener...")
        sandbox = get_tiled_sandbox()

        print("DEBUG Connected to Tiled server at", list(sandbox))

        sub = sandbox.subscribe()
        sub.child_created.add_callback(on_new_tiled_spectrum)
        sub.start_in_thread()

        _tiled_subscription = sub
        _tiled_listener_started = True
        print("Tiled listener started.")

        def _cleanup():
            global _tiled_subscription
            try:
                if _tiled_subscription is not None:
                    _tiled_subscription.disconnect()
                    print("Tiled listener disconnected.")
            except Exception as e:
                print("Error disconnecting Tiled listener:", e)

        atexit.register(_cleanup)
