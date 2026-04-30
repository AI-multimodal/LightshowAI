import numpy as np

def _patch_pymatgen_neighbors():
    try:
        from pymatgen.optimization import neighbors as pmg_neighbors
        _original_find_points = pmg_neighbors.find_points_in_spheres

        def _patched_find_points_in_spheres(
            all_coords, center_coords, r, pbc, lattice, tol=1e-8
        ):
            pbc = np.asarray(pbc, dtype=np.int64)
            return _original_find_points(
                all_coords, center_coords, r, pbc, lattice, tol
            )

        pmg_neighbors.find_points_in_spheres = _patched_find_points_in_spheres
        # print("Applied Windows int64 compatibility patch for pymatgen")
    except Exception as e:
        print(f"Warning: Could not apply pymatgen patch: {e}")

_patch_pymatgen_neighbors()


from base64 import b64encode, b64decode
import os
import io
import tempfile
import pathlib
from zipfile import ZipFile
import re
import pandas as pd
import numpy as np
import dash
from dash import dcc, html
import plotly.express as px
import plotly.graph_objects as go
import json

from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
from pymatgen.core.structure import Structure
from mp_api.client import MPRester
from datetime import timedelta
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

import crystal_toolkit.components as ctc
from crystal_toolkit.helpers.layouts import (
    Box,
    Column,
    Columns,
    Loading
)

from lightshowai.models import predict
from lightshowai.postprocess import compare_utils
from lightshowai.postprocess.normalize import normalizeSpectrum, spectrum_from_new_csv
from lightshowai.postprocess.shakeup import loadShakeupKernel, shakeup as shakeupSpectrum
from datetime import datetime

_DAT_PATH = pathlib.Path(__file__).parent / "postprocess" / "Rutile-spfcn_model.dat"
_Aw = loadShakeupKernel(str(_DAT_PATH))

import redis
import threading
import queue
import atexit
from datetime import datetime

from tiled.client import from_uri
from lightshowai.auth import init_auth, get_current_user

TILED_URL = os.getenv("TILED_URL")
TILED_API_KEY = os.environ["TILED_API_KEY"]
XAS_SANDBOX_URL = os.environ["XAS_SANDBOX_URL"]
CHATBOT_URL = os.getenv("OMNIXAS_CHATBOT_URL", "https://localhost:8445")

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


app = dash.Dash(prevent_initial_callbacks=True, title="OmniXAS@Lightshow.ai",
                url_base_pathname="/omnixas/")
server = app.server
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)

# visitor count code
# decode_responses=False: Flask-Session stores pickled bytes and needs raw
# bytes back. Any future code that stores strings in Redis should decode
# explicitly on read: redis_client.get("some:key").decode("utf-8")
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "127.0.0.1"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    username=os.environ.get("REDIS_USER") or None,
    password=os.environ.get("REDIS_PASSWORD") or None,
    decode_responses=False
)

# Flask secret key — required for signing session cookies
_flask_secret = os.environ.get("FLASK_SECRET_KEY")
if not _flask_secret:
    raise RuntimeError("FLASK_SECRET_KEY is not set")

server.config.update(
    SECRET_KEY=_flask_secret,
    # Server-side sessions stored in Redis
    SESSION_TYPE="redis",
    SESSION_REDIS=redis_client,
    SESSION_KEY_PREFIX="omnixas:session:",   # namespace to avoid collisions
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_USE_SIGNER=True,                  # sign the session ID cookie
    # Cookie hardening
    SESSION_COOKIE_NAME="omnixas_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("OMNIXAS_COOKIE_SECURE", "true").lower() == "true",
)

Session(server)
init_auth(server)

# return amount of visitors, and update count
@server.route("/visitor-count")
def _visitor_count():
    try:
        count = redis_client.incr("app:visitor_count")

    except redis.RedisError as e:
        print(f"Redis error: {e}")
        return '{"error": "Database unavailable"}', 503, {"Content-Type": "application/json"}

    return f'{{"count": {count}}}', 200, {"Content-Type": "application/json"}

# Common styles
base_font = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

section_header_style = {
    "fontWeight": "700",
    "fontSize": "16px",
    "color": "#222",
    "marginBottom": "14px",
    "paddingBottom": "10px",
    "borderBottom": "2px solid #ddd",
    "fontFamily": base_font,
    "letterSpacing": "0.2px"
}

column_header_style = {
    "fontWeight": "700",
    "fontSize": "16px",
    "color": "#111",
    "marginBottom": "14px",
    "paddingBottom": "10px",
    "borderBottom": "2px solid #ddd",
    "fontFamily": base_font,
    "letterSpacing": "0.1px"
}

input_label_style = {
    "fontSize": "13px",
    "color": "#444",
    "marginBottom": "6px",
    "fontWeight": "600",
    "fontFamily": base_font
}

card_style = {
    "backgroundColor": "white",
    "borderRadius": "8px",
    "padding": "18px",
    "marginBottom": "12px",
    "border": "1px solid #e8e8e8"
}

button_primary_style = {
    'padding': '12px 24px',
    'fontSize': '14px',
    'border': 'none',
    'borderRadius': '6px',
    'backgroundColor': '#333',
    'color': 'white',
    'cursor': 'pointer',
    'fontWeight': '600',
    'marginRight': '8px',
    'letterSpacing': '0.3px',
    'fontFamily': base_font
}

button_secondary_style = {
    'padding': '8px 16px',
    'fontSize': '12px',
    'border': '1px solid #ddd',
    'borderRadius': '6px',
    'backgroundColor': 'white',
    'color': '#666',
    'cursor': 'pointer',
    'fontFamily': base_font
}

_radio_base = {
    'flex': '1', 'height': '40px', 'padding': '0',
    'cursor': 'pointer', 'fontSize': '13px',
    'fontFamily': base_font, 'boxSizing': 'border-box'
}

radio_left_active_style = {
    **_radio_base,
    'border': '1px solid #333', 'borderRight': 'none',
    'backgroundColor': '#333', 'color': 'white',
    'borderRadius': '6px 0 0 6px', 'fontWeight': '600'
}

radio_left_inactive_style = {
    **_radio_base,
    'border': '1px solid #ddd', 'borderRight': 'none',
    'backgroundColor': 'white', 'color': '#666',
    'borderRadius': '6px 0 0 6px', 'fontWeight': '400'
}

radio_right_active_style = {
    **_radio_base,
    'border': '1px solid #333',
    'backgroundColor': '#333', 'color': 'white',
    'borderRadius': '0 6px 6px 0', 'fontWeight': '600'
}

radio_right_inactive_style = {
    **_radio_base,
    'border': '1px solid #ddd',
    'backgroundColor': 'white', 'color': '#666',
    'borderRadius': '0 6px 6px 0', 'fontWeight': '400'
}

radio_row_style = {'display': 'flex', 'width': '100%', 'marginBottom': '15px'}

radio_label_style = {'fontSize': '11px', 'display': 'block', 'marginBottom': '4px', 'color': '#666'}

struct_component = ctc.StructureMoleculeComponent(id="st_vis",
                                                  show_image_button=False,
                                                  show_export_button=False)

upload_component = ctc.StructureMoleculeUploadComponent(id='file_loader')

# Combined single/multiple structure upload component
batch_upload_component = dcc.Upload(
    id='batch_structure_upload',
    children=html.Div([
        html.Div([
            'Drag & Drop or ',
            html.A('Select File(s)', style={'color': '#222', 'cursor': 'pointer', 'fontWeight': '600', 'textDecoration': 'underline'})
        ])
    ]),
    style={
        'width': '100%',
        'height': '50px',
        'lineHeight': '50px',
        'borderWidth': '1px',
        'borderStyle': 'dashed',
        'borderColor': '#d0d0d0',
        'borderRadius': '6px',
        'textAlign': 'center',
        'backgroundColor': '#fafafa',
        'cursor': 'pointer',
        'color': '#666',
        'fontSize': '13px',
        'fontFamily': base_font
    },
    multiple=True,  # Allow single or multiple file selection
    accept='.cif,.vasp,.poscar,.json'
)

shakeup_store = dcc.Store(id='shakeup-store', data='no')

# Store for batch processing status
batch_processing_store = dcc.Store(id='batch_processing_store', data={'status': 'idle', 'processed': 0, 'total': 0})

xas_plot = dcc.Graph(
    id='xas_plot',
    style={'height': '420px'},
    config={'responsive': True, 'doubleClick': 'reset'}
)
st_source = html.Div(id='st_source', children='No structure loaded yet',
                     style={'fontSize': '13px', 'color': '#555', 'fontWeight': '500', 'fontFamily': base_font})

all_elements = ['Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu']
ene_start = {'Ti': 4964.504, 'V': 5464.097, 'Cr': 5989.168, 'Mn': 6537.886,
             'Fe': 7111.23, 'Co': 7709.282, 'Ni': 8332.181, 'Cu': 8983.173}
ene_grid = {el: np.linspace(start, start + 35, 141) for el, start in ene_start.items()}
xas_model_names = [f'{el} FEFF' for el in all_elements] + ['Ti VASP', 'Cu VASP']
absorber_dropdown = dcc.Dropdown(xas_model_names, clearable=False, value='Ti VASP', id='absorber')

# All available metrics for display
ALL_METRICS = ["coss_deriv", "pearson", "spearman", "coss", "kendalltaub", "normed_wasserstein"]

# Short display names for table headers
METRIC_SHORT_NAMES = {
    "coss_deriv": "Cos(∂)",
    "pearson": "Pearson",
    "spearman": "Spearman",
    "coss": "Cosine",
    "kendalltaub": "Kendall",
    "normed_wasserstein": "Wasser.",
}

# radio button helpers
def _radio_btn_styles(is_left_active, left_extra=None, right_extra=None):
    left  = {**(radio_left_active_style   if is_left_active else radio_left_inactive_style),  **(left_extra  or {})}
    right = {**(radio_right_inactive_style if is_left_active else radio_right_active_style),   **(right_extra or {})}
    return left, right

def _radio_callback(btn_left_id, btn_right_id, val_left, val_right, current_val):
    """
    Resolve the new toggle value given which button was clicked.
    Returns the new value string.
    """
    ctx = dash.callback_context
    if ctx.triggered:
        tid = ctx.triggered[0]['prop_id'].split('.')[0]
        if tid == btn_left_id:
            return val_left
        if tid == btn_right_id:
            return val_right
    return current_val

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

def get_current_structure_label(st_data, structure_source=None):
    """
    Return a clean structure label for plot legends.

    Prefer labels stored directly on the structure dict. Fall back to parsing
    st_source only for older paths.
    """
    if isinstance(st_data, dict):
        for key in ("label", "structure_id", "filename", "material_id"):
            value = st_data.get(key)
            if value:
                return str(value)

    if structure_source and isinstance(structure_source, str):
        if structure_source.startswith("Current structure:"):
            return structure_source.split(":", 1)[1].strip()

        # Avoid using batch summary text as a legend label.
        if structure_source.startswith("Batch loaded:") or structure_source.startswith("Loaded "):
            return None

        return structure_source

    return None

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
try:
    start_tiled_listener()
except Exception as e:
    print(f"Failed to start Tiled listener: {e}")

def get_spectrum_match_score(predicted_spectrum, exp_spectrum, element):
    """
    Compare predicted spectrum against experimental spectrum using
    lightshow.postprocess.compare_utils.compare_between_spectra.

    Returns comparison_range which is the energy range used for comparison.
    """
    try:
        ene = ene_grid[element]
        ml_spectrum = np.column_stack((ene, predicted_spectrum))
        exp_energy = np.array(exp_spectrum['energy'])
        exp_absorption = np.array(exp_spectrum['absorption'])
        expt_spectrum = np.column_stack((exp_energy, exp_absorption))

        opt_metric = "coss_deriv"
        other_metrics = ["pearson", "spearman", "coss", "kendalltaub", "coss_deriv", "normed_wasserstein"]

        erange = 35
        erange_threshold = 0.04
        truncation_strategy = "from_spect2"
        erange_lbound_delta = 5

        correlations, shift = compare_utils.compare_between_spectra(
            expt_spectrum,
            ml_spectrum,
            erange=erange,
            erange_threshold=erange_threshold,
            erange_lbound_delta=erange_lbound_delta,
            truncation_strategy=truncation_strategy,
            grid_interpolator=compare_utils.gridInterpolatorFixedSpacing(0.25),
            output_correlations=other_metrics,
            opt_strategy="grid_search_and_local_opt",
            accuracy=0.1,
            method=opt_metric,
            norm_y_axis=True
        )

        # Calculate the comparison range
        # The shift returned aligns ML spectrum to experimental spectrum
        # ML spectrum energy range after shift: (ene + shift)
        # The comparison uses erange (35 eV) starting from edge

        # For ML spectrum (spect2), find where edge starts
        ml_y_normalized = (ml_spectrum[:, 1] - np.min(ml_spectrum[:, 1])) / (np.max(ml_spectrum[:, 1]) - np.min(ml_spectrum[:, 1]))
        ml_edge_idx = np.argmax(ml_y_normalized > erange_threshold)
        ml_edge_energy = ml_spectrum[ml_edge_idx, 0]

        # The comparison range in the EXPERIMENTAL spectrum's energy scale
        # ML edge energy + shift = where ML edge aligns in exp energy scale
        comparison_start = ml_edge_energy + shift
        comparison_end = comparison_start + erange

        # Debug output
        # print(f"=== Comparison Range Debug ===")
        # print(f"ML edge energy: {ml_edge_energy:.1f} eV")
        # print(f"Shift: {shift:.2f} eV")
        # print(f"Comparison range: {comparison_start:.1f} - {comparison_end:.1f} eV")

        score = correlations.get(opt_metric, 0.0)
        if np.isnan(score) or np.isinf(score):
            score = 0.0

        return {
            'score': round(float(score), 3),
            'correlations': {k: round(float(v), 3) if not (np.isnan(v) or np.isinf(v)) else 0.0
                           for k, v in correlations.items()},
            'shift': round(float(shift), 2),
            'comparison_range': (round(float(comparison_start), 1), round(float(comparison_end), 1))
        }

    except Exception as e:
        print(f"Error in spectrum matching: {e}")
        import traceback
        traceback.print_exc()
        return {
            'score': 0.0,
            'correlations': {},
            'shift': 0.0,
            'comparison_range': None
        }


