import dash
import queue
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash import html
from datetime import datetime
from services.tiled_client import _tiled_spectra_cache, _tiled_spectra_cache_lock, _tiled_queue
from components.viewer import struct_component
from components.styles import button_primary_style, button_secondary_style, input_label_style
from .upload_cb import _build_column_ui, _raw_dropdown_defaults

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

def register_callbacks(app):
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
        if raw_data is None or load_source != "pending":
            raise PreventUpdate
        return (current_clicks or 0) + 1

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
