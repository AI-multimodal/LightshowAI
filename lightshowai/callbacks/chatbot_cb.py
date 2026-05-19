import dash
import json
import pathlib
from datetime import datetime
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from mp_api.client import MPRester
from pymatgen.core.structure import Structure
from services.chatbot import (
    _latest_chatbot_structure_file, _read_chatbot_structure_srcdoc,
    _latest_chatbot_scores_file, _extract_mpid_from_chatbot_meta
)
from core.math_utils import decorate_structure_with_xas
from core.matching import sort_scores_by_metric
from components.tables import build_scores_table
from components.viewer import struct_component

def register_callbacks(app):
    @app.callback(
        Output("chatbot_structure_meta_store", "data"),
        Input("chatbot_structure_poll_interval", "n_intervals"),
        State("chatbot_structure_meta_store", "data"),
    )
    def poll_latest_chatbot_structure(_n_intervals, current_meta):
        if current_meta is None:
            return {
                "session_started_at": datetime.now().timestamp(),
                "key": None,
                "srcdoc": "",
                "scores_key": None,
                "scores_file": None,
            }

        session_started_at = current_meta.get("session_started_at")
        if session_started_at is None:
            session_started_at = datetime.now().timestamp()

        struct_key = current_meta.get("key")
        srcdoc = current_meta.get("srcdoc", "")
        file_name = current_meta.get("file")
        updated = current_meta.get("updated")

        latest = _latest_chatbot_structure_file()
        if latest is not None:
            try:
                stat = latest.stat()
                if stat.st_mtime >= float(session_started_at):
                    new_struct_key = f"{latest.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
                    if new_struct_key != struct_key:
                        new_srcdoc = _read_chatbot_structure_srcdoc(latest)
                        if new_srcdoc:
                            struct_key = new_struct_key
                            srcdoc = new_srcdoc
                            file_name = latest.name
                            updated = datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M:%S")
            except OSError:
                pass

        scores_key = current_meta.get("scores_key")
        scores_file = current_meta.get("scores_file")

        latest_scores = _latest_chatbot_scores_file(session_started_at)
        if latest_scores is not None:
            try:
                ss = latest_scores.stat()
                new_scores_key = f"{latest_scores.resolve()}::{ss.st_mtime_ns}"
                if new_scores_key != scores_key:
                    scores_key = new_scores_key
                    scores_file = str(latest_scores.resolve())
            except OSError:
                pass

        composite_key = f"{struct_key}|{scores_key}"
        old_composite_key = f"{current_meta.get('key')}|{current_meta.get('scores_key')}"
        if composite_key == old_composite_key:
            raise PreventUpdate

        return {
            "session_started_at": session_started_at,
            "key": struct_key,
            "file": file_name,
            "updated": updated,
            "srcdoc": srcdoc,
            "scores_key": scores_key,
            "scores_file": scores_file,
        }

    @app.callback(
        Output("chatbot_structure_iframe", "srcDoc"),
        Output("chatbot_structure_iframe", "style"),
        Output("structure_component_wrapper", "style"),
        Output("chatbot_structure_hint", "children"),
        Input("chatbot_structure_meta_store", "data"),
    )
    def render_chatbot_structure_preview(meta):
        hidden_style = {
            "display": "none",
            "width": "100%",
            "height": "680px",
            "border": "1px solid #e5e5e5",
            "borderRadius": "6px",
            "backgroundColor": "#fff",
            "marginTop": "10px",
        }
        visible_style = {
            **hidden_style,
            "display": "block",
        }
        structure_visible = {'minHeight': '200px', 'width': '100%', 'position': 'relative', 'display': 'block'}
        structure_hidden = {'minHeight': '200px', 'width': '100%', 'position': 'relative', 'display': 'none'}

        if not meta or not meta.get("srcdoc"):
            return "", hidden_style, structure_visible, ""

        label = f"Chatbot structure loaded: {meta.get('file', 'structure.html')} (updated {meta.get('updated', '--:--:--')})"
        return "", hidden_style, structure_visible, label

    @app.callback(
        Output(struct_component.id(), "data", allow_duplicate=True),
        Output("st_source", "children", allow_duplicate=True),
        Input("chatbot_structure_meta_store", "data"),
        State("absorber", "value"),
        State("shakeup-store", "data"),
        prevent_initial_call=True,
    )
    def update_structure_from_chatbot_meta(meta, el_type, shakeup_val):
        if not meta or not meta.get("srcdoc"):
            raise PreventUpdate

        mpid = _extract_mpid_from_chatbot_meta(meta)
        if not mpid:
            raise PreventUpdate

        try:
            with MPRester() as mpr:
                docs = mpr.materials.search(
                    material_ids=[mpid],
                    fields=["material_id", "structure"],
                )
        except Exception as exc:
            print(f"Chatbot structure load failed for {mpid}: {exc}")
            raise PreventUpdate

        if not docs:
            raise PreventUpdate

        doc = docs[0]
        st = getattr(doc, "structure", None)
        if st is None or not isinstance(st, Structure):
            raise PreventUpdate

        st_dict = decorate_structure_with_xas(st, el_type)
        st_dict["label"] = mpid
        st_dict["material_id"] = mpid
        st_dict["structure_id"] = mpid

        return st_dict, f"Current structure: {mpid}"

    @app.callback(
        Output("structure_scores_store", "data", allow_duplicate=True),
        Output("matching_results_table", "children", allow_duplicate=True),
        Output("comparison_range_store", "data", allow_duplicate=True),
        Input("chatbot_structure_meta_store", "data"),
        State("sort_metric_store", "data"),
        prevent_initial_call=True,
    )
    def update_scores_from_chatbot_meta(meta, sort_metric):
        if not meta or not meta.get("scores_file") or not meta.get("scores_key"):
            raise PreventUpdate

        scores_path = pathlib.Path(meta["scores_file"])
        if not scores_path.is_file():
            raise PreventUpdate

        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[chatbot scores] failed to read {scores_path}: {exc}")
            raise PreventUpdate

        if not isinstance(scores, list) or not scores:
            raise PreventUpdate

        if sort_metric is None:
            sort_metric = "coss_deriv"

        for entry in scores:
            entry.setdefault("selected", True)

        scores = sort_scores_by_metric(scores, sort_metric)
        comparison_range = None
        for entry in scores:
            cr = entry.get("comparison_range")
            if cr:
                comparison_range = cr
                break

        print(f"[chatbot scores] loaded {len(scores)} structures from {scores_path.name}")
        return scores, build_scores_table(scores, sort_metric), comparison_range
