import dash
import numpy as np
import pathlib
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash import html
from pymatgen.core.structure import Structure
from mp_api.client import MPRester
from lightshowai.models import predict
from core.parsing import parse_mpid_list, parse_structure_file
from core.math_utils import apply_shakeup_if_needed, decorate_structure_with_xas, ene_grid
from core.matching import get_spectrum_match_score, mark_active_structure_selected, sort_scores_by_metric
from components.tables import build_scores_table
from components.viewer import struct_component

def register_callbacks(app):
    @app.callback(
        Output(struct_component.id(), "data", allow_duplicate=True),
        Output('st_source', "children", allow_duplicate=True),
        Output('structure_scores_store', 'data', allow_duplicate=True),
        Output('matching_results_table', 'children', allow_duplicate=True),
        Output('comparison_range_store', 'data', allow_duplicate=True),
        Output('mpid_list_input', 'value'),
        Input("mpid_search_btn", "n_clicks"),
        State("mpid_list_input", "value"),
        State('absorber', 'value'),
        State('shakeup-store', 'data'),
        State('exp_spectrum_store', 'data'),
        State('structure_scores_store', 'data'),
        State('sort_metric_store', 'data'),
        prevent_initial_call=True
    )
    def update_structure_by_mpid(n_clicks, mpid_list_value, el_type, shakeup_val, exp_data, existing_scores, sort_metric):
        if not n_clicks:
            raise PreventUpdate

        if existing_scores is None:
            existing_scores = []

        if sort_metric is None:
            sort_metric = "coss_deriv"

        mpids = parse_mpid_list(mpid_list_value)
        if not mpids:
            raise PreventUpdate

        element, theory = el_type.split(" ")
        has_exp_data = exp_data is not None and "energy" in exp_data and "absorption" in exp_data

        successful = 0
        failed = 0
        failed_ids = []
        comparison_range = None
        last_st_dict = None
        last_mpid = None

        with MPRester() as mpr:
            docs = mpr.materials.search(
                material_ids=mpids,
                fields=["material_id", "structure"],
            )

        docs_by_id = {str(doc.material_id): doc for doc in docs}

        for mpid in mpids:
            try:
                doc = docs_by_id.get(mpid)
                if doc is None or doc.structure is None:
                    failed += 1
                    failed_ids.append(f"{mpid} (not found)")
                    continue

                st = doc.structure
                if not isinstance(st, Structure):
                    failed += 1
                    failed_ids.append(f"{mpid} (invalid structure)")
                    continue

                if element not in st.composition:
                    failed += 1
                    failed_ids.append(f"{mpid} (no {element})")
                    continue
                print(f"Predicting spectrum for {mpid} with element {element} and theory {theory}")
                specs = predict(st, element, theory)
                if len(specs) == 0:
                    failed += 1
                    failed_ids.append(f"{mpid} (no spectrum)")
                    continue

                processed_specs = apply_shakeup_if_needed(specs, element, el_type, shakeup_val)
                specs_array = np.array(list(processed_specs.values()))
                predicted_spectrum = specs_array.mean(axis=0)
                energy = ene_grid[element].tolist()

                if has_exp_data:
                    match_result = get_spectrum_match_score(predicted_spectrum, exp_data, element)
                else:
                    match_result = {
                        "score": 0.0,
                        "correlations": {},
                        "shift": 0.0,
                        "comparison_range": None
                    }

                st_dict = st.as_dict()
                st_dict["xas"] = specs
                st_dict["label"] = mpid
                st_dict["material_id"] = mpid
                st_dict["structure_id"] = mpid

                old_entry = next((s for s in existing_scores if s["structure_id"] == mpid), None)
                was_selected = old_entry.get("selected", False) if old_entry else False

                existing_scores = [s for s in existing_scores if s["structure_id"] != mpid]

                existing_scores.append({
                    "structure_id": mpid,
                    "score": match_result["score"],
                    "shift": match_result["shift"],
                    "correlations": match_result["correlations"],
                    "comparison_range": match_result["comparison_range"],
                    "spectrum": predicted_spectrum.tolist(),
                    "energy": energy,
                    "element": element,
                    "selected": was_selected,
                    "st_data": st_dict,
                })

                if match_result["comparison_range"] is not None:
                    comparison_range = match_result["comparison_range"]

                last_st_dict = st_dict
                last_mpid = mpid
                successful += 1

            except Exception as e:
                print(f"Error processing {mpid}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
                failed_ids.append(mpid)
        existing_scores = mark_active_structure_selected(existing_scores, last_mpid)
        existing_scores = sort_scores_by_metric(existing_scores, sort_metric)

        if successful == 0:
            source_text = f"No valid structures loaded. Failed: {failed}"
            return (
                dash.no_update,
                source_text,
                existing_scores,
                build_scores_table(existing_scores, sort_metric),
                comparison_range,
                dash.no_update
            )

        if successful == 1:
            source_text = f"Current structure: {last_mpid}"
        else:
            source_text = f"Loaded {successful} MP structures"

        if failed > 0:
            source_text += f" | Failed: {failed}"

        return (
            last_st_dict,
            source_text,
            existing_scores,
            build_scores_table(existing_scores, sort_metric),
            comparison_range,
            ""
        )

    @app.callback(
        Output('structure_scores_store', 'data', allow_duplicate=True),
        Output('matching_results_table', 'children', allow_duplicate=True),
        Output('comparison_range_store', 'data', allow_duplicate=True),
        Output('batch_status', 'children'),
        Output('batch_structure_upload', 'contents'),
        Output(struct_component.id(), "data", allow_duplicate=True),
        Output('st_source', "children", allow_duplicate=True),
        Input('batch_structure_upload', 'contents'),
        State('batch_structure_upload', 'filename'),
        State('exp_spectrum_store', 'data'),
        State('absorber', 'value'),
        State('structure_scores_store', 'data'),
        State('sort_metric_store', 'data'),
        State('shakeup-store', 'data'),
        prevent_initial_call=True
    )
    def handle_batch_upload(contents_list, filenames_list, exp_data, el_type, existing_scores, sort_metric, shakeup_val):
        if contents_list is None or len(contents_list) == 0:
            raise PreventUpdate

        if existing_scores is None:
            existing_scores = []

        if sort_metric is None:
            sort_metric = 'coss_deriv'

        has_exp_data = exp_data is not None and 'energy' in exp_data and 'absorption' in exp_data
        element = el_type.split(' ')[0]

        successful = 0
        failed = 0
        failed_files = []
        last_st_dict = None
        last_filename = None
        last_structure_id = None
        comparison_range = None

        for contents, filename in zip(contents_list, filenames_list):
            try:
                st = parse_structure_file(contents, filename)
                if st is None:
                    failed += 1
                    failed_files.append(filename)
                    continue

                if element not in st.composition:
                    print(f"Structure {filename} does not contain {element}, skipping...")
                    failed += 1
                    failed_files.append(f"{filename} (no {element})")
                    continue

                print("XAS Spectrum generated for structure:", st, element, el_type.split(' ')[1])
                specs = predict(st, element, el_type.split(' ')[1])
                
                if len(specs) == 0:
                    failed += 1
                    failed_files.append(f"{filename} (no spectrum)")
                    continue

                processed_specs = apply_shakeup_if_needed(specs, element, el_type, shakeup_val)
                specs_array = np.array(list(processed_specs.values()))
                predicted_spectrum = specs_array.mean(axis=0)
                energy = ene_grid[element].tolist()
                structure_id = pathlib.Path(filename).stem

                if has_exp_data:
                    match_result = get_spectrum_match_score(predicted_spectrum, exp_data, element)
                else:
                    match_result = {
                        'score': 0.0,
                        'correlations': {},
                        'shift': 0.0,
                        'comparison_range': None
                    }

                st_dict = st.as_dict()
                st_dict["xas"] = specs
                st_dict["label"] = pathlib.Path(filename).stem
                st_dict["filename"] = filename
                st_dict["structure_id"] = structure_id

                old_entry = next((s for s in existing_scores if s['structure_id'] == structure_id), None)
                was_selected = old_entry.get('selected', False) if old_entry else False
                existing_scores = [s for s in existing_scores if s['structure_id'] != structure_id]

                existing_scores.append({
                    'structure_id': structure_id,
                    'score': match_result['score'],
                    'shift': match_result['shift'],
                    'correlations': match_result['correlations'],
                    'comparison_range': match_result['comparison_range'],
                    'spectrum': predicted_spectrum.tolist(),
                    'energy': energy,
                    'element': element,
                    'selected': was_selected,
                    'st_data': st_dict,
                })

                if match_result['comparison_range'] is not None:
                    comparison_range = match_result['comparison_range']

                last_st_dict = st_dict
                last_filename = filename
                last_structure_id = structure_id
                successful += 1

            except Exception as e:
                print(f"Error processing {filename}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
                failed_files.append(filename)

        existing_scores = mark_active_structure_selected(existing_scores, last_structure_id)
        existing_scores = sort_scores_by_metric(existing_scores, sort_metric)
        
        if successful > 0 and failed == 0:
            status_msg = html.Span(f"✓ Processed {successful} structure(s) successfully", style={'color': 'green'})
        elif successful > 0 and failed > 0:
            status_msg = html.Span([
                html.Span(f"✓ Processed {successful} structure(s). ", style={'color': 'green'}),
                html.Span(f"✗ Failed: {failed} ({', '.join(failed_files[:3])}{'...' if len(failed_files) > 3 else ''})", style={'color': 'orange'})
            ])
        else:
            status_msg = html.Span(f"✗ Failed to process all {failed} file(s)", style={'color': 'red'})

        if successful > 0:
            source_text = f"Current structure: {pathlib.Path(last_filename).stem}"
        else:
            source_text = "No structures loaded"

        return (
            existing_scores,
            build_scores_table(existing_scores, sort_metric),
            comparison_range,
            status_msg,
            None,
            last_st_dict if last_st_dict else dash.no_update,
            source_text
        )

    @app.callback(
        Output(struct_component.id(), 'data', allow_duplicate=True),
        Input('absorber', 'value'),
        State(struct_component.id(), "data")
    )
    def update_structure_by_absorber(el_type, st_data):
        if st_data is None:
            raise PreventUpdate
        st = Structure.from_dict(st_data)
        st_dict = decorate_structure_with_xas(st, el_type)
        return st_dict
