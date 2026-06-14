import dash
import json
import numpy as np
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
from dash import html
import plotly.graph_objects as go
from core.math_utils import apply_shakeup_if_needed, ene_grid
from core.matching import (
    get_spectrum_match_score, sort_scores_by_metric, 
    mark_active_structure_selected, build_matching_metadata
)
from components.tables import build_scores_table
from services.tiled_client import update_tiled_lightshowai_metadata
from components.viewer import struct_component

def register_callbacks(app):
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
        try:
            id_str = trigger_id.rsplit('.', 1)[0]
            id_dict = json.loads(id_str)
            clicked_metric = id_dict['metric']
        except Exception:
            raise PreventUpdate
        return clicked_metric

    @app.callback(
        Output('structure_scores_store', 'data', allow_duplicate=True),
        Output('matching_results_table', 'children', allow_duplicate=True),
        Output('comparison_range_store', 'data', allow_duplicate=True),
        Output(struct_component.id(), 'data', allow_duplicate=True),
        Output('st_source', 'children', allow_duplicate=True),
        Output('selected_spectra_store', 'data', allow_duplicate=True),
        Output('xas_plot', 'figure', allow_duplicate=True),
        Input('clear_scores_btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def handle_clear_scores(n_clicks):
        """Handle entirely clearing out structures, graphs, and scores."""
        if not n_clicks:
            raise PreventUpdate
            
        return (
            [], 
            html.Div("Upload experimental spectrum and load structures to see matching scores",
                     style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}),
            None, 
            None,        # Clears the underlying data store
            "No structure loaded yet", 
            [], 
            go.Figure()
        )

    @app.callback(
        Output('structure_scores_store', 'data'),
        Output('matching_results_table', 'children'),
        Output('comparison_range_store', 'data'),
        Input('exp_spectrum_store', 'data'),
        Input({'type': 'spectrum-checkbox', 'index': ALL}, 'value'),
        Input('sort_metric_store', 'data'),
        Input('shakeup-store', 'data'),
        Input({'type': 'select-all-checkbox'}, 'value'),
        State('structure_scores_store', 'data'),
        State('absorber', 'value'),
        prevent_initial_call=True
    )
    def update_matching_results(exp_data, checkbox_values, sort_metric, shakeup_val, select_all_value, existing_scores, el_type):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id']
        
        if existing_scores is None:
            existing_scores = []
        if sort_metric is None:
            sort_metric = 'coss_deriv'
            
        # 1. Handle "Select All" checkbox
        if 'select-all-checkbox' in trigger_id:
            for s in existing_scores:
                s['selected'] = bool(select_all_value)
            existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update
            
        # 2. Handle individual structure checkboxes
        if 'spectrum-checkbox' in trigger_id:
            if checkbox_values:
                for i, score_entry in enumerate(existing_scores):
                    if i < len(checkbox_values):
                        score_entry['selected'] = bool(checkbox_values[i])
            existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update
            
        # 3. Handle sorting column changes
        if 'sort_metric_store' in trigger_id:
            existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
            return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update
            
        # 4. Handle Shakeup or Experimental Data changes (Recalculate ALL scores)
        if 'shakeup-store' in trigger_id or 'exp_spectrum_store' in trigger_id:
            if len(existing_scores) == 0:
                return existing_scores, html.Div("Load a structure to see matching scores",
                               style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"}), dash.no_update
                               
            has_exp_data = exp_data is not None and 'energy' in exp_data and 'absorption' in exp_data
            
            for s in existing_scores:
                st_dict = s.get('st_data', {})
                specs = st_dict.get('xas', {})
                if not specs: 
                    continue
                    
                processed_specs = apply_shakeup_if_needed(specs, s['element'], el_type, shakeup_val)
                specs_array = np.array(list(processed_specs.values()))
                predicted_spectrum = specs_array.mean(axis=0)
                s['spectrum'] = predicted_spectrum.tolist()
                
                if has_exp_data:
                    match_result = get_spectrum_match_score(predicted_spectrum, exp_data, s['element'])
                    s['score'] = match_result['score']
                    s['shift'] = match_result['shift']
                    s['correlations'] = match_result['correlations']
                    s['comparison_range'] = match_result['comparison_range']
                else:
                    s['score'] = 0.0
                    s['shift'] = 0.0
                    s['correlations'] = {}
                    s['comparison_range'] = None
                    
            existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
            
            comp_range = None
            if len(existing_scores) > 0:
                active_entry = next((e for e in existing_scores if e.get('selected')), existing_scores[0])
                comp_range = active_entry.get('comparison_range')
                
            return existing_scores, build_scores_table(existing_scores, sort_metric), comp_range

        return existing_scores, build_scores_table(existing_scores, sort_metric), dash.no_update

    @app.callback(
        Output(struct_component.id(), 'data', allow_duplicate=True),
        Output('st_source', 'children', allow_duplicate=True),
        Input({'type': 'spectrum-checkbox', 'index': ALL}, 'value'),
        State('structure_scores_store', 'data'),
        prevent_initial_call=True,
    )
    def display_latest_checked_structure(checkbox_values, scores):
        ctx = dash.callback_context
        if not ctx.triggered: raise PreventUpdate
        trigger_prop = ctx.triggered[0]['prop_id']
        
        # Only update the viewer when a checkbox is explicitly CHECKED (True), not unchecked
        if 'spectrum-checkbox' not in trigger_prop or not ctx.triggered[0]['value']: 
            raise PreventUpdate
            
        try:
            rank = json.loads(trigger_prop.rsplit('.', 1)[0])['index']
        except Exception: 
            raise PreventUpdate
            
        if not scores or rank >= len(scores): 
            raise PreventUpdate
            
        entry = scores[rank]
        if entry.get('st_data') is None: 
            raise PreventUpdate
            
        return entry['st_data'], f"Current structure: {entry['structure_id']}"

    @app.callback(
        Output("upload_metadata_status", "children"),
        Output("upload_metadata_status", "style"),
        Input("upload_metadata_btn", "n_clicks"),
        State("exp_spectrum_store", "data"),
        State("structure_scores_store", "data"),
        prevent_initial_call=True,
    )
    def handle_upload_metadata_click(n_clicks, exp_data, scores):
        if n_clicks is None: raise PreventUpdate
        try:
            metadata = build_matching_metadata(exp_data, scores)
            update_tiled_lightshowai_metadata(exp_data, metadata)
            return "✓ Successfully uploaded to Tiled", {"color": "green", "fontSize": "11px", "marginTop": "8px"}
        except Exception as e:
            return f"✗ Error: {e}", {"color": "red", "fontSize": "11px", "marginTop": "8px"}

    @app.callback(
        Output("upload_metadata_container", "style"),
        Input("exp_spectrum_store", "data"),
        Input("structure_scores_store", "data"),
        State("last_load_source_store", "data"),
    )
    def render_metadata_upload_section(exp_data, scores, load_source):
        if load_source == "pending" and exp_data and scores and len(scores) > 0:
            return {"display": "block"}
        return {"display": "none"}