# Store for matching results
matching_results_store = dcc.Store(id='matching_results_store', data=[])
structure_scores_store = dcc.Store(id='structure_scores_store', data=[])
comparison_range_store = dcc.Store(id='comparison_range_store', data=None)
selected_spectra_store = dcc.Store(id='selected_spectra_store', data=[])
sort_metric_store = dcc.Store(id='sort_metric_store', data='coss_deriv')

# Custom experimental spectrum upload component
exp_upload_component = dcc.Upload(
    id='exp_spectrum_upload',
    children=html.Div([
        html.Div([
            'Drag and Drop or ',
            html.A('Select File', style={'color': '#222', 'cursor': 'pointer', 'fontWeight': '600', 'textDecoration': 'underline'})
        ])
    ]),
    style={
        'width': '100%',
        'height': '50px',
        'lineHeight': '50px',
        'borderWidth': '1px',
        'borderStyle': 'dashed',
        'borderColor': '#d0d0d0',
        'borderRadius': '6px',
        'textAlign': 'center',
        'backgroundColor': '#fafafa',
        'cursor': 'pointer',
        'color': '#666',
        'fontSize': '13px',
        'fontFamily': base_font
    },
    multiple=False,
    accept='.dat,.mat,.csv,.xdi'
)

# Input for material name
exp_material_name_input = dcc.Input(
    id='exp_material_name',
    type='text',
    placeholder='e.g., Anatase TiO2',
    style={
        'width': '100%',
        'padding': '10px 12px',
        'borderRadius': '6px',
        'border': '1px solid #ddd',
        'fontSize': '12px',
        'boxSizing': 'border-box',
        'fontFamily': base_font
    }
)

mpid_list_input = dcc.Textarea(
    id="mpid_list_input",
    placeholder="Enter MP IDs separated by commas, spaces, or new lines\nExample:\nmp-390, mp-2657\nmp-5827",
    style={
        "width": "100%",
        "height": "90px",
        "padding": "10px 12px",
        "borderRadius": "6px",
        "border": "1px solid #ddd",
        "fontSize": "12px",
        "boxSizing": "border-box",
        "fontFamily": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    }
)

