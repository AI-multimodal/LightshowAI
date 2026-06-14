import dash
import pandas as pd
import numpy as np
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
from lightshowai.postprocess.normalize import normalizeSpectrum, spectrum_from_new_csv
from components.styles import button_secondary_style
from dash import html, dcc
import pathlib
import os

from core.parsing import parse_file_columns

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


def register_callbacks(app):
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
                None, None, [], [], None, None, hidden_style, [],
                html.Span(f"Error: {error_msg}", style={'color': 'red'}),
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                [], [], [], None, None, None, None, "manual",
            )

        columns = result['columns']
        default_x = result.get('auto_x_col', 0)
        default_y = result.get('auto_y_col', 1 if len(columns) > 1 else 0)
        default_x = min(default_x, len(columns) - 1)
        default_y = min(default_y, len(columns) - 1)

        options, col_definition, info_text = _build_column_ui(columns, filename, default_x, default_y)
        raw_options, raw_energy_val, raw_itiff_val, raw_i0_val = _raw_dropdown_defaults(columns, raw_type=raw_type or 'transmission')
        detected_format = result.get('detected_format')
        default_data_type = 'raw' if detected_format == 'new_xas_csv' else 'norm'
        material_name_from_file = pathlib.Path(filename).stem if filename else ""

        return (
            result, columns, options, options, default_x, default_y,
            visible_style, col_definition, html.Span(info_text, style={'color': 'blue'}),
            dash.no_update, dash.no_update, material_name_from_file, default_data_type,
            raw_options, raw_options, raw_options, raw_energy_val, raw_itiff_val, raw_i0_val,
            None, "manual",
        )

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
    def apply_column_selection(n_clicks, raw_data, columns, x_col_idx, y_col_idx, material_name, data_type, raw_mode, bin_mode, flattenmode, raw_energy_idx, raw_itiff_idx, raw_i0_idx):
        if n_clicks is None or raw_data is None:
            raise PreventUpdate
        try:
            if columns is None:
                return None, html.Span("No column information available", style={'color': 'red'})
            filename = raw_data.get('filename', 'experimental_spectrum')
            display_name = material_name.strip() if material_name and material_name.strip() else filename
            data_type = data_type or 'norm'
            raw_mode = raw_mode or 'transmission'
            apply_flat = flattenmode == 'yes'
            raw_matrix = raw_data.get('data', [])
            if not raw_matrix:
                return None, html.Span("No experimental data available", style={'color': 'red'})

            if data_type == 'raw':
                is_fluor = raw_mode == 'fluorescence'
                signal_name = 'iff' if is_fluor else 'it'
                required = {'energy': raw_energy_idx, 'i0': raw_i0_idx, signal_name: raw_itiff_idx}
                missing = [name for name, idx in required.items() if idx is None]
                if missing:
                    return None, html.Span(f"Please select all required raw columns: {', '.join(missing)}", style={'color': 'red'})
                max_idx = len(raw_matrix) - 1
                selected_indices = [raw_energy_idx, raw_i0_idx, raw_itiff_idx]
                if any(idx < 0 or idx > max_idx for idx in selected_indices):
                    return None, html.Span("One or more selected raw columns are out of range", style={'color': 'red'})
                energy = np.array(raw_matrix[raw_energy_idx], dtype=float)
                i0 = np.array(raw_matrix[raw_i0_idx], dtype=float)
                signal = np.array(raw_matrix[raw_itiff_idx], dtype=float)
                min_len = min(len(energy), len(i0), len(signal))
                energy, i0, signal = energy[:min_len], i0[:min_len], signal[:min_len]
                finite_mask = np.isfinite(energy) & np.isfinite(i0) & np.isfinite(signal)
                energy, i0, signal = energy[finite_mask], i0[finite_mask], signal[finite_mask]
                if len(energy) < 2:
                    return None, html.Span("Not enough valid raw data points", style={'color': 'red'})
                df_raw = pd.DataFrame({'energy': energy, 'i0': i0, signal_name: signal})
                apply_bin = bin_mode > 0 if isinstance(bin_mode, (int, float)) else False
                spec, meta = spectrum_from_new_csv(df_raw, mode=raw_mode, apply_binning=apply_bin, bin_interval=bin_mode if apply_bin else 0.25)
                spec = normalizeSpectrum(spec, flatten=apply_flat)
                x_data, y_data = spec[:, 0], spec[:, 1]
                x_label, y_label = meta.get('x_label', 'Energy'), f"Normalized μ(E) [{meta.get('mode', raw_mode).capitalize()}]"
            else:
                if x_col_idx is None or y_col_idx is None:
                    return None, html.Span("Please select both X and Y axis columns", style={'color': 'red'})
                max_idx = len(raw_matrix) - 1
                if x_col_idx < 0 or x_col_idx > max_idx or y_col_idx < 0 or y_col_idx > max_idx:
                    return None, html.Span("Selected X or Y column is out of range", style={'color': 'red'})
                x_data, y_data = np.array(raw_matrix[x_col_idx], dtype=float), np.array(raw_matrix[y_col_idx], dtype=float)
                min_len = min(len(x_data), len(y_data))
                x_data, y_data = x_data[:min_len], y_data[:min_len]
                finite_mask = np.isfinite(x_data) & np.isfinite(y_data)
                x_data, y_data = x_data[finite_mask], y_data[finite_mask]
                if len(x_data) < 2:
                    return None, html.Span("Not enough valid data points", style={'color': 'red'})
                sort_idx = np.argsort(x_data)
                x_data, y_data = x_data[sort_idx], y_data[sort_idx]
                x_label, y_label = columns[x_col_idx]['name'], columns[y_col_idx]['name']

            result = {'energy': x_data.tolist(), 'absorption': y_data.tolist(), 'filename': filename, 'material_name': display_name, 'x_label': x_label, 'y_label': y_label, 'data_type': data_type, 'raw_mode': raw_mode if data_type == 'raw' else None}
            x_min, x_max = float(np.min(x_data)), float(np.max(x_data))
            info_text = f"✓ {display_name} ({len(x_data)} points, {x_label}: {x_min:.1f}-{x_max:.1f})"

            try:
                from services.chatbot import CHATBOT_PLOT_ROOT
                shared_dat = CHATBOT_PLOT_ROOT / "current_experimental.dat"
                lines = [f"# Experimental XANES spectrum: {display_name}", f"# Source: {filename}", f"# {x_label}  {y_label}"]
                for e, a in zip(x_data.tolist(), y_data.tolist()):
                    lines.append(f"{e}  {a}")
                shared_dat.write_text("\n".join(lines) + "\n")
            except Exception as _write_err:
                print(f"[xas_ui] failed to write shared experimental dat: {_write_err}")

            return result, html.Span(info_text, style={'color': 'green'})
        except Exception as e:
            print(f"Error applying column selection: {e}")
            import traceback
            traceback.print_exc()
            return None, html.Span(f"Error: {str(e)}", style={'color': 'red'})

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
        if n_clicks is None or columns is None:
            raise PreventUpdate
        for i, new_name in enumerate(new_names):
            if i < len(columns):
                columns[i]['name'] = new_name.strip() if new_name else f"Column {i+1}"
        options = [{'label': f"{col['name']} ({col['num_values']} pts)", 'value': col['index']} for col in columns]
        return columns, options, options, html.Span("Column names updated!", style={'color': 'green'})
