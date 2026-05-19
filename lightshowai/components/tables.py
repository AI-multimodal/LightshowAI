from dash import dcc, html
from core.matching import ALL_METRICS, METRIC_SHORT_NAMES
from .styles import base_font

# Cache for build_scores_table to avoid rebuilding when scores haven't changed
_scores_cache = {'scores': None, 'table': None}

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

def build_scores_table(scores, sort_metric='coss_deriv'):
    """Build the HTML table for displaying structure scores with all metrics as sortable columns."""
    if not scores:
        _scores_cache['scores'] = None
        _scores_cache['table'] = None
        return html.Div("No scores yet",
                       style={"color": "#999", "fontSize": "12px", "textAlign": "center", "padding": "20px"})

    # Return cached table if scores haven't changed
    current_key = tuple(
        (s.get('structure_id', ''), s.get('selected', False))
        for s in scores
    )
    if current_key == _scores_cache.get('scores') and sort_metric == _scores_cache.get('sort_metric'):
        return _scores_cache['table']

    all_selected = all(entry.get('selected', False) for entry in scores)

    header_cells = [
        html.Th(
            dcc.Checklist(
                id={'type': 'select-all-checkbox'},
                options=[{'label': '', 'value': True}],
                value=[True] if all_selected else [],
                style={"margin": "0", "padding": "0"},
                inputStyle={"marginRight": "0"}
            ),
            style={**base_header_style, "width": "28px", "textAlign": "center"}
        ),
        html.Th("#", style={**base_header_style, "width": "22px", "textAlign": "center"}),
        html.Th("Structure", style={**base_header_style, "textAlign": "left", "minWidth": "70px"}),
        html.Th("Shift", style={**base_header_style, "width": "50px"}),
    ]

    for metric in ALL_METRICS:
        is_active = (metric == sort_metric)
        style = active_header_style if is_active else base_header_style
        # In a generic environment, we can't easily check for normed_wasserstein without importing core.matching or something
        # but we know it from the logic.
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
        import numpy as np # Needed for nan/inf check if not already imported
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

    _scores_cache['scores'] = current_key
    _scores_cache['sort_metric'] = sort_metric
    _scores_cache['table'] = html.Div(table, style={
        "overflowX": "auto",
        "fontSize": "11px",
    })
    return _scores_cache['table']
