import dash
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from components.styles import _radio_btn_styles

def register_callbacks(app):
    @app.callback(
        Output('norm-type-container', 'style'),
        Output('raw-type-container',  'style'),
        Output('raw-dropdown-container', 'style'),
        Input('exp-data-type-store', 'data')
    )
    def toggle_raw_norm_ui(data_type):
        if data_type == 'raw':
            return {'display': 'none'}, {'display': 'block'}, {'display': 'flex'}
        else:
            return {'display': 'block'}, {'display': 'none'}, {'display': 'none'}

    @app.callback(
        Output('btn-format-norm', 'style'),
        Output('btn-format-raw',  'style'),
        Output('btn-type-fluor',  'style'),
        Output('btn-type-trans',  'style'),
        Output('btn-flatten-yes', 'style'),
        Output('btn-flatten-no',  'style'),
        Output('btn-shakeup-on',  'style'),
        Output('btn-shakeup-off', 'style'),
        Input('exp-data-type-store', 'data'),
        Input('exp-raw-type-store',  'data'),
        Input('exp-flatten-store',  'data'),
        Input('shakeup-store',      'data')
    )
    def update_radio_button_styles(data_type, raw_type, flatten, shakeup):
        s1, s2 = _radio_btn_styles(data_type == 'norm')
        s3, s4 = _radio_btn_styles(raw_type == 'fluorescence')
        s5, s6 = _radio_btn_styles(flatten == 'yes')
        s7, s8 = _radio_btn_styles(shakeup == 'yes')
        return s1, s2, s3, s4, s5, s6, s7, s8

    @app.callback(
        Output('shakeup-store', 'data'),
        Input('btn-shakeup-on',  'n_clicks'),
        Input('btn-shakeup-off', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_shakeup_store(n_on, n_off):
        ctx = dash.callback_context
        if not ctx.triggered: raise PreventUpdate
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        return 'yes' if button_id == 'btn-shakeup-on' else 'no'

    @app.callback(
        Output('exp-data-type-store', 'data'),
        Input('btn-format-norm', 'n_clicks'),
        Input('btn-format-raw',  'n_clicks'),
        prevent_initial_call=True
    )
    def update_data_type(n_norm, n_raw):
        ctx = dash.callback_context
        if not ctx.triggered: raise PreventUpdate
        return 'norm' if ctx.triggered[0]['prop_id'].split('.')[0] == 'btn-format-norm' else 'raw'

    @app.callback(
        Output('exp-raw-type-store', 'data'),
        Input('btn-type-fluor', 'n_clicks'),
        Input('btn-type-trans', 'n_clicks'),
        prevent_initial_call=True
    )
    def update_raw_type(n_fluor, n_trans):
        ctx = dash.callback_context
        if not ctx.triggered: raise PreventUpdate
        return 'fluorescence' if ctx.triggered[0]['prop_id'].split('.')[0] == 'btn-type-fluor' else 'transmission'

    @app.callback(
        Output('exp-binning-store', 'data'),
        Input('binning-interval-slider', 'value'),
        prevent_initial_call=True
    )
    def update_binning(val):
        return val

    @app.callback(
        Output('exp-flatten-store', 'data'),
        Input('btn-flatten-yes', 'n_clicks'),
        Input('btn-flatten-no',  'n_clicks'),
        prevent_initial_call=True
    )
    def update_flatten(n_yes, n_no):
        ctx = dash.callback_context
        if not ctx.triggered: raise PreventUpdate
        return 'yes' if ctx.triggered[0]['prop_id'].split('.')[0] == 'btn-flatten-yes' else 'no'

    @app.callback(
        Output('shakeup-toggle-container', 'style'),
        Input('absorber', 'value')
    )
    def update_shakeup_visibility(absorber):
        if not absorber:
            return {'display': 'none'}
        return {'display': 'block', 'marginTop': '12px'} if 'VASP' in absorber else {'display': 'none'}
