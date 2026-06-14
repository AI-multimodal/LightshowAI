from dash import dcc, html
import crystal_toolkit.components as ctc
from core.math_utils import xas_model_names
from .styles import (
    base_font, button_primary_style, button_secondary_style, 
    input_label_style, radio_left_active_style, radio_right_inactive_style,
    radio_row_style, radio_label_style
)

shakeup_store = dcc.Store(id='shakeup-store', data='no')

# Store for batch processing status
batch_processing_store = dcc.Store(id='batch_processing_store', data={'status': 'idle', 'processed': 0, 'total': 0})

absorber_dropdown = dcc.Dropdown(xas_model_names, clearable=False, value='Ti VASP', id='absorber')

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
        "minHeight": "105px",
        "padding": "10px 12px",
        "borderRadius": "6px",
        "border": "1px solid #ddd",
        "fontSize": "12px",
        "boxSizing": "border-box",
        "resize": "vertical",
        "fontFamily": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    }
)

mpid_search_btn = html.Button(
    "Search MP IDs",
    id="mpid_search_btn",
    style={
        **button_primary_style,
        "width": "100%",
        "padding": "12px",
        "fontSize": "12px",
        "marginTop": "8px",
        "marginBottom": "12px",
        "marginRight": "0",
        "borderRadius": "6px"
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

# Tiled and Chatbot Stores
tiled_poll_interval = dcc.Interval(
    id="tiled_poll_interval",
    interval=1000,   # 1 second
    n_intervals=0
)

pending_spectra_store = dcc.Store(id="pending_spectra_store", data=[])
last_load_source_store = dcc.Store(id="last_load_source_store", data=None)

chatbot_structure_poll_interval = dcc.Interval(
    id="chatbot_structure_poll_interval",
    interval=2500,
    n_intervals=0,
)

chatbot_structure_meta_store = dcc.Store(id="chatbot_structure_meta_store", data=None)

# Matching Stores
matching_results_store = dcc.Store(id='matching_results_store', data=[])
structure_scores_store = dcc.Store(id='structure_scores_store', data=[])
comparison_range_store = dcc.Store(id='comparison_range_store', data=None)
selected_spectra_store = dcc.Store(id='selected_spectra_store', data=[])
sort_metric_store = dcc.Store(id='sort_metric_store', data='coss_deriv')
matching_metadata_store = dcc.Store(id="matching_metadata_store", data=None)
