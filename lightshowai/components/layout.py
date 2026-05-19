from dash import dcc, html
from crystal_toolkit.helpers.layouts import Column, Columns, Loading
from services.chatbot import CHATBOT_URL
from .styles import (
    base_font, section_header_style, column_header_style, 
    input_label_style, card_style, button_primary_style, 
    button_secondary_style, radio_left_active_style, 
    radio_right_inactive_style, radio_row_style, radio_label_style,
    radio_left_inactive_style, radio_right_active_style
)
from .inputs import (
    shakeup_store, batch_processing_store, absorber_dropdown,
    exp_upload_component, exp_material_name_input, mpid_list_input,
    mpid_search_btn, exp_raw_data_store, exp_columns_store,
    exp_spectrum_store, exp_column_definition_area, exp_x_axis_dropdown,
    exp_y_axis_dropdown, exp_raw_energy_dropdown, exp_raw_itiff_dropdown,
    exp_raw_i0_dropdown, exp_apply_btn, clear_exp_btn,
    batch_upload_component, tiled_poll_interval, pending_spectra_store,
    last_load_source_store, chatbot_structure_poll_interval,
    chatbot_structure_meta_store, matching_results_store,
    structure_scores_store, comparison_range_store,
    selected_spectra_store, sort_metric_store, matching_metadata_store
)
from .viewer import struct_component, chatbot_structure_iframe, chatbot_structure_hint
from .plots import xas_plot

def get_layout():
    st_source = html.Div(id='st_source', children='No structure loaded yet',
                         style={'fontSize': '13px', 'color': '#555', 'fontWeight': '500', 'fontFamily': base_font})

    return html.Div([
        tiled_poll_interval,
        chatbot_structure_poll_interval,
        chatbot_structure_meta_store,
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
                                ], style={"marginTop": "12px", "marginBottom": "15px"}),
                            ],
                            style={"display": "none"}
                        ),

                        html.Div(id='exp_file_info', children='No experimental spectrum loaded',
                                 style={'fontSize': '11px', 'color': '#888', 'marginTop': '10px', 'fontFamily': base_font}),
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
                            id="structure_component_wrapper",
                            style={'minHeight': '200px', 'width': '100%', 'position': 'relative', 'display': 'block'}
                        ),
                        chatbot_structure_iframe,
                        chatbot_structure_hint,
                    ], style=card_style),

                    # XAS Model Prediction Card
                    html.Div([
                        html.Div("XAS Machine Learning Model", style=section_header_style),
                        absorber_dropdown,
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
                            style={'display': 'block', 'marginTop': '12px'} if absorber_dropdown.value and 'VASP' in absorber_dropdown.value else {'display': 'none'}
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

                                    matching_metadata_store,
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
