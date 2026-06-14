import numpy as np
import plotly.graph_objects as go
from dash import dcc
from core.math_utils import ene_grid

xas_plot = dcc.Graph(
    id='xas_plot',
    style={'height': '420px'},
    config={'responsive': True, 'doubleClick': 'reset'}
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