mpid_search_btn = html.Button(
    "Search MP IDs",
    id="mpid_search_btn",
    style={
        'padding': '8px 16px',
        'fontSize': '12px',
        'border': 'none',
        'borderRadius': '6px',
        'backgroundColor': '#333',
        'color': 'white',
        'cursor': 'pointer',
        'fontWeight': '500',
        'marginTop': '8px',
        'fontFamily': "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    }
)

# Store for raw file data (before column selection)
exp_raw_data_store = dcc.Store(id='exp_raw_data_store', data=None)

# Store for column definitions
exp_columns_store = dcc.Store(id='exp_columns_store', data=None)

# Store for final experimental spectrum data
exp_spectrum_store = dcc.Store(id='exp_spectrum_store', data=None)

# Dynamic column definition area
exp_column_definition_area = html.Div(
    id='exp_column_definition_area',
    children=[],
    style={'marginTop': '10px'}
)

# Dropdown for X-axis column selection
exp_x_axis_dropdown = dcc.Dropdown(
    id='exp_x_axis_dropdown',
    options=[],
    placeholder='Select X-axis column',
    style={'marginBottom': '8px'}
)

# Dropdown for Y-axis column selection
exp_y_axis_dropdown = dcc.Dropdown(
    id='exp_y_axis_dropdown',
    options=[],
    placeholder='Select Y-axis column',
    style={'marginBottom': '8px'}
)

exp_raw_energy_dropdown = dcc.Dropdown(
    id='exp_raw_energy_dropdown',
    options=[],
    placeholder='Select Energy column',
    clearable=True,
    style={'fontSize': '12px'}
)

exp_raw_itiff_dropdown = dcc.Dropdown(
    id='exp_raw_itiff_dropdown',
    options=[],
    placeholder='Select It / Iff column',
    clearable=True,
    style={'fontSize': '12px'}
)

exp_raw_i0_dropdown = dcc.Dropdown(
    id='exp_raw_i0_dropdown',
    options=[],
    placeholder='Select I0 column',
    clearable=True,
    style={'fontSize': '12px'}
)

# Button to apply column selection and plot
exp_apply_btn = html.Button(
    "Apply & Plot",
    id="exp_apply_btn",
    style={
        **button_primary_style,
        "width": "48%",
        "height": "40px",
        "padding": "0",
        "marginTop": "6px",
        "fontSize": "13px",
        "marginRight": "4%",
        "display": "inline-block",
        "boxSizing": "border-box",
        "verticalAlign": "top"
    }
)

clear_exp_btn = html.Button(
    "Clear",
    id="clear_exp_btn",
    style={
        **button_secondary_style,
        "width": "48%",
        "height": "40px",
        "padding": "0",
        "marginTop": "6px",
        "fontSize": "13px",
        "marginRight": "0",
        "display": "inline-block",
        "boxSizing": "border-box",
        "verticalAlign": "top"
    }
)

# Display for uploaded experimental file info
exp_file_info = html.Div(id='exp_file_info', children='No experimental spectrum loaded',
                         style={
                             'fontSize': '11px',
                             'color': '#888',
                             'marginTop': '10px',
                             'fontFamily': base_font
                         })

tiled_poll_interval = dcc.Interval(
    id="tiled_poll_interval",
    interval=1000,   # 1 second
    n_intervals=0
)

# tiled_live_store = dcc.Store(id="tiled_live_store", data=None)

# List of pending spectra from Tiled, newest-first. Each entry has the shape:
#   {"key": str, "metadata": dict, "spectrum": dict, "arrived_at": iso-timestamp}
# Per-Dash-session, so each user has their own pending list.
pending_spectra_store = dcc.Store(id="pending_spectra_store", data=[])

# Marks the origin of the most recent raw_data population.
# "pending" = from a pending-entry load, "manual" = from file upload, None = initial.
# Used by auto_apply_pending_load to decide whether to auto-trigger Apply & Plot.
last_load_source_store = dcc.Store(id="last_load_source_store", data=None)

def parse_mpid_list(value):
    if not value:
        return []

    if isinstance(value, list):
        text = " ".join(str(x) for x in value if x)
    else:
        text = str(value)

    mpids = re.findall(r"mp-\d+", text)

    # de-duplicate while preserving order
    seen = set()
    result = []
    for mpid in mpids:
        if mpid not in seen:
            seen.add(mpid)
            result.append(mpid)

    return result

def _format_pending_label(entry):
    """Build the dropdown label for a pending entry: 'Key • HH:MM Day'."""
    key = entry.get("key", "unknown")
    try:
        arrived = datetime.fromisoformat(entry["arrived_at"])
        label_time = arrived.strftime("%H:%M %a")
    except (KeyError, ValueError):
        label_time = ""
    return f"{key} • {label_time}" if label_time else key

def _load_pending_entry(entry):
    """
    Translate a pending Tiled entry into the outputs needed to populate
    the experimental-spectrum UI. Spectrum data is fetched from the
    server-side cache by key.
    """
    key = entry["key"]

    with _tiled_spectra_cache_lock:
        cached = _tiled_spectra_cache.get(key)

    if cached is None:
        # Spectrum was dropped from cache — shouldn't happen in practice,
        # but don't crash. Return empty load.
        return (
                None,               # exp_raw_data_store
                None,               # exp_columns_store
                [],                 # exp_x_axis_dropdown options
                [],                 # exp_y_axis_dropdown options
                None,               # exp_x_axis_dropdown value
                None,               # exp_y_axis_dropdown value
                {"display": "none"},
                [],
                html.Span(f"Spectrum {key} no longer available", style={"color": "red"}),
                "",
                "norm",
                [],                 # exp_raw_energy_dropdown options
                [],                 # exp_raw_itiff_dropdown options
                [],                 # exp_raw_i0_dropdown options
                None,               # exp_raw_energy_dropdown value
                None,               # exp_raw_itiff_dropdown value
                None,               # exp_raw_i0_dropdown value
                None,               # exp_spectrum_store
            )

    spec = cached["spectrum"]
    md = cached["metadata"]
    material_name = md.get("Sample.name", "") or key

    col_names = list(spec.keys())
    data = [[float(v) for v in spec[name]] for name in col_names]
    columns = [
        {"index": i, "name": name, "num_values": len(data[i]),
         "sample_values": data[i][:5]}
        for i, name in enumerate(col_names)
    ]

    lower = [n.lower().strip() for n in col_names]
    auto_x = lower.index("energy") if "energy" in lower else 0
    auto_y = next(
        (i for i, n in enumerate(lower) if n in ("iff", "it", "if", "ir")),
        1,
    )
    is_new_csv = (
        "energy" in lower
        and "i0" in lower
        and any(c in lower for c in ("iff", "it", "ir"))
    )

    raw_data = {
        "columns": columns,
        "data": data,
        "filename": key,
        "auto_x_col": auto_x,
        "auto_y_col": auto_y,
        "detected_format": "new_xas_csv" if is_new_csv else "generic_csv",
    }

    options, col_definition, info_text = _build_column_ui(
    columns, key, auto_x, auto_y
    )

    raw_options, raw_energy_val, raw_itiff_val, raw_i0_val = _raw_dropdown_defaults(
        columns,
        raw_type='transmission'
    )

    default_data_type = 'raw' if is_new_csv else 'norm'

    return (
        raw_data,
        columns,
        options,
        options,
        auto_x,
        auto_y,
        {"display": "block"},
        col_definition,
        html.Span(info_text, style={"color": "blue"}),
        material_name,
        default_data_type,
        raw_options,
        raw_options,
        raw_options,
        raw_energy_val,
        raw_itiff_val,
        raw_i0_val,
        None,  # clear exp_spectrum_store until Apply runs
    )

onmixas_layout = html.Div([
    tiled_poll_interval,
    # tiled_live_store,
    pending_spectra_store,
    last_load_source_store,
    # Main content area
    Columns([
        # Column 1: Input Controls
        Column(
            [
                # Experimental Spectrum Upload Card
                html.Div([
                    html.Div("Upload Experimental Spectrum", style=section_header_style),
                   html.Div(
                        id="pending_spectra_section",
                        children=[
                            html.Div(
                                id="pending_spectra_header",
                                children="",
                                style={
                                    **input_label_style,
                                    "color": "#1a73e8",
                                    "marginBottom": "8px",
                                }
                            ),
                            html.Div([
                                html.Div(
                                    dcc.Dropdown(
                                        id="pending_spectra_dropdown",
                                        options=[],
                                        value=None,
                                        clearable=False,
                                        style={"fontSize": "12px"}
                                    ),
                                    style={"marginBottom": "8px"}
                                ),
                                html.Div([
                                    html.Button(
                                        "Load",
                                        id="pending_load_btn",
                                        n_clicks=0,
                                        style={
                                            **button_primary_style,
                                            "width": "48%",
                                            "height": "36px",
                                            "padding": "0",
                                            "fontSize": "12px",
                                            "marginRight": "4%",
                                        }
                                    ),
                                    html.Button(
                                        "Dismiss",
                                        id="pending_dismiss_btn",
                                        n_clicks=0,
                                        style={
                                            **button_secondary_style,
                                            "width": "48%",
                                            "height": "36px",
                                            "padding": "0",
                                            "fontSize": "12px",
                                        }
                                    ),
                                ]),
                            ], style={
                                "backgroundColor": "#f0f7ff",
                                "border": "1px solid #c5dcf5",
                                "borderRadius": "6px",
                                "padding": "12px",
                            }),
                        ],
                        style={"display": "none"}
                    ),

                    html.Div("Material Name (optional):", style=input_label_style),
                    exp_material_name_input,

                    html.Div(
                        "Accepted formats: .csv, .dat, .mat, .xdi",
                        style={"fontSize": "11px", "color": "#999", "marginTop": "10px", "marginBottom": "8px"}
                    ),

                    exp_upload_component,
                    exp_column_definition_area,

                    html.Div(
                        id='exp_column_selection_area',
                        children=[
                            html.Div("Select columns to plot:", style={**input_label_style, "marginTop": "12px"}),
                            html.Div([
                                html.Div([
                                    html.Div([
                                        html.Span(
                                            "X-axis:",
                                            style={"fontSize": "11px", "display": "block", "marginBottom": "4px", "color": "#666"}
                                        ),
                                        exp_x_axis_dropdown,
                                    ], style={"display": "inline-block", "width": "48%", "marginRight": "4%", "verticalAlign": "top"}),

                                    html.Div([
                                        html.Span(
                                            "Y-axis:",
                                            style={"fontSize": "11px", "display": "block", "marginBottom": "4px", "color": "#666"}
                                        ),
                                        exp_y_axis_dropdown,
                                    ], style={"display": "inline-block", "width": "48%", "verticalAlign": "top"}),
                                ], id='norm-type-container', style={'display': 'block'}),

                                html.Div([
                                    html.Div([
                                        html.Span(
                                            "Energy",
                                            style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px', 'color': '#666'}
                                        ),
                                        exp_raw_energy_dropdown,
                                    ], style={'flex': '1', 'minWidth': '0', 'marginRight': '6px'}),

                                    html.Div([
                                        html.Span(
                                            id='raw-itiff-label',
                                            children="It / Iff",
                                            style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px', 'color': '#666'}
                                        ),
                                        exp_raw_itiff_dropdown,
                                    ], style={'flex': '1', 'minWidth': '0', 'marginRight': '6px'}),

                                    html.Div([
                                        html.Span(
                                            "I0",
                                            style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px', 'color': '#666'}
                                        ),
                                        exp_raw_i0_dropdown,
                                    ], style={'flex': '1', 'minWidth': '0'}),
                                ], id='raw-dropdown-container', style={'display': 'none', 'marginBottom': '8px'}),
                            ], style={'marginBottom': '15px'}),
                            html.Div([
                                html.Span("Data Format", style=radio_label_style),
                                dcc.Store(id='exp-data-type-store', data='norm'),
                                html.Div([
                                    html.Button("Normalized", id='btn-format-norm', style=radio_left_active_style),
                                    html.Button("Raw",        id='btn-format-raw',  style=radio_right_inactive_style),
                                ], style=radio_row_style)
                            ]),

                            dcc.Store(id='exp-raw-type-store', data='transmission'),
                                html.Div(
                                id='raw-type-container',
                                children=[
                                    html.Span("Measurement Type", style=radio_label_style),
                                    html.Div([
                                        html.Button("Fluorescent",  id="btn-type-fluor",  style=radio_left_inactive_style),
                                        html.Button("Transmission", id="btn-type-trans",  style=radio_right_active_style),
                                    ], style=radio_row_style),
                                    
                                    dcc.Store(id='exp-binning-store', data=0.25),
                                    html.Span("Bin Interval (eV)", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px', 'color': '#666'}),
                                    html.Div([
                                        dcc.Slider(
                                            id='binning-interval-slider',
                                            min=0,
                                            max=1.0,
                                            step=0.05,
                                            value=0.25,
                                            marks={0: {'label': 'Raw', 'style': {'fontSize': '10px'}},
                                                0.25: {'label': '0.25', 'style': {'fontSize': '10px'}},
                                                0.5: {'label': '0.5', 'style': {'fontSize': '10px'}},
                                                1.0: {'label': '1.0 eV', 'style': {'fontSize': '10px'}}},
                                            tooltip={"placement": "bottom", "always_visible": False},
                                            updatemode='mouseup',
                                            included=False,
                                        ),
                                    ], style={'marginBottom': '15px', 'marginTop': '10px'}),

                                    dcc.Store(id='exp-flatten-store', data='yes'),
                                    html.Span('Flatten Spectrum', style=radio_label_style),
                                    html.Div([
                                        html.Button('Yes', id='btn-flatten-yes', style=radio_left_active_style),
                                        html.Button('No',  id='btn-flatten-no',  style=radio_right_inactive_style),
                                    ], style=radio_row_style),
                                ],
                                style={'display': 'none'}
                            ),

                            html.Div([
                                exp_apply_btn,
                                clear_exp_btn,
                            ], style={"marginTop": "12px"}),
                        ],
                        style={"display": "none"}
                    ),

                    exp_file_info,
                    exp_raw_data_store,
                    exp_columns_store,
                    exp_spectrum_store,
                ], style=card_style),

                # Load Structure Card
                html.Div([
                    html.Div("Load Structure", style=section_header_style),

                    # Multiple structure search
                    html.Div("Materials Project IDs:", style={**input_label_style, "marginBottom": "8px"}),
                    mpid_list_input,
                    mpid_search_btn,

                    # Combined single/multiple file upload
                    html.Div("Upload structure file(s):", style={**input_label_style, "marginBottom": "4px"}),
                    html.Div(
                        "Single or multiple files • Supported: .cif, .vasp, .poscar, .json",
                        style={"fontSize": "10px", "color": "#999", "marginBottom": "8px"}
                    ),
                    batch_upload_component,
                    batch_processing_store,

                    # Processing status
                    html.Div(id='batch_status', children='', style={
                        "fontSize": "11px",
                        "color": "#666",
                        "marginTop": "8px",
                        "fontFamily": base_font
                    }),

                    html.Div(st_source, style={"marginTop": "10px"}),
                ], style=card_style),


            ],
            style={"flex": "1", "minWidth": "150px", "padding": "0 6px"}
        ),

        # Column 2: Crystal Structure Viewer
        Column(
            [
                html.Div([
                    html.Div("Crystal Structure Viewer", style=column_header_style),
                    html.Div(
                        Loading(struct_component.layout(size="100%")),
                        style={'minHeight': '200px', 'width': '100%', 'position': 'relative'}
                    )
                ], style=card_style),

                # XAS Model Prediction Card
                html.Div([
                    html.Div("XAS Machine Learning Model", style=section_header_style),
                    Loading(absorber_dropdown),
                    shakeup_store,
                    html.Div(
                        id='shakeup-toggle-container',
                        children=[
                            html.Span("Shake-up Correction", style={**radio_label_style, 'marginTop': '12px'}),
                            html.Div([
                                html.Button("On",  id='btn-shakeup-on',  style=radio_left_inactive_style),
                                html.Button("Off", id='btn-shakeup-off', style=radio_right_active_style),
                            ], style={**radio_row_style, 'marginBottom': '0'}),
                        ],
                        style={'display': 'none'}
                    ),
                ], style=card_style)
            ], 
            style={"flex": "1", "padding": "0 6px", "minWidth": "150px", "alignSelf": "flex-start"}
        ),

        # Column 3: Spectrum Analysis
        Column(
            html.Div([
                html.Div([
                    html.Div("XANES Spectrum Analysis", style=column_header_style),
                    xas_plot,

                    # Energy shift slider
                    html.Div([
                        html.Div([
                            html.Span("Shift Predicted Spectrum: ", style={"fontSize": "12px", "color": "#666", "fontFamily": base_font}),
                            html.Span(id='energy_shift_display', children="0.0 eV",
                                     style={"fontSize": "12px", "fontWeight": "600", "color": "#333", "fontFamily": base_font}),
                        ], style={"marginTop": "15px", "marginBottom": "8px"}),
                        dcc.Slider(
                            id='energy_shift_slider',
                            min=-50,
                            max=50,
                            step=0.01,
                            value=0,
                            marks=None,
                            tooltip={"placement": "bottom", "always_visible": False},
                            updatemode='drag',
                            included=False,
                        ),
                        html.Div([
                            html.Span("-50 eV", style={"fontSize": "10px", "color": "#999", "fontFamily": base_font}),
                            html.Span("0", style={"fontSize": "10px", "color": "#999", "position": "absolute", "left": "50%", "transform": "translateX(-50%)", "fontFamily": base_font}),
                            html.Span("+50 eV", style={"fontSize": "10px", "color": "#999", "fontFamily": base_font}),
                        ], style={"display": "flex", "justifyContent": "space-between", "position": "relative", "marginTop": "-5px"}),
                        html.Button("Reset Shift", id="reset_shift_btn", style={**button_secondary_style, "marginTop": "10px"})], id='energy_shift_container'),

                    html.Hr(style={"margin": "20px 0", "border": "none", "borderTop": "1px solid #eee"}),

                    html.Button("Download POSCAR and Spectrum", id="download_btn", style={
                        **button_primary_style,
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "12px",
                        "marginRight": "0",
                        "borderRadius": "6px"
                    }),
                    dcc.Download(id="download_sink"),

                    # Matching Results Section
                    html.Div([
                        html.Div([
                            html.Span("Structure Matching Scores", style={
                                "fontWeight": "600",
                                "fontSize": "13px",
                                "color": "#333",
                            }),
                            html.Button("Clear All", id="clear_scores_btn", style={**button_secondary_style, "marginLeft": "10px"}),
                        ], style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "space-between",
                            "marginTop": "20px",
                            "marginBottom": "12px",
                            "paddingBottom": "10px",
                            "borderBottom": "1px solid #eee"
                        }),
                        html.Div(id='matching_results_table', children=[
                            html.Div("Upload experimental spectrum and load structures to see matching scores",
                                    style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"})
                        ]),

                        html.Div(
                            id="upload_metadata_container",
                            children=[
                                html.Button(
                                    "Upload Meta Data",
                                    id="upload_metadata_btn",
                                    n_clicks=0,
                                    style={
                                        **button_primary_style,
                                        "width": "100%",
                                        "padding": "10px",
                                        "fontSize": "12px",
                                        "marginTop": "12px",
                                        "marginRight": "0",
                                        "borderRadius": "6px"
                                    }
                                ),

                                html.Div(
                                    id="upload_metadata_status",
                                    children="",
                                    style={
                                        "fontSize": "11px",
                                        "marginTop": "8px",
                                        "fontFamily": base_font
                                    }
                                ),

                                dcc.Store(id="matching_metadata_store", data=None),
                            ],
                            style={"display": "none"}
                        ),

                        structure_scores_store,
                        comparison_range_store,
                        selected_spectra_store,
                        sort_metric_store,
                    ]),

                ], style=card_style)
            ]),
            style={"flex": "1.5", "minWidth": "150px", "padding": "0 6px"}
        ),

        # Column 4: Agentic Chatbot
        Column(
            [
                html.Div([
                    html.Div("LightshowAI Chatbot", style=column_header_style),
                    html.Div(
                        [
                            html.Iframe(
                                id="chatbot_iframe",
                                src=CHATBOT_URL,
                                style={
                                    "width": "100%",
                                    "height": "900px",
                                    "border": "1px solid #e5e5e5",
                                    "borderRadius": "6px",
                                    "backgroundColor": "#fff",
                                },
                                sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads",
                            ),
                            html.Div(
                                [
                                    html.Span("Chat URL: ", style={"fontWeight": "600"}),
                                    html.A(CHATBOT_URL, href=CHATBOT_URL, target="_blank", rel="noopener noreferrer"),
                                ],
                                style={"fontSize": "11px", "color": "#666", "marginTop": "8px", "wordBreak": "break-all"},
                            ),
                        ]
                    ),
                ], style=card_style),
            ],
            style={"flex": "1", "minWidth": "320px", "padding": "0 6px", "alignSelf": "flex-start"}
        ),
    ],
    desktop_only=False,
    centered=False),
], style={
    "alignItems": "flex-start",
    "flexWrap": "wrap",
    "background": "#f5f5f5",
    "minHeight": "100vh",
    "padding": "24px",
    "paddingBottom": "16px",
    "fontFamily": base_font,
    "position": "relative" 
})

# Store for energy shift value
energy_shift_store = dcc.Store(id='energy_shift_store', data=0)


def parse_file_columns(contents, filename):
    """
    Parse uploaded file and extract all columns with their data.
    Supports XDI format with # Column.N: name headers.
    """
    if contents is None:
        return None

    content_type, content_string = contents.split(',')
    decoded = b64decode(content_string)

    try:
        if filename is None:
            filename = "unknown.dat"

        ext = pathlib.Path(filename).suffix.lower()
        print(f"=== DEBUG: Parsing file '{filename}' with extension '{ext}'")

        columns = []
        data = []

        auto_x_col = 0
        auto_y_col = 1

        if ext in ['.csv', '.dat', '.txt', '.xdi']:
            text = decoded.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

            comment_lines = []
            data_lines = []

            for line in lines:
                if line.startswith(('#', '%', '!')):
                    comment_lines.append(line)
                else:
                    data_lines.append(line)

            if len(data_lines) == 0:
                raise ValueError("No data lines found in file")

            xdi_columns = {}
            energy_col_candidates = []
            absorption_col_candidates = []

            for comment in comment_lines:
                xdi_match = re.match(r'#\s*Column\.(\d+):\s*(.+)', comment, re.IGNORECASE)
                if xdi_match:
                    col_num = int(xdi_match.group(1)) - 1
                    col_name = xdi_match.group(2).strip()
                    xdi_columns[col_num] = col_name
                    print(f"=== DEBUG: Found XDI column {col_num}: '{col_name}'")

                    col_lower = col_name.lower()
                    if any(term in col_lower for term in ['energy', ' e ', 'ev', 'photon']):
                        energy_col_candidates.append(col_num)

                    if any(term in col_lower for term in ['norm', 'absorption', 'abs', 'mu', 'flat']):
                        absorption_col_candidates.append(col_num)

            if comment_lines and not xdi_columns:
                last_comment = comment_lines[-1]
                header_text = last_comment.lstrip('#').strip()
                header_parts = header_text.split()

                if len(header_parts) >= 2 and ':' not in header_text:
                    print(f"=== DEBUG: Found inline header: {header_parts}")
                    for i, name in enumerate(header_parts):
                        xdi_columns[i] = name
                        name_lower = name.lower()
                        if name_lower in ['e', 'energy', 'ev']:
                            energy_col_candidates.append(i)
                        if name_lower in ['norm', 'flat', 'abs', 'mu', 'absorption']:
                            absorption_col_candidates.append(i)

            first_line = data_lines[0]

            if ',' in first_line:
                delimiter = ','
            else:
                delimiter = None

            first_parts = first_line.split(delimiter) if delimiter else first_line.split()
            num_columns = len(first_parts)

            try:
                float(first_parts[0].strip())
                header = None
                start_idx = 0
            except ValueError:
                header = [p.strip() for p in first_parts]
                start_idx = 1
                if not xdi_columns:
                    for i, name in enumerate(header):
                        xdi_columns[i] = name

            data = [[] for _ in range(num_columns)]

            for line in data_lines[start_idx:]:
                parts = line.split(delimiter) if delimiter else line.split()
                for i, part in enumerate(parts):
                    if i < num_columns:
                        try:
                            data[i].append(float(part.strip()))
                        except ValueError:
                            pass

            for i in range(num_columns):
                if i in xdi_columns:
                    col_name = xdi_columns[i]
                elif header and i < len(header):
                    col_name = header[i]
                else:
                    col_name = f"Column {i+1}"

                sample_values = data[i][:5] if len(data[i]) >= 5 else data[i]
                columns.append({
                    'index': i,
                    'name': col_name,
                    'num_values': len(data[i]),
                    'sample_values': sample_values
                })

            if energy_col_candidates:
                auto_x_col = energy_col_candidates[0]

            if absorption_col_candidates:
                for candidate in absorption_col_candidates:
                    col_name = xdi_columns.get(candidate, '').lower()
                    if 'norm' in col_name or 'flat' in col_name:
                        auto_y_col = candidate
                        break
                else:
                    auto_y_col = absorption_col_candidates[0]
            elif len(columns) > 1:
                auto_y_col = 1

        elif ext == '.mat':
            try:
                from scipy.io import loadmat
                mat_data = loadmat(io.BytesIO(decoded))

                data_keys = [k for k in mat_data.keys() if not k.startswith('__')]

                for i, key in enumerate(data_keys):
                    arr = mat_data[key]
                    if isinstance(arr, np.ndarray) and arr.size > 1:
                        flat_arr = arr.flatten().astype(float).tolist()
                        sample_values = flat_arr[:5] if len(flat_arr) >= 5 else flat_arr
                        columns.append({
                            'index': i,
                            'name': key,
                            'num_values': len(flat_arr),
                            'sample_values': sample_values
                        })
                        data.append(flat_arr)

                        key_lower = key.lower()
                        if any(term in key_lower for term in ['energy', 'e', 'ev']):
                            auto_x_col = i
                        if any(term in key_lower for term in ['absorption', 'abs', 'mu', 'norm']):
                            auto_y_col = i

            except ImportError:
                raise ValueError("scipy is required to read .mat files")

        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if len(columns) < 2:
            raise ValueError("File must have at least 2 columns for X and Y axes")
        
        for col in columns:
            name_lower = str(col['name']).lower().strip()
            if name_lower in ['energy', 'e', 'ev']:
                auto_x_col = col['index']
            elif name_lower in ['iff', 'if', 'fluor', 'it', 'trans', 'absorption', 'mu']:
                auto_y_col = col['index']

        auto_x_col = min(auto_x_col, len(columns) - 1)
        auto_y_col = min(auto_y_col, len(columns) - 1)
        if auto_x_col == auto_y_col and len(columns) > 1:
            auto_y_col = 1 if auto_x_col == 0 else 0

        print(f"=== DEBUG: Found {len(columns)} columns")
        print(f"=== DEBUG: Auto-selected X={auto_x_col}, Y={auto_y_col}")
        
        col_names_lower = [str(col['name']).lower().strip() for col in columns]
        is_new_csv = ("energy" in col_names_lower and "i0" in col_names_lower and 
                      any(c in col_names_lower for c in ["iff", "it", "ir"]))
        
        return {
            'columns': columns,
            'data': data,
            'filename': filename,
            'auto_x_col': auto_x_col,
            'auto_y_col': auto_y_col,
            'detected_format': 'new_xas_csv' if is_new_csv else 'generic_csv'
        }

    except Exception as e:
        print(f"Error parsing file columns: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}

@app.callback(
    Output("pending_spectra_store", "data", allow_duplicate=True),
    Output("last_load_source_store", "data", allow_duplicate=True),
    Output("exp_raw_data_store", "data", allow_duplicate=True),
    Output("exp_columns_store", "data", allow_duplicate=True),
    Output("exp_x_axis_dropdown", "options", allow_duplicate=True),
    Output("exp_y_axis_dropdown", "options", allow_duplicate=True),
    Output("exp_x_axis_dropdown", "value", allow_duplicate=True),
    Output("exp_y_axis_dropdown", "value", allow_duplicate=True),
    Output("exp_column_selection_area", "style", allow_duplicate=True),
    Output("exp_column_definition_area", "children", allow_duplicate=True),
    Output("exp_file_info", "children", allow_duplicate=True),
    Output("exp_material_name", "value", allow_duplicate=True),
    Output("exp-data-type-store", "data", allow_duplicate=True),
    Output("exp_raw_energy_dropdown", "options", allow_duplicate=True),
    Output("exp_raw_itiff_dropdown", "options", allow_duplicate=True),
    Output("exp_raw_i0_dropdown", "options", allow_duplicate=True),
    Output("exp_raw_energy_dropdown", "value", allow_duplicate=True),
    Output("exp_raw_itiff_dropdown", "value", allow_duplicate=True),
    Output("exp_raw_i0_dropdown", "value", allow_duplicate=True),
    Output("exp_spectrum_store", "data", allow_duplicate=True),

    # Clear structure / matching state when loading a new Tiled spectrum.
    Output(struct_component.id(), "data", allow_duplicate=True),
    Output("st_source", "children", allow_duplicate=True),
    Output("structure_scores_store", "data", allow_duplicate=True),
    Output("matching_results_table", "children", allow_duplicate=True),
    Output("comparison_range_store", "data", allow_duplicate=True),
    Output("selected_spectra_store", "data", allow_duplicate=True),
    Output("matching_metadata_store", "data", allow_duplicate=True),
    Output("upload_metadata_status", "children", allow_duplicate=True),
    Output("batch_status", "children", allow_duplicate=True),

    Input("pending_load_btn", "n_clicks"),
    State("pending_spectra_dropdown", "value"),
    State("pending_spectra_store", "data"),
    prevent_initial_call=True,
)
def handle_load_click(n_clicks, selected_idx, pending):
    if n_clicks is None or not pending or selected_idx is None:
        raise PreventUpdate

    if selected_idx >= len(pending):
        raise PreventUpdate

    entry = pending[selected_idx]
    load_results = _load_pending_entry(entry)
    updated_pending = [e for i, e in enumerate(pending) if i != selected_idx]

    empty_scores_message = html.Div(
        "Load structures to see matching scores",
        style={
            "color": "#999",
            "fontSize": "12px",
            "textAlign": "center",
            "padding": "20px"
        }
    )

    return (
        updated_pending,
        "pending",
        *load_results,

        # Fresh-start state for the new Tiled experimental spectrum.
        None,                         # struct_component data
        "No structure loaded yet",    # st_source
        [],                           # structure_scores_store
        empty_scores_message,         # matching_results_table
        None,                         # comparison_range_store
        [],                           # selected_spectra_store
        None,                         # matching_metadata_store
        "",                           # upload_metadata_status
        "",                           # batch_status
    )


@app.callback(
    Output("pending_spectra_section", "style"),
    Output("pending_spectra_header", "children"),
    Output("pending_spectra_dropdown", "options"),
    Output("pending_spectra_dropdown", "value"),
    Input("pending_spectra_store", "data"),
)
def render_pending_section(pending):
    print(f"[render_pending] callback fired with {len(pending) if pending else 0} entries")

    if not pending:
        return {"display": "none"}, "", [], None

    options = [
        {"label": _format_pending_label(entry), "value": idx}
        for idx, entry in enumerate(pending)
    ]
    header = f"New from beamline ({len(pending)})"
    return (
        {"display": "block", "marginBottom": "16px"},
        header,
        options,
        0,
    )

@app.callback(
    Output("exp_apply_btn", "n_clicks"),
    Input("exp_raw_data_store", "data"),
    State("exp_apply_btn", "n_clicks"),
    State("last_load_source_store", "data"),
    prevent_initial_call=True,
)
def auto_apply_pending_load(raw_data, current_clicks, load_source):
    """
    Auto-click Apply & Plot only when raw_data was populated by a
    pending-entry load. Manual uploads do NOT auto-apply; the user
    clicks Apply & Plot themselves after reviewing column detection.
    """
    if raw_data is None or load_source != "pending":
        raise PreventUpdate
    return (current_clicks or 0) + 1

@app.callback(
    Output("upload_metadata_container", "style"),
    Input("tiled_poll_interval", "n_intervals"),
    prevent_initial_call=False,
)
def toggle_upload_metadata_button_visibility(_):
    if get_current_user() is None:
        return {"display": "none"}

    return {"display": "block"}


@app.callback(
    Output("matching_metadata_store", "data"),
    Output("upload_metadata_status", "children"),
    Input("upload_metadata_btn", "n_clicks"),
    State("exp_spectrum_store", "data"),
    State("structure_scores_store", "data"),
    prevent_initial_call=True
)
def upload_matching_metadata_to_tiled(n_clicks, exp_data, scores):
    if not n_clicks:
        raise PreventUpdate

    if get_current_user() is None:
        return dash.no_update, html.Span(
            "✗ Please log in before uploading metadata",
            style={"color": "red"}
        )

    try:
        metadata = build_matching_metadata(exp_data, scores, top_n=3)
        print("Analysis Meta Data", metadata)
        payload = update_tiled_lightshowai_metadata(exp_data, metadata)

        return metadata, html.Span(
            "✓ Metadata uploaded to Tiled",
            style={"color": "green"}
        )

    except Exception as e:
        print(f"Error uploading matching metadata to Tiled: {e}")
        import traceback
        traceback.print_exc()

        return dash.no_update, html.Span(
            f"✗ Metadata upload failed: {str(e)}",
            style={"color": "red"}
        )

@app.callback(
    Output('exp-data-type-store', 'data'),
    Input('btn-format-norm', 'n_clicks'),
    Input('btn-format-raw', 'n_clicks'),
    State('exp-data-type-store', 'data'),
    prevent_initial_call=True,
)
def update_format_store(_, __, current_val):
    return _radio_callback(
        'btn-format-norm',
        'btn-format-raw',
        'norm',
        'raw',
        current_val or 'norm'
    )


@app.callback(
    Output('btn-format-norm', 'style'),
    Output('btn-format-raw', 'style'),
    Output('raw-type-container', 'style'),
    Output('norm-type-container', 'style'),
    Output('raw-dropdown-container', 'style'),
    Input('exp-data-type-store', 'data'),
    prevent_initial_call=False,
)
def render_format_toggle(current_val):
    current_val = current_val or 'norm'

    left, right = _radio_btn_styles(current_val == 'norm')

    raw_extra_style = {
        'display': 'none' if current_val == 'norm' else 'block'
    }

    norm_style = {
        'display': 'block' if current_val == 'norm' else 'none'
    }

    raw_dropdown_style = {
        'display': 'flex' if current_val == 'raw' else 'none',
        'marginBottom': '8px'
    }

    return left, right, raw_extra_style, norm_style, raw_dropdown_style



@app.callback(
    Output("pending_spectra_store", "data", allow_duplicate=True),
    Input("pending_dismiss_btn", "n_clicks"),
    State("pending_spectra_dropdown", "value"),
    State("pending_spectra_store", "data"),
    prevent_initial_call=True,
)
def handle_dismiss(n_clicks, selected_idx, pending):
    if n_clicks is None or not pending or selected_idx is None:
        raise PreventUpdate
    if selected_idx >= len(pending):
        raise PreventUpdate

    return [e for i, e in enumerate(pending) if i != selected_idx]
@app.callback(
    Output("pending_spectra_store", "data", allow_duplicate=True),
    Input("tiled_poll_interval", "n_intervals"),
    State("pending_spectra_store", "data"),
    prevent_initial_call=True,
)
def poll_tiled_updates(n, current_pending):
    from lightshowai.auth import get_current_user
    if get_current_user() is None:
        raise PreventUpdate

    new_events = []
    while True:
        try:
            new_events.append(_tiled_queue.get_nowait())
        except queue.Empty:
            break

    if not new_events:
        raise PreventUpdate

    stamped = [
        {**ev, "arrived_at": datetime.now().isoformat()}
        for ev in new_events
    ]
    updated = list(reversed(stamped)) + (current_pending or [])

    print(f"[poll] pending list now has {len(updated)} entries: "
          f"{[e.get('key') for e in updated]}")

    return updated

def _raw_dropdown_defaults(columns, raw_type='transmission'):
    options = [
        {
            'label': f"{col['name']} ({col['num_values']} pts)",
            'value': col['index']
        }
        for col in columns
    ]

    col_names_lower = {
        col['index']: str(col['name']).strip().lower()
        for col in columns
    }

    energy_val = next(
        (idx for idx, name in col_names_lower.items()
         if name in ['energy', 'e', 'ev']),
        None
    )

    i0_val = next(
        (idx for idx, name in col_names_lower.items()
         if name in ['i0', 'io']),
        None
    )

    is_fluor = (raw_type or 'transmission') == 'fluorescence'

    if is_fluor:
        itiff_val = next(
            (idx for idx, name in col_names_lower.items()
             if name in ['iff', 'if', 'fluor', 'fluorescence']),
            None
        )
    else:
        itiff_val = next(
            (idx for idx, name in col_names_lower.items()
             if name in ['it', 'ir', 'trans', 'transmission']),
            None
        )

    return options, energy_val, itiff_val, i0_val

def _build_column_ui(columns, filename, default_x, default_y):
    """Build dropdown options, column-definition table, and info text."""
    options = [{'label': f"{col['name']} ({col['num_values']} pts)", 'value': col['index']}
               for col in columns]

    max_visible_rows = 5
    table_height = "auto" if len(columns) <= max_visible_rows else f"{max_visible_rows * 40 + 30}px"

    col_definition = html.Div([
        html.Div(f"Detected {len(columns)} columns (edit names if needed):",
                 style={"fontSize": "12px", "marginBottom": "6px", "marginTop": "10px"}),
        html.Div([
            html.Table([
                html.Thead(html.Tr([
                    html.Th("#", style={"padding": "4px 8px", "fontSize": "11px", "width": "30px",
                                        "position": "sticky", "top": "0",
                                        "backgroundColor": "#fafafa", "zIndex": "1"}),
                    html.Th("Column Name", style={"padding": "4px 8px", "fontSize": "11px",
                                                  "position": "sticky", "top": "0",
                                                  "backgroundColor": "#fafafa", "zIndex": "1"}),
                    html.Th("Points", style={"padding": "4px 8px", "fontSize": "11px", "width": "50px",
                                             "position": "sticky", "top": "0",
                                             "backgroundColor": "#fafafa", "zIndex": "1"}),
                    html.Th("Sample Values", style={"padding": "4px 8px", "fontSize": "11px",
                                                    "position": "sticky", "top": "0",
                                                    "backgroundColor": "#fafafa", "zIndex": "1"}),
                ])),
                html.Tbody([
                    html.Tr([
                        html.Td(col['index'] + 1, style={"padding": "4px 8px", "fontSize": "11px",
                                                         "verticalAlign": "middle"}),
                        html.Td(
                            dcc.Input(
                                id={'type': 'col-name-input', 'index': col['index']},
                                type='text', value=col['name'],
                                style={'width': '100%', 'padding': '4px', 'fontSize': '11px',
                                       'border': '1px solid #ccc', 'borderRadius': '3px'}
                            ),
                            style={"padding": "4px"}
                        ),
                        html.Td(col['num_values'], style={"padding": "4px 8px", "fontSize": "11px",
                                                          "verticalAlign": "middle"}),
                        html.Td(", ".join([f"{v:.2f}" for v in col['sample_values'][:3]]) + "...",
                                style={"padding": "4px 8px", "fontSize": "10px",
                                       "color": "#666", "verticalAlign": "middle"}),
                    ]) for col in columns
                ])
            ], style={"borderCollapse": "collapse", "width": "100%"})
        ], style={
            "maxHeight": table_height,
            "overflowY": "auto" if len(columns) > max_visible_rows else "visible",
            "border": "1px solid #ddd", "marginBottom": "10px"
        }),
        html.Button("Update Column Names", id="exp_update_col_names_btn",
                    style={**button_secondary_style, "width": "100%", "height": "40px",
                           "padding": "0", "fontSize": "13px", "marginBottom": "10px",
                           "boxSizing": "border-box"})
    ])

    x_name = columns[default_x]['name'] if default_x < len(columns) else "Column 1"
    y_name = columns[default_y]['name'] if default_y < len(columns) else "Column 2"
    info_text = f"Loaded: {filename} (auto-selected: X={x_name}, Y={y_name})"

    return options, col_definition, info_text




@app.callback(
    Output('exp-flatten-store', 'data'),
    Output('btn-flatten-yes', 'style'),
    Output('btn-flatten-no', 'style'),
    Input('btn-flatten-yes', 'n_clicks'),
    Input('btn-flatten-no', 'n_clicks'),
    State('exp-flatten-store', 'data'),
    prevent_initial_call=False,
)
def update_flatten_mode(_, __, current_val):
    current_val = _radio_callback('btn-flatten-yes', 'btn-flatten-no', 'yes', 'no', current_val)
    left, right = _radio_btn_styles(current_val == 'yes')
    return current_val, left, right


@app.callback(
    Output('exp-raw-type-store', 'data'),
    Output('btn-type-fluor', 'style'),
    Output('btn-type-trans', 'style'),
    Input('btn-type-fluor', 'n_clicks'),
    Input('btn-type-trans', 'n_clicks'),
    State('exp-raw-type-store', 'data'),
    prevent_initial_call=False,
)
def update_measurement_mode(_, __, current_val):
    current_val = _radio_callback('btn-type-fluor', 'btn-type-trans', 'fluorescence', 'transmission', current_val)
    left, right = _radio_btn_styles(current_val == 'fluorescence')
    return current_val, left, right


@app.callback(
    Output('shakeup-store', 'data'),
    Output('btn-shakeup-on', 'style'),
    Output('btn-shakeup-off', 'style'),
    Input('btn-shakeup-on', 'n_clicks'),
    Input('btn-shakeup-off', 'n_clicks'),
    State('shakeup-store', 'data'),
    prevent_initial_call=False,
)
def update_shakeup_toggle(_, __, current_val):
    current_val = _radio_callback('btn-shakeup-on', 'btn-shakeup-off', 'yes', 'no', current_val)
    left, right = _radio_btn_styles(current_val == 'yes')
    return current_val, left, right

@app.callback(
    Output('shakeup-toggle-container', 'style'),
    Input('absorber', 'value'),
    prevent_initial_call=False
)
def toggle_shakeup_visibility(el_type):
    if el_type == 'Ti VASP':
        return {'display': 'block'}
    return {'display': 'none'}

@app.callback(
    Output('exp_raw_itiff_dropdown', 'value', allow_duplicate=True),
    Output('raw-itiff-label', 'children'),
    Input('exp-raw-type-store', 'data'),
    State('exp_columns_store', 'data'),
    prevent_initial_call=True,
)
def sync_itiff_dropdown_to_mode(raw_type, columns):
    if columns is None:
        raise PreventUpdate

    _, _, itiff_val, _ = _raw_dropdown_defaults(columns, raw_type)

    label = 'Iff' if raw_type == 'fluorescence' else 'It'
    return itiff_val, label

@app.callback(
    Output('exp_raw_data_store', 'data'),
    Output('exp_columns_store', 'data'),
    Output('exp_x_axis_dropdown', 'options'),
    Output('exp_y_axis_dropdown', 'options'),
    Output('exp_x_axis_dropdown', 'value'),
    Output('exp_y_axis_dropdown', 'value'),
    Output('exp_column_selection_area', 'style'),
    Output('exp_column_definition_area', 'children'),
    Output('exp_file_info', 'children', allow_duplicate=True),
    Output('exp_spectrum_upload', 'contents'),
    Output('exp_spectrum_upload', 'filename'),
    Output('exp_material_name', 'value'),
    Output('exp-data-type-store', 'data', allow_duplicate=True),
    Output('exp_raw_energy_dropdown', 'options'),
    Output('exp_raw_itiff_dropdown', 'options'),
    Output('exp_raw_i0_dropdown', 'options'),
    Output('exp_raw_energy_dropdown', 'value'),
    Output('exp_raw_itiff_dropdown', 'value'),
    Output('exp_raw_i0_dropdown', 'value'),
    Output('exp_spectrum_store', 'data', allow_duplicate=True),
    Output('last_load_source_store', 'data', allow_duplicate=True),
    Input('exp_spectrum_upload', 'contents'),
    Input('clear_exp_btn', 'n_clicks'),
    State('exp_spectrum_upload', 'filename'),
    State('exp-raw-type-store', 'data'),
    prevent_initial_call=True
)
def handle_file_upload(contents, clear_clicks, filename, raw_type):
    """
    Handle manual experimental-spectrum file upload.

    This populates the shared experimental data stores used by both manual
    uploads and Tiled-loaded spectra. It also prepares both the normalized
    X/Y dropdowns and the raw Energy / It-or-Iff / I0 dropdowns.
    """
    ctx = dash.callback_context

    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    hidden_style = {"display": "none"}
    visible_style = {"display": "block"}

    empty_return = (
        None,               # exp_raw_data_store
        None,               # exp_columns_store
        [],                 # exp_x_axis_dropdown options
        [],                 # exp_y_axis_dropdown options
        None,               # exp_x_axis_dropdown value
        None,               # exp_y_axis_dropdown value
        hidden_style,       # exp_column_selection_area style
        [],                 # exp_column_definition_area children
        'No experimental spectrum loaded',
        None,               # exp_spectrum_upload contents
        None,               # exp_spectrum_upload filename
        '',                 # exp_material_name
        'norm',             # exp-data-type-store
        [],                 # exp_raw_energy_dropdown options
        [],                 # exp_raw_itiff_dropdown options
        [],                 # exp_raw_i0_dropdown options
        None,               # exp_raw_energy_dropdown value
        None,               # exp_raw_itiff_dropdown value
        None,               # exp_raw_i0_dropdown value
        None,               # exp_spectrum_store
        "manual",           # last_load_source_store
    )

    if trigger_id == 'clear_exp_btn':
        return empty_return

    if contents is None:
        raise PreventUpdate

    result = parse_file_columns(contents, filename)

    if result is None or 'error' in result:
        error_msg = result.get('error', 'Failed to parse file') if result else 'Failed to parse file'

        return (
            None,
            None,
            [],
            [],
            None,
            None,
            hidden_style,
            [],
            html.Span(f"Error: {error_msg}", style={'color': 'red'}),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            [],
            [],
            [],
            None,
            None,
            None,
            None,
            "manual",
        )

    columns = result['columns']

    default_x = result.get('auto_x_col', 0)
    default_y = result.get('auto_y_col', 1 if len(columns) > 1 else 0)

    default_x = min(default_x, len(columns) - 1)
    default_y = min(default_y, len(columns) - 1)

    options, col_definition, info_text = _build_column_ui(
        columns,
        filename,
        default_x,
        default_y
    )

    raw_options, raw_energy_val, raw_itiff_val, raw_i0_val = _raw_dropdown_defaults(
        columns,
        raw_type=raw_type or 'transmission'
    )

    detected_format = result.get('detected_format')
    default_data_type = 'raw' if detected_format == 'new_xas_csv' else 'norm'

    material_name_from_file = pathlib.Path(filename).stem if filename else ""

    return (
        result,                                      # exp_raw_data_store
        columns,                                     # exp_columns_store
        options,                                     # exp_x_axis_dropdown options
        options,                                     # exp_y_axis_dropdown options
        default_x,                                   # exp_x_axis_dropdown value
        default_y,                                   # exp_y_axis_dropdown value
        visible_style,                               # exp_column_selection_area style
        col_definition,                              # exp_column_definition_area children
        html.Span(info_text, style={'color': 'blue'}),
        dash.no_update,                              # exp_spectrum_upload contents
        dash.no_update,                              # exp_spectrum_upload filename
        material_name_from_file,                     # exp_material_name
        default_data_type,                           # exp-data-type-store
        raw_options,                                 # exp_raw_energy_dropdown options
        raw_options,                                 # exp_raw_itiff_dropdown options
        raw_options,                                 # exp_raw_i0_dropdown options
        raw_energy_val,                              # exp_raw_energy_dropdown value
        raw_itiff_val,                               # exp_raw_itiff_dropdown value
        raw_i0_val,                                  # exp_raw_i0_dropdown value
        None,                                        # clear exp_spectrum_store until Apply & Plot
        "manual",                                    # last_load_source_store
    )


@app.callback(
    Output('exp_columns_store', 'data', allow_duplicate=True),
    Output('exp_x_axis_dropdown', 'options', allow_duplicate=True),
    Output('exp_y_axis_dropdown', 'options', allow_duplicate=True),
    Output('exp_file_info', 'children', allow_duplicate=True),
    Input('exp_update_col_names_btn', 'n_clicks'),
    State({'type': 'col-name-input', 'index': ALL}, 'value'),
    State('exp_columns_store', 'data'),
    prevent_initial_call=True
)
def update_column_names(n_clicks, new_names, columns):
    """Update column names when user edits them."""
    if n_clicks is None or columns is None:
        raise PreventUpdate

    for i, new_name in enumerate(new_names):
        if i < len(columns):
            columns[i]['name'] = new_name.strip() if new_name else f"Column {i+1}"

    options = [{'label': f"{col['name']} ({col['num_values']} pts)", 'value': col['index']} for col in columns]

    return columns, options, options, html.Span("Column names updated!", style={'color': 'green'})

@app.callback(
    Output('exp-binning-store', 'data'),
    Input('binning-interval-slider', 'value'),
    prevent_initial_call=False
)
def update_binning_mode(slider_val):
    return slider_val if slider_val is not None else 0.25

@app.callback(
    Output('exp_spectrum_store', 'data'),
    Output('exp_file_info', 'children', allow_duplicate=True),
    Input('exp_apply_btn', 'n_clicks'),
    State('exp_raw_data_store', 'data'),
    State('exp_columns_store', 'data'),
    State('exp_x_axis_dropdown', 'value'),
    State('exp_y_axis_dropdown', 'value'),
    State('exp_material_name', 'value'),
    State('exp-data-type-store', 'data'),
    State('exp-raw-type-store', 'data'),
    State('exp-binning-store', 'data'),
    State('exp-flatten-store', 'data'),
    State('exp_raw_energy_dropdown', 'value'),
    State('exp_raw_itiff_dropdown', 'value'),
    State('exp_raw_i0_dropdown', 'value'),
    prevent_initial_call=True
)
def apply_column_selection(
    n_clicks,
    raw_data,
    columns,
    x_col_idx,
    y_col_idx,
    material_name,
    data_type,
    raw_mode,
    bin_mode,
    flattenmode,
    raw_energy_idx,
    raw_itiff_idx,
    raw_i0_idx
):
    """
    Apply column selection and create the experimental spectrum.

    Supports both data sources:
      1. manual file upload
      2. Tiled pending-spectrum load

    Supports both data modes:
      1. normalized/generic X-Y data
      2. raw XAS data using Energy + I0 + It/Iff
    """
    if n_clicks is None or raw_data is None:
        raise PreventUpdate

    try:
        if columns is None:
            return None, html.Span(
                "No column information available",
                style={'color': 'red'}
            )

        filename = raw_data.get('filename', 'experimental_spectrum')
        display_name = (
            material_name.strip()
            if material_name and material_name.strip()
            else filename
        )

        data_type = data_type or 'norm'
        raw_mode = raw_mode or 'transmission'
        apply_flat = flattenmode == 'yes'

        raw_matrix = raw_data.get('data', [])

        if not raw_matrix:
            return None, html.Span(
                "No experimental data available",
                style={'color': 'red'}
            )

        # ------------------------------------------------------------
        # Raw mode:
        # Use Energy + I0 + It/Iff, independent of whether data came
        # from file upload or Tiled.
        # ------------------------------------------------------------
        if data_type == 'raw':
            is_fluor = raw_mode == 'fluorescence'
            signal_name = 'iff' if is_fluor else 'it'

            required = {
                'energy': raw_energy_idx,
                'i0': raw_i0_idx,
                signal_name: raw_itiff_idx,
            }

            missing = [name for name, idx in required.items() if idx is None]
            if missing:
                return None, html.Span(
                    f"Please select all required raw columns: {', '.join(missing)}",
                    style={'color': 'red'}
                )

            max_idx = len(raw_matrix) - 1
            selected_indices = [raw_energy_idx, raw_i0_idx, raw_itiff_idx]

            if any(idx < 0 or idx > max_idx for idx in selected_indices):
                return None, html.Span(
                    "One or more selected raw columns are out of range",
                    style={'color': 'red'}
                )

            energy = np.array(raw_matrix[raw_energy_idx], dtype=float)
            i0 = np.array(raw_matrix[raw_i0_idx], dtype=float)
            signal = np.array(raw_matrix[raw_itiff_idx], dtype=float)

            min_len = min(len(energy), len(i0), len(signal))
            energy = energy[:min_len]
            i0 = i0[:min_len]
            signal = signal[:min_len]

            finite_mask = (
                np.isfinite(energy)
                & np.isfinite(i0)
                & np.isfinite(signal)
            )

            energy = energy[finite_mask]
            i0 = i0[finite_mask]
            signal = signal[finite_mask]

            if len(energy) < 2:
                return None, html.Span(
                    "Not enough valid raw data points",
                    style={'color': 'red'}
                )

            df_raw = pd.DataFrame({
                'energy': energy,
                'i0': i0,
                signal_name: signal,
            })

            apply_bin = bin_mode > 0 if isinstance(bin_mode, (int, float)) else False

            spec, meta = spectrum_from_new_csv(
                df_raw,
                mode=raw_mode,
                apply_binning=apply_bin,
                bin_interval=bin_mode if apply_bin else 0.25
            )

            spec = normalizeSpectrum(spec, flatten=apply_flat)

            x_data = np.array(spec[:, 0], dtype=float)
            y_data = np.array(spec[:, 1], dtype=float)

            x_label = meta.get('x_label', 'Energy')
            y_label = f"Normalized μ(E) [{meta.get('mode', raw_mode).capitalize()}]"

        # ------------------------------------------------------------
        # Normalized/generic mode:
        # Use user-selected X and Y columns directly.
        # ------------------------------------------------------------
        else:
            if x_col_idx is None or y_col_idx is None:
                return None, html.Span(
                    "Please select both X and Y axis columns",
                    style={'color': 'red'}
                )

            max_idx = len(raw_matrix) - 1
            if x_col_idx < 0 or x_col_idx > max_idx or y_col_idx < 0 or y_col_idx > max_idx:
                return None, html.Span(
                    "Selected X or Y column is out of range",
                    style={'color': 'red'}
                )

            x_data = np.array(raw_matrix[x_col_idx], dtype=float)
            y_data = np.array(raw_matrix[y_col_idx], dtype=float)

            min_len = min(len(x_data), len(y_data))
            x_data = x_data[:min_len]
            y_data = y_data[:min_len]

            finite_mask = np.isfinite(x_data) & np.isfinite(y_data)
            x_data = x_data[finite_mask]
            y_data = y_data[finite_mask]

            if len(x_data) < 2:
                return None, html.Span(
                    "Not enough valid data points",
                    style={'color': 'red'}
                )

            sort_idx = np.argsort(x_data)
            x_data = x_data[sort_idx]
            y_data = y_data[sort_idx]

            x_label = columns[x_col_idx]['name']
            y_label = columns[y_col_idx]['name']

        result = {
            'energy': x_data.tolist(),
            'absorption': y_data.tolist(),
            'filename': filename,
            'material_name': display_name,
            'x_label': x_label,
            'y_label': y_label,
            'data_type': data_type,
            'raw_mode': raw_mode if data_type == 'raw' else None,
        }

        x_min = float(np.min(x_data))
        x_max = float(np.max(x_data))

        info_text = (
            f"✓ {display_name} "
            f"({len(x_data)} points, {x_label}: {x_min:.1f}-{x_max:.1f})"
        )

        print(f"=== DEBUG: Plot ready. Output contains {len(x_data)} items. ===")

        return result, html.Span(info_text, style={'color': 'green'})

    except Exception as e:
        print(f"Error applying column selection: {e}")
        import traceback
        traceback.print_exc()

        return None, html.Span(
            f"Error: {str(e)}",
            style={'color': 'red'}
        )
@app.callback(
    Output("download_sink", "data"),
    Input("download_btn", "n_clicks"),
    State(struct_component.id(), "data"),
    State('absorber', 'value'),
)
def download_xas_prediction(n_clicks, st_data, el_type):
    if st_data is None:
        raise PreventUpdate
    el, theory = el_type.split(' ')
    st = Structure.from_dict(st_data)
    d_xas = st_data['xas']
    specs = np.stack([ene_grid[el]] + list(d_xas.values()))
    site_idxs = ["Energy"] + [f'Atom #{int(i) + 1}' for i in d_xas.keys()]
    df = pd.DataFrame(specs, index=site_idxs)
    with tempfile.TemporaryDirectory() as td:
        tmpdir = pathlib.Path(td)
        if len(d_xas) == 0:
            fn_spec = tmpdir / "no_spectrum.csv"
        else:
            fn_spec = tmpdir / "spectrum.csv"
        fn_poscar = tmpdir / 'POSCAR'
        files_to_zip = [fn_poscar, fn_spec]
        st.to(fn_poscar, fmt='poscar')
        df.to_csv(fn_spec, float_format="%.3f", header=False)
        zip_fn = tmpdir / f'OmniXAS_{el}_{theory}_Prediction_{n_clicks}.zip'
        with ZipFile(zip_fn, mode="w") as zip_file:
            for fn in files_to_zip:
                zip_file.write(fn, arcname=fn.name)
        bytes = b64encode((tmpdir / zip_fn).read_bytes()).decode("ascii")
        download_data = {"content": bytes,
                         "base64": True,
                         "type": "application/zip",
                         "filename": zip_fn.name}

    return download_data


@app.callback(
    Output(struct_component.id(), "data", allow_duplicate=True),
    Output('st_source', "children", allow_duplicate=True),
    Output('structure_scores_store', 'data', allow_duplicate=True),
    Output('matching_results_table', 'children', allow_duplicate=True),
    Output('comparison_range_store', 'data', allow_duplicate=True),
    Input("mpid_search_btn", "n_clicks"),
    State("mpid_list_input", "value"),
    State('absorber', 'value'),
    State('shakeup-store', 'data'),
    State('exp_spectrum_store', 'data'),
    State('structure_scores_store', 'data'),
    State('sort_metric_store', 'data'),
    prevent_initial_call=True
)
def update_structure_by_mpid(n_clicks, mpid_list_value, el_type, shakeup_val, exp_data, existing_scores, sort_metric):
    if not n_clicks:
        raise PreventUpdate

    if existing_scores is None:
        existing_scores = []

    if sort_metric is None:
        sort_metric = "coss_deriv"

    mpids = parse_mpid_list(mpid_list_value)
    if not mpids:
        raise PreventUpdate

    element, theory = el_type.split(" ")
    has_exp_data = exp_data is not None and "energy" in exp_data and "absorption" in exp_data

    successful = 0
    failed = 0
    failed_ids = []
    comparison_range = None
    last_st_dict = None
    last_mpid = None

    with MPRester() as mpr:
        docs = mpr.materials.search(
            material_ids=mpids,
            fields=["material_id", "structure"],
        )

    docs_by_id = {str(doc.material_id): doc for doc in docs}

    for mpid in mpids:
        try:
            doc = docs_by_id.get(mpid)
            if doc is None or doc.structure is None:
                failed += 1
                failed_ids.append(f"{mpid} (not found)")
                continue

            st = doc.structure
            if not isinstance(st, Structure):
                failed += 1
                failed_ids.append(f"{mpid} (invalid structure)")
                continue

            if element not in st.composition:
                failed += 1
                failed_ids.append(f"{mpid} (no {element})")
                continue
            print(f"Predicting spectrum for {mpid} with element {element} and theory {theory}")
            specs = predict(st, element, theory)
            if len(specs) == 0:
                failed += 1
                failed_ids.append(f"{mpid} (no spectrum)")
                continue

            specs_array = np.array(list(specs.values()))
            predicted_spectrum = specs_array.mean(axis=0)
            energy = ene_grid[element].tolist()

            if has_exp_data:
                match_result = get_spectrum_match_score(predicted_spectrum, exp_data, element)
            else:
                match_result = {
                    "score": 0.0,
                    "correlations": {},
                    "shift": 0.0,
                    "comparison_range": None
                }

            old_entry = next((s for s in existing_scores if s["structure_id"] == mpid), None)
            was_selected = old_entry.get("selected", False) if old_entry else False

            existing_scores = [s for s in existing_scores if s["structure_id"] != mpid]

            existing_scores.append({
                "structure_id": mpid,
                "score": match_result["score"],
                "shift": match_result["shift"],
                "correlations": match_result["correlations"],
                "comparison_range": match_result["comparison_range"],
                "spectrum": predicted_spectrum.tolist(),
                "energy": energy,
                "element": element,
                "selected": was_selected
            })

            if match_result["comparison_range"] is not None:
                comparison_range = match_result["comparison_range"]

            st_dict = st.as_dict()
            st_dict["xas"] = specs
            st_dict["label"] = mpid
            st_dict["material_id"] = mpid
            st_dict["structure_id"] = mpid

            last_st_dict = st_dict
            last_mpid = mpid

        except Exception as e:
            print(f"Error processing {mpid}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            failed_ids.append(mpid)
    existing_scores = mark_active_structure_selected(existing_scores, last_mpid)
    existing_scores = sort_scores_by_metric(existing_scores, sort_metric)

    if successful == 0:
        source_text = f"No valid structures loaded. Failed: {failed}"
        return (
            dash.no_update,
            source_text,
            existing_scores,
            build_scores_table(existing_scores, sort_metric),
            comparison_range
        )

    if successful == 1:
        source_text = f"Current structure: {last_mpid}"
    else:
        source_text = f"Loaded {successful} MP structures"

    if failed > 0:
        source_text += f" | Failed: {failed}"

    return (
        last_st_dict,
        source_text,
        existing_scores,
        build_scores_table(existing_scores, sort_metric),
        comparison_range
    )


def decorate_structure_with_xas(st: Structure, el_type, apply_shakeup=False):
    absorbing_site, spectroscopy_type = el_type.split(' ')
    st_dict = st.as_dict()
    if absorbing_site in st.composition:
        print("XAS Spectrum generated for structure:", st, absorbing_site, spectroscopy_type)
        specs = predict(st, absorbing_site, spectroscopy_type)
        if apply_shakeup and el_type == 'Ti VASP':
            new_specs = {}
            for k, v in specs.items():
                orig_ene = ene_grid['Ti']
                shaken = shakeupSpectrum(
                    np.column_stack((orig_ene, v)),
                    _Aw, pad_right=10, truncate_right=0.5
                )
                shaken_interp = np.interp(orig_ene, shaken[:, 0], shaken[:, 1])
                new_specs[k] = shaken_interp.tolist()
            specs = new_specs
            
        st_dict['xas'] = specs
    else:
        st_dict['xas'] = {}
    return st_dict

def parse_structure_file(contents, filename):
    """
    Parse a structure file from base64-encoded contents.
    Supports CIF, VASP/POSCAR, and JSON formats.
    """
    try:
        content_type, content_string = contents.split(',')
        decoded = b64decode(content_string)

        ext = pathlib.Path(filename).suffix.lower()

        if ext in ['.cif']:
            # CIF format
            from pymatgen.io.cif import CifParser
            text = decoded.decode('utf-8')
            parser = CifParser.from_str(text)
            st = parser.parse_structures()[0]
        elif ext in ['.vasp', '.poscar', '']:
            # VASP/POSCAR format
            from pymatgen.io.vasp import Poscar
            text = decoded.decode('utf-8')
            poscar = Poscar.from_str(text)
            st = poscar.structure
        elif ext == '.json':
            # JSON format (pymatgen Structure dict)
            import json
            text = decoded.decode('utf-8')
            data = json.loads(text)
            st = Structure.from_dict(data)
        else:
            # Try to auto-detect format
            text = decoded.decode('utf-8')
            try:
                # Try CIF first
                from pymatgen.io.cif import CifParser
                parser = CifParser.from_str(text)
                st = parser.parse_structures()[0]
            except:
                try:
                    # Try POSCAR
                    from pymatgen.io.vasp import Poscar
                    poscar = Poscar.from_str(text)
                    st = poscar.structure
                except:
                    raise ValueError(f"Could not parse file format: {ext}")

        return st
    except Exception as e:
        print(f"Error parsing structure file {filename}: {e}")
        import traceback
        traceback.print_exc()
        return None


@app.callback(
    Output('structure_scores_store', 'data', allow_duplicate=True),
    Output('matching_results_table', 'children', allow_duplicate=True),
    Output('comparison_range_store', 'data', allow_duplicate=True),
    Output('batch_status', 'children'),
    Output('batch_structure_upload', 'contents'),
    Output(struct_component.id(), "data", allow_duplicate=True),
    Output('st_source', "children", allow_duplicate=True),
    Input('batch_structure_upload', 'contents'),
    State('batch_structure_upload', 'filename'),
    State('exp_spectrum_store', 'data'),
    State('absorber', 'value'),
    State('structure_scores_store', 'data'),
    State('sort_metric_store', 'data'),
    State('shakeup-store', 'data'),
    prevent_initial_call=True
)
def handle_batch_upload(contents_list, filenames_list, exp_data, el_type, existing_scores, sort_metric, shakeup_val):
    """
    Handle batch upload of multiple structure files.
    Parse each file, generate XAS spectrum, and compare with experimental data.
    """
    
    if contents_list is None or len(contents_list) == 0:
        raise PreventUpdate

    if existing_scores is None:
        existing_scores = []

    if sort_metric is None:
        sort_metric = 'coss_deriv'

    has_exp_data = exp_data is not None and 'energy' in exp_data and 'absorption' in exp_data

    element = el_type.split(' ')[0]

    # Process each uploaded file
    successful = 0
    failed = 0
    failed_files = []
    last_st_dict = None
    last_filename = None
    last_structure_id = None
    comparison_range = None

    for contents, filename in zip(contents_list, filenames_list):
        try:
            # Parse the structure file
            st = parse_structure_file(contents, filename)

            if st is None:
                failed += 1
                failed_files.append(filename)
                continue

            # Check if structure contains the absorbing element
            if element not in st.composition:
                print(f"Structure {filename} does not contain {element}, skipping...")
                failed += 1
                failed_files.append(f"{filename} (no {element})")
                continue

            # Generate XAS spectrum
            print("XAS Spectrum generated for structure:", st, element, el_type.split(' ')[1])
            specs = predict(st, element, el_type.split(' ')[1])
            
            if shakeup_val == 'yes' and el_type == 'Ti VASP':
                orig_ene = ene_grid['Ti']
                new_specs = {}
                for k, v in specs.items():
                    shaken = shakeupSpectrum(np.column_stack((orig_ene, v)), _Aw, pad_right=10, truncate_right=0.5)
                    new_specs[k] = np.interp(orig_ene, shaken[:, 0], shaken[:, 1]).tolist()
                specs = new_specs

            if len(specs) == 0:
                failed += 1
                failed_files.append(f"{filename} (no spectrum)")
                continue

            # Calculate average spectrum
            specs_array = np.array(list(specs.values()))
            predicted_spectrum = specs_array.mean(axis=0)
            energy = ene_grid[element].tolist()

            # Get structure ID from filename (remove extension)
            structure_id = pathlib.Path(filename).stem

            # Compare with experimental data if available

            if has_exp_data:
                match_result = get_spectrum_match_score(predicted_spectrum, exp_data, element)
            else:
                match_result = {
                    'score': 0.0,
                    'correlations': {},
                    'shift': 0.0,
                    'comparison_range': None
                }

            # Check if this structure already exists - preserve selection state
            old_entry = next((s for s in existing_scores if s['structure_id'] == structure_id), None)
            was_selected = old_entry.get('selected', False) if old_entry else False

            # Remove old entry if exists
            existing_scores = [s for s in existing_scores if s['structure_id'] != structure_id]

            # Add new score entry
            existing_scores.append({
                'structure_id': structure_id,
                'score': match_result['score'],
                'shift': match_result['shift'],
                'correlations': match_result['correlations'],
                'comparison_range': match_result['comparison_range'],
                'spectrum': predicted_spectrum.tolist(),
                'energy': energy,
                'element': element,
                'selected': was_selected
            })

            # Keep track of comparison range from last successful processing
            if match_result['comparison_range'] is not None:
                comparison_range = match_result['comparison_range']

            # Store last structure for display
            st_dict = st.as_dict()
            st_dict["xas"] = specs
            st_dict["label"] = pathlib.Path(filename).stem
            st_dict["filename"] = filename
            st_dict["structure_id"] = structure_id

            last_st_dict = st_dict
            last_filename = filename
            last_structure_id = structure_id

            successful += 1

        except Exception as e:
            print(f"Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            failed_files.append(filename)

    # Sort scores by current metric
    existing_scores = mark_active_structure_selected(existing_scores, last_structure_id)
    existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
    

    # Build status message
    if successful > 0 and failed == 0:
        status_msg = html.Span(f"✓ Processed {successful} structure(s) successfully", style={'color': 'green'})
    elif successful > 0 and failed > 0:
        status_msg = html.Span([
            html.Span(f"✓ Processed {successful} structure(s). ", style={'color': 'green'}),
            html.Span(f"✗ Failed: {failed} ({', '.join(failed_files[:3])}{'...' if len(failed_files) > 3 else ''})", style={'color': 'orange'})
        ])
    else:
        status_msg = html.Span(f"✗ Failed to process all {failed} file(s)", style={'color': 'red'})

    # Update source text
    if successful > 0:
        source_text = f"Current structure: {pathlib.Path(last_filename).stem}"
    else:
        source_text = "No structures loaded"

    return (
        existing_scores,
        build_scores_table(existing_scores, sort_metric),
        comparison_range,
        status_msg,
        None,  # Clear the upload contents
        last_st_dict if last_st_dict else dash.no_update,
        source_text
    )


def build_figure_with_exp(predicted_spectrum, exp_data, el_type, is_average, no_element, sel_mismatch, energy_shift=0, comparison_range=None, selected_spectra=None, current_structure_id=None):
    """
    Build a plotly figure with predicted spectrum and optional experimental overlay.
    The comparison_range parameter zooms the plot to the energy range used for comparison.
    """
    element = el_type.split(" ")[0]
    fig = go.Figure()

    has_exp_data = exp_data is not None and 'energy' in exp_data and 'absorption' in exp_data
    has_selected = selected_spectra is not None and len(selected_spectra) > 0

    if has_selected:
        num_selected = len(selected_spectra)
        title = f'Comparing {num_selected} Structure{"s" if num_selected > 1 else ""} with Experimental'
    elif predicted_spectrum is None and has_exp_data:
        exp_display_name = exp_data.get('material_name', exp_data.get('filename', 'Experimental'))
        title = f'Experimental Spectrum: {exp_display_name}'
    elif no_element:
        title = f"This structure doesn't contain {element}"
    elif sel_mismatch:
        title = f"The selected atom is not a {element} atom"
    elif is_average:
        title = f'Average K-edge XANES Spectrum of {el_type}'
        if has_exp_data:
            title += " (with Experimental)"
    else:
        title = f'K-edge XANES Spectrum for the selected {element} atom'
        if has_exp_data:
            title += " (with Experimental)"

    exp_energy = None
    exp_absorption = None
    if has_exp_data:
        exp_energy = np.array(exp_data['energy'])
        exp_absorption = np.array(exp_data['absorption'])

    colors = ['#636EFA', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']

    if has_selected:
        for idx, spec_entry in enumerate(selected_spectra):
            spec_data = np.array(spec_entry['spectrum'])
            spec_energy = np.array(spec_entry['energy'])
            spec_shift = spec_entry.get('shift', 0.0)
            structure_id = spec_entry['structure_id']

            spec_energy_shifted = spec_energy + spec_shift

            if has_exp_data and len(exp_absorption) > 0:
                pred_range = np.max(spec_data) - np.min(spec_data)
                exp_range = np.max(exp_absorption) - np.min(exp_absorption)

                if pred_range > 0 and exp_range > 0:
                    spec_normalized = (spec_data - np.min(spec_data)) / pred_range
                    spec_scaled = spec_normalized * exp_range + np.min(exp_absorption)
                else:
                    spec_scaled = spec_data
            else:
                spec_scaled = spec_data

            color = colors[idx % len(colors)]
            fig.add_trace(go.Scatter(
                x=spec_energy_shifted,
                y=spec_scaled,
                mode='lines',
                name=f'{structure_id}',
                line=dict(color=color, width=2),
            ))

    elif predicted_spectrum is not None:
        ene = ene_grid[element]
        ene_shifted = ene + energy_shift

        predicted_was_normalized = False
        if has_exp_data and len(exp_absorption) > 0:
            pred_range = np.max(predicted_spectrum) - np.min(predicted_spectrum)
            exp_range = np.max(exp_absorption) - np.min(exp_absorption)

            if pred_range > 0 and exp_range > 0:
                pred_normalized = (predicted_spectrum - np.min(predicted_spectrum)) / pred_range
                pred_scaled = pred_normalized * exp_range + np.min(exp_absorption)
                predicted_was_normalized = True
            else:
                pred_scaled = predicted_spectrum
        else:
            pred_scaled = predicted_spectrum

        if current_structure_id:
            pred_name = f'{current_structure_id}'
            if predicted_was_normalized:
                pred_name += ' (normalized)'
        else:
            pred_name = 'Predicted (normalized)' if predicted_was_normalized else 'Predicted'

        if energy_shift != 0:
            pred_name += f' [{energy_shift:+.1f} eV]'

        fig.add_trace(go.Scatter(
            x=ene_shifted,
            y=pred_scaled,
            mode='lines',
            name=pred_name,
            line=dict(color='#636EFA', width=2),
        ))

    if has_exp_data:
        exp_display_name = exp_data.get('material_name', exp_data.get('filename', 'Experimental'))
        fig.add_trace(go.Scatter(
            x=exp_energy,
            y=exp_absorption,
            mode='markers',
            name=f'Exp: {exp_display_name}',
            marker=dict(color='#EF553B', size=4),
        ))

    if has_exp_data:
        x_axis_label = exp_data.get('x_label', 'Energy (eV)')
        y_axis_label = exp_data.get('y_label', 'Absorption')
    else:
        x_axis_label = "Energy (eV)"
        y_axis_label = "Absorption"

    layout_config = dict(
        title=title,
        xaxis_title=x_axis_label,
        yaxis_title=y_axis_label,
        legend=dict(
            yanchor="bottom",
            y=0.01,
            xanchor="right",
            x=0.99,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=10)
        ),
        hovermode='x unified'
    )

    # Apply comparison range to x-axis to zoom into the comparison region
    if has_exp_data and comparison_range is not None and len(comparison_range) == 2:
        x_start, x_end = comparison_range
        if x_start < x_end and (x_end - x_start) > 5:
            pad_x = (x_end - x_start) * 0.1
            x_min, x_max = x_start - pad_x, x_end + pad_x
            
            layout_config['xaxis'] = dict(
                range=[x_min, x_max], minallowed=x_min, maxallowed=x_max, 
                autorange=False, title=x_axis_label
            )
            
            y_vals = np.concatenate([np.array(t.y)[(np.array(t.x) >= x_min) & (np.array(t.x) <= x_max)] 
                                     for t in fig.data if t.x is not None and t.y is not None] or [[]])
            
            if y_vals.size > 0:
                y_min, y_max = np.nanmin(y_vals), np.nanmax(y_vals)
                pad_y = max((y_max - y_min) * 0.1, 0.1)
                
                layout_config['yaxis'] = dict(
                    range=[y_min - pad_y, y_max + pad_y], minallowed=y_min - pad_y, 
                    maxallowed=y_max + pad_y, autorange=False, title=y_axis_label
                )
            
            print(f"=== Plot x-axis range set to: {x_min:.1f} - {x_max:.1f} eV ===")
    
    fig.update_layout(**layout_config)
    return fig


@app.callback(
    Output("xas_plot", "figure", allow_duplicate=True),
    Input(struct_component.id(), "data"),
    Input('exp_spectrum_store', 'data'),
    Input('energy_shift_slider', 'value'),
    Input('comparison_range_store', 'data'),
    Input('structure_scores_store', 'data'),
    State('absorber', 'value'),
    State('st_source', 'children')
)
def predict_average_xas(st_data: dict, exp_data: dict, energy_shift: float, comparison_range, structure_scores, el_type, structure_source) -> Structure:
    if st_data is None and exp_data is None:
        raise PreventUpdate

    current_structure_id = get_current_structure_label(st_data, structure_source)
    

    selected_spectra = None
    if structure_scores:
        selected_spectra = [s for s in structure_scores if s.get('selected', False) and 'spectrum' in s]
        if len(selected_spectra) == 0:
            selected_spectra = None

    predicted_spectrum = None
    no_element = False

    if selected_spectra is None and st_data is not None:
        specs = st_data.get('xas', {})
        if len(specs) == 0:
            no_element = True
        else:
            specs_array = np.array(list(specs.values()))
            predicted_spectrum = specs_array.mean(axis=0)

    fig = build_figure_with_exp(
        predicted_spectrum, exp_data, el_type,
        is_average=True, no_element=no_element, sel_mismatch=False,
        energy_shift=energy_shift or 0, comparison_range=comparison_range,
        selected_spectra=selected_spectra, current_structure_id=current_structure_id
    )
    return fig


@app.callback(
    Output("xas_plot", "figure", allow_duplicate=True),
    Input(struct_component.id('scene'), "selectedObject"),
    State(struct_component.id(), 'data'),
    State('exp_spectrum_store', 'data'),
    State('absorber', 'value'),
    State('energy_shift_slider', 'value'),
    State('comparison_range_store', 'data'),
    State('st_source', 'children')
)
def predict_site_specific_xas(sel, st_data, exp_data, el_type, energy_shift, comparison_range, structure_source) -> Structure:
    if st_data is None:
        raise PreventUpdate

    current_structure_id = get_current_structure_label(st_data, structure_source)

    specs = st_data['xas']
    element = el_type.split(' ')[0]
    shift = energy_shift or 0
    if len(specs) == 0:
        fig = build_figure_with_exp(None, exp_data, el_type, is_average=False, no_element=True, sel_mismatch=False, energy_shift=shift, comparison_range=comparison_range, current_structure_id=current_structure_id)
    elif sel is None or len(sel) == 0:
        specs = np.array(list(specs.values()))
        spectrum = specs.mean(axis=0)
        fig = build_figure_with_exp(spectrum, exp_data, el_type, is_average=True, no_element=False, sel_mismatch=False, energy_shift=shift, comparison_range=comparison_range, current_structure_id=current_structure_id)
    else:
        st = Structure.from_dict(st_data)
        el_sel = sel[0]['tooltip'].split('(')[0].strip()
        pos_sel = np.array([float(x) for x in sel[0]['tooltip'].split('(')[1].split(')')[0].split(',')])
        frac_pos_sel = st.lattice.get_fractional_coords(pos_sel)
        dist = st.lattice.get_all_distances(frac_pos_sel, st.frac_coords)[0]
        i_site = np.argmin(dist)
        assert dist[i_site] < 0.01
        assert st[i_site].specie.symbol == el_sel
        if st[i_site].specie.symbol != element:
            fig = build_figure_with_exp(None, exp_data, el_type, is_average=False, no_element=False, sel_mismatch=True, energy_shift=shift, comparison_range=comparison_range, current_structure_id=current_structure_id)
        else:
            spectrum = np.array(specs[str(i_site)])
            site_structure_id = f"{current_structure_id} (site {i_site})" if current_structure_id else None
            fig = build_figure_with_exp(spectrum, exp_data, el_type, is_average=False, no_element=False, sel_mismatch=False, energy_shift=shift, comparison_range=comparison_range, current_structure_id=site_structure_id)
    return fig


@app.callback(
    Output(struct_component.id(), "data", allow_duplicate=True),
    Input('absorber', 'value'),
    State(struct_component.id(), "data"),
    Input('shakeup-store', 'data'),
)
def update_structure_by_absorber(el_type, st_data, shakeup_val) -> Structure:
    if st_data is None:
        raise PreventUpdate
    st = Structure.from_dict(st_data)
    st_dict = decorate_structure_with_xas(st, el_type, apply_shakeup=(shakeup_val == 'yes'))
    return st_dict


@app.callback(
    Output('energy_shift_slider', 'value'),
    Input('reset_shift_btn', 'n_clicks'),
    prevent_initial_call=True
)
def reset_energy_shift(n_clicks):
    if n_clicks is None:
        raise PreventUpdate
    return 0


@app.callback(
    Output('energy_shift_display', 'children'),
    Input('energy_shift_slider', 'value')
)
def update_shift_display(value):
    if value is None:
        value = 0
    return f"{value:+.1f} eV"


@app.callback(
    Output('sort_metric_store', 'data'),
    Input({'type': 'sort-metric-btn', 'metric': ALL}, 'n_clicks'),
    State('sort_metric_store', 'data'),
    prevent_initial_call=True
)
def handle_sort_click(n_clicks_list, current_sort_metric):
    """Handle clicks on sortable column headers to change the sort metric."""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id']
    import json
    try:
        id_str = trigger_id.rsplit('.', 1)[0]
        id_dict = json.loads(id_str)
        clicked_metric = id_dict['metric']
    except Exception:
        raise PreventUpdate

    return clicked_metric

@app.callback(
    Output('structure_scores_store', 'data'),
    Output('matching_results_table', 'children'),
    Output('comparison_range_store', 'data'),
    Input(struct_component.id(), "data"),
    Input('exp_spectrum_store', 'data'),
    Input('clear_scores_btn', 'n_clicks'),
    Input({'type': 'spectrum-checkbox', 'index': ALL}, 'value'),
    Input('sort_metric_store', 'data'),
    State('structure_scores_store', 'data'),
    State('st_source', 'children'),
    State('absorber', 'value'),
    prevent_initial_call=True
)
def update_matching_results(st_data, exp_data, clear_clicks, checkbox_values, sort_metric, existing_scores, structure_source, el_type):
    """Update the matching results table when a structure is loaded and experimental data is available."""
    ctx = dash.callback_context

    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id']

    if existing_scores is None:
        existing_scores = []

    if sort_metric is None:
        sort_metric = 'coss_deriv'

    if 'clear_scores_btn' in trigger_id:
        return [], html.Div("Upload experimental spectrum and load structures to see matching scores",
                           style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}), None

    if 'spectrum-checkbox' in trigger_id:
        for i, score_entry in enumerate(existing_scores):
            if i < len(checkbox_values):
                score_entry['selected'] = bool(checkbox_values[i])
        existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
        return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    if 'sort_metric_store' in trigger_id:
        existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
        return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    has_exp_data = exp_data is not None and 'energy' in exp_data and 'absorption' in exp_data

    if not has_exp_data:
        if len(existing_scores) == 0:
            return existing_scores, html.Div("Upload experimental spectrum first to enable matching",
                           style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}), None
        else:
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    if st_data is None:
        if len(existing_scores) == 0:
            return existing_scores, html.Div("Load a structure to see matching scores",
                           style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}), None
        else:
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    specs = st_data.get('xas', {})
    if len(specs) == 0:
        if len(existing_scores) == 0:
            return existing_scores, html.Div("No spectrum available for matching",
                           style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}), None
        else:
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    specs_array = np.array(list(specs.values()))
    predicted_spectrum = specs_array.mean(axis=0)
    element = el_type.split(' ')[0]
    energy = ene_grid[element].tolist()

    structure_id = None
    if structure_source and isinstance(structure_source, str):
        if structure_source.startswith("Current structure:"):
            structure_id = structure_source.split(":", 1)[1].strip()

    if structure_id is None:
        return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    match_result = get_spectrum_match_score(predicted_spectrum, exp_data, element)

    old_entry = next((s for s in existing_scores if s['structure_id'] == structure_id), None)
    was_selected = old_entry.get('selected', False) if old_entry else False

    updated_scores = [s for s in existing_scores if s['structure_id'] != structure_id]

    updated_scores.append({
        'structure_id': structure_id,
        'score': match_result['score'],
        'shift': match_result['shift'],
        'correlations': match_result['correlations'],
        'comparison_range': match_result['comparison_range'],
        'spectrum': predicted_spectrum.tolist(),
        'energy': energy,
        'element': element,
        'selected': was_selected
    })

    updated_scores = mark_active_structure_selected(updated_scores, structure_id)
    updated_scores = sort_scores_by_metric(updated_scores, sort_metric)

    return updated_scores, build_scores_table(updated_scores, sort_metric), match_result['comparison_range']

def build_matching_metadata(exp_data, scores, top_n=3):
    """
    Build metadata in the requested format:

    {
        experimental_spectrum_filename: {
            structure_name: {
                "pearson": score,
                "spearman": score
            },
            ...
        }
    }
    """
    if exp_data is None:
        raise ValueError("No experimental spectrum loaded")

    filename = exp_data.get("filename")
    if not filename:
        raise ValueError("Experimental spectrum filename is missing")

    if not scores:
        raise ValueError("No structure matching scores available")

    top_scores = scores[:top_n]

    structure_metadata = {}

    for entry in top_scores:
        structure_name = entry.get("structure_id", "unknown_structure")
        correlations = entry.get("correlations", {}) or {}

        structure_metadata[structure_name] = {
            "pearson": correlations.get("pearson"),
            "spearman": correlations.get("spearman"),
        }

    return {
        filename: structure_metadata
    }

def mark_active_structure_selected(scores, active_structure_id, only_active=True):
    """
    Mark the currently displayed structure as checked in the score table.

    If only_active=True, all other structures are unchecked so the table
    matches the structure currently shown in the viewer/plot.
    """
    if not scores or not active_structure_id:
        return scores

    active_structure_id = str(active_structure_id)

    for entry in scores:
        is_active = str(entry.get("structure_id")) == active_structure_id

        if is_active:
            entry["selected"] = True
        elif only_active:
            entry["selected"] = False

    return scores

def sort_scores_by_metric(scores, metric):
    """Sort scores list by the given metric. For normed_wasserstein, lower is better (sort ascending)."""
    if not scores:
        return scores

    reverse = metric != 'normed_wasserstein'

    def sort_key(entry):
        correlations = entry.get('correlations', {})
        val = correlations.get(metric, 0.0)
        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            return -999 if reverse else 999
        return val

    return sorted(scores, key=sort_key, reverse=reverse)


def build_scores_table(scores, sort_metric='coss_deriv'):
    """Build the HTML table for displaying structure scores with all metrics as sortable columns."""
    if not scores:
        return html.Div("No scores yet",
                       style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"})

    base_header_style = {
        "padding": "5px 4px",
        "textAlign": "right",
        "fontWeight": "600",
        "fontSize": "10px",
        "color": "#666",
        "borderBottom": "2px solid #e8e8e8",
        "backgroundColor": "#fafafa",
        "whiteSpace": "nowrap",
    }

    active_header_style = {
        **base_header_style,
        "color": "#333",
        "borderBottom": "2px solid #333",
        "backgroundColor": "#f0f0f0",
    }

    table_cell_style = {
        "padding": "5px 4px",
        "fontSize": "11px",
        "color": "#333",
        "borderBottom": "1px solid #eee",
        "textAlign": "right",
    }

    header_cells = [
        html.Th("", style={**base_header_style, "width": "28px", "textAlign": "center"}),
        html.Th("#", style={**base_header_style, "width": "22px", "textAlign": "center"}),
        html.Th("Structure", style={**base_header_style, "textAlign": "left", "minWidth": "70px"}),
        html.Th("Shift", style={**base_header_style, "width": "50px"}),
    ]

    for metric in ALL_METRICS:
        is_active = (metric == sort_metric)
        style = active_header_style if is_active else base_header_style
        arrow = " ▼" if is_active and metric != 'normed_wasserstein' else (" ▲" if is_active else "")

        header_cells.append(
            html.Th(
                html.Button(
                    METRIC_SHORT_NAMES[metric] + arrow,
                    id={'type': 'sort-metric-btn', 'metric': metric},
                    style={
                        "border": "none",
                        "background": "none",
                        "cursor": "pointer",
                        "fontWeight": "700" if is_active else "600",
                        "fontSize": "11px",
                        "color": "#333" if is_active else "#666",
                        "padding": "0",
                        "fontFamily": base_font,
                        "textDecoration": "none",
                        "whiteSpace": "nowrap",
                    },
                    title=f"Sort by {metric}" + (" (lower is better)" if metric == 'normed_wasserstein' else " (higher is better)"),
                ),
                style=style,
            )
        )

    header = html.Tr(header_cells)

    rows = []
    for rank, entry in enumerate(scores):
        correlations = entry.get('correlations', {})
        shift = entry.get('shift', 0.0)
        is_selected = entry.get('selected', False)

        row_cells = [
            html.Td(
                dcc.Checklist(
                    id={'type': 'spectrum-checkbox', 'index': rank},
                    options=[{'label': '', 'value': True}],
                    value=[True] if is_selected else [],
                    style={"margin": "0", "padding": "0"},
                    inputStyle={"marginRight": "0"}
                ),
                style={**table_cell_style, "textAlign": "center", "padding": "3px"}
            ),
            html.Td(rank + 1, style={**table_cell_style, "color": "#999", "fontWeight": "500", "textAlign": "center"}),
            html.Td(entry['structure_id'], style={
                **table_cell_style,
                "fontFamily": "monospace",
                "fontSize": "10px",
                "textAlign": "left",
                "maxWidth": "90px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }),
            html.Td(f"{shift:+.1f}", style={
                **table_cell_style,
                "fontSize": "10px",
                "color": "#666"
            }),
        ]

        for metric in ALL_METRICS:
            val = correlations.get(metric, None)
            is_sort_col = (metric == sort_metric)

            if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
                display_val = "—"
                score_color = "#999"
            else:
                display_val = f"{val:.3f}"
                if metric == 'normed_wasserstein':
                    if val <= 0.1:
                        score_color = "#28a745"
                    elif val <= 0.3:
                        score_color = "#ffc107"
                    else:
                        score_color = "#dc3545"
                else:
                    if val >= 0.9:
                        score_color = "#28a745"
                    elif val >= 0.7:
                        score_color = "#ffc107"
                    else:
                        score_color = "#dc3545"

            cell_style = {
                **table_cell_style,
                "fontWeight": "700" if is_sort_col else "400",
                "color": score_color,
                "fontSize": "11px" if is_sort_col else "10px",
                "backgroundColor": "#f8f8f8" if is_sort_col else "transparent",
            }

            row_cells.append(html.Td(display_val, style=cell_style))

        rows.append(html.Tr(row_cells))

    table = html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "fontFamily": base_font,
            "tableLayout": "auto",
        }
    )

    return html.Div(table, style={
        "overflowX": "auto",
        "fontSize": "11px",
    })

ctc.register_crystal_toolkit(app=app, layout=onmixas_layout)

def serve():
    if "MP_API_KEY" not in os.environ:
        print("Environment variable MP_API_KEY not found, "
              "please set your materials project API key to "
              "this environment variable before running this app")
        exit()
    start_tiled_listener()
    app.run(debug=False, port=8443, host='127.0.0.1')

if __name__ == "__main__":
    serve()