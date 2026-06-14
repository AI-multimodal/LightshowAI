import dash

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

def _radio_btn_styles(is_left_active, left_extra=None, right_extra=None):
    left  = {**(radio_left_active_style   if is_left_active else radio_left_inactive_style),  **(left_extra  or {})}
    right = {**(radio_right_inactive_style if is_left_active else radio_right_active_style),   **(right_extra or {})}
    return left, right
