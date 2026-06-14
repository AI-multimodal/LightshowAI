import dash
import numpy as np
import pandas as pd
import pathlib
import tempfile
from zipfile import ZipFile
from base64 import b64encode
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from pymatgen.core.structure import Structure
from core.math_utils import apply_shakeup_if_needed, ene_grid
from components.plots import build_figure_with_exp
from components.viewer import struct_component

def get_current_structure_label(st_data, structure_source=None):
    if isinstance(st_data, dict):
        for key in ("label", "structure_id", "filename", "material_id"):
            value = st_data.get(key)
            if value:
                return str(value)
    if structure_source and isinstance(structure_source, str):
        if structure_source.startswith("Current structure:"):
            return structure_source.split(":", 1)[1].strip()
        if structure_source.startswith("Batch loaded:") or structure_source.startswith("Loaded "):
            return None
        return structure_source
    return None

def register_callbacks(app):
    @app.callback(
        Output("xas_plot", "figure", allow_duplicate=True),
        Input(struct_component.id(), "data"),
        Input('exp_spectrum_store', 'data'),
        Input('energy_shift_slider', 'value'),
        Input('comparison_range_store', 'data'),
        Input('structure_scores_store', 'data'),
        State('absorber', 'value'),
        State('st_source', 'children'),
        State('shakeup-store', 'data')
    )
    def predict_average_xas(st_data: dict, exp_data: dict, energy_shift: float, comparison_range, structure_scores, el_type, structure_source, shakeup_val):
        if st_data is None and exp_data is None:
            raise PreventUpdate
        current_structure_id = get_current_structure_label(st_data, structure_source)
        has_scores = structure_scores is not None and len(structure_scores) > 0
        selected_spectra =[]
        if has_scores:
            selected_spectra =[s for s in structure_scores if s.get('selected', False) and 'spectrum' in s]
        predicted_spectrum, no_element = None, False
        if not has_scores and st_data is not None:
            specs = st_data.get('xas', {})
            if len(specs) == 0:
                no_element = True
            else:
                element = el_type.split(' ')[0]
                processed_specs = apply_shakeup_if_needed(specs, element, el_type, shakeup_val)
                specs_array = np.array(list(processed_specs.values()))
                predicted_spectrum = specs_array.mean(axis=0)
        return build_figure_with_exp(predicted_spectrum, exp_data, el_type, is_average=True, no_element=no_element, sel_mismatch=False, energy_shift=energy_shift or 0, comparison_range=comparison_range, selected_spectra=selected_spectra, current_structure_id=current_structure_id)

    @app.callback(
        Output("xas_plot", "figure", allow_duplicate=True),
        Input(struct_component.id('scene'), "selectedObject"),
        State(struct_component.id(), 'data'),
        State('exp_spectrum_store', 'data'),
        State('absorber', 'value'),
        State('energy_shift_slider', 'value'),
        State('comparison_range_store', 'data'),
        State('st_source', 'children'),
        State('shakeup-store', 'data')
    )
    def predict_site_specific_xas(sel, st_data, exp_data, el_type, energy_shift, comparison_range, structure_source, shakeup_val):
        if st_data is None:
            raise PreventUpdate
        current_structure_id = get_current_structure_label(st_data, structure_source)
        element = el_type.split(' ')[0]
        specs = apply_shakeup_if_needed(st_data.get('xas', {}), element, el_type, shakeup_val)
        shift = energy_shift or 0
        if len(specs) == 0:
            fig = build_figure_with_exp(None, exp_data, el_type, is_average=False, no_element=True, sel_mismatch=False, energy_shift=shift, comparison_range=comparison_range, current_structure_id=current_structure_id)
        elif sel is None or len(sel) == 0:
            specs_arr = np.array(list(specs.values()))
            spectrum = specs_arr.mean(axis=0)
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
            fn_spec = tmpdir / ("no_spectrum.csv" if len(d_xas) == 0 else "spectrum.csv")
            fn_poscar = tmpdir / 'POSCAR'
            st.to(fn_poscar, fmt='poscar')
            df.to_csv(fn_spec, float_format="%.3f", header=False)
            zip_fn = tmpdir / f'OmniXAS_{el}_{theory}_Prediction_{n_clicks}.zip'
            with ZipFile(zip_fn, mode="w") as zip_file:
                for fn in [fn_poscar, fn_spec]:
                    zip_file.write(fn, arcname=fn.name)
            bytes_content = b64encode(zip_fn.read_bytes()).decode("ascii")
            download_data = {"content": bytes_content, "base64": True, "type": "application/zip", "filename": zip_fn.name}
        return download_data
