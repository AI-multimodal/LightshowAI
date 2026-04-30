"""MCP server exposing LightshowAI XANES prediction tools."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from mcp.server.fastmcp import FastMCP

# --- paths -------------------------------------------------------------------
# This file may live in either of two layouts:
#   (a) <repo>/mcp/lightshowai_server.py         (broader agentic_workflows repo)
#   (b) <repo>/examples/LightshowAI/mcp/...      (self-contained LightshowAI example)
# Detect (b) first by checking for a sibling `lightshowai` package directory.
_HERE = Path(__file__).resolve().parent
_VENDORED_LIGHTSHOWAI_DIR = _HERE.parent  # examples/LightshowAI/ in layout (b)
if (_VENDORED_LIGHTSHOWAI_DIR / "lightshowai").is_dir():
    _LIGHTSHOWAI_DIR = _VENDORED_LIGHTSHOWAI_DIR
    _REPO_DIR = _LIGHTSHOWAI_DIR
else:
    _REPO_DIR = _HERE.parent
    _LIGHTSHOWAI_DIR = _REPO_DIR / "examples" / "LightshowAI"

_ENV_FILE = _REPO_DIR / ".env"

# Add LightshowAI package to path
sys.path.insert(0, str(_LIGHTSHOWAI_DIR))

# --- env / API key -----------------------------------------------------------
def _load_env() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value

_load_env()

# --- energy grid (per-element K-edge, 141 pts over 35 eV) -------------------
_ENE_START = {
    "Ti": 4964.504, "V": 5464.097, "Cr": 5989.168, "Mn": 6537.886,
    "Fe": 7111.23,  "Co": 7709.282, "Ni": 8332.181, "Cu": 8983.173,
}
_ENE_GRID = {el: np.linspace(s, s + 35, 141) for el, s in _ENE_START.items()}

# --- lazy model cache --------------------------------------------------------
_model_cache: dict[str, object] = {}

def _get_model(element: str, spectroscopy_type: str):
    from lightshowai.models import XASBlockModule
    key = f"{element}_{spectroscopy_type}"
    if key not in _model_cache:
        _model_cache[key] = XASBlockModule.load(element=element, spectroscopy_type=spectroscopy_type)
    return _model_cache[key]

def _object_value(obj: object, key: str):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _plain_value(value: object):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _fetch_material_doc_and_structure(material_id: str):
    from mp_api.client import MPRester
    api_key = os.environ.get("MP_API_KEY")
    with MPRester(api_key) as mpr:
        doc = None
        try:
            doc = mpr.summary.get_data_by_id(material_id)
        except Exception:
            pass
        structure = _object_value(doc, "structure") if doc is not None else None
        if structure is None:
            structure = mpr.get_structure_by_material_id(material_id)
        return doc, structure


def _material_metadata(doc: object, structure: object) -> dict:
    symmetry = _object_value(doc, "symmetry")
    meta = {
        "formula": _object_value(doc, "formula_pretty") or structure.formula,
        "energy_above_hull_eV_per_atom": _object_value(doc, "energy_above_hull"),
        "band_gap_eV": _object_value(doc, "band_gap"),
        "is_stable": _object_value(doc, "is_stable"),
    }
    if symmetry is not None:
        meta.update(
            {
                "crystal_system": _object_value(symmetry, "crystal_system"),
                "space_group": _object_value(symmetry, "symbol"),
                "space_group_number": _object_value(symmetry, "number"),
            }
        )
    return {key: _plain_value(value) for key, value in meta.items() if value is not None}


def _energy_metadata(energy: list[float]) -> dict:
    if not energy:
        return {}
    return {
        "energy_start_eV": round(float(energy[0]), 3),
        "energy_end_eV": round(float(energy[-1]), 3),
        "energy_n_points": len(energy),
        "energy_step_eV": round(
            (float(energy[-1]) - float(energy[0])) / max(len(energy) - 1, 1),
            3,
        ),
    }


def _write_spectrum_csv(data: dict, output_path: str) -> str:
    csv_path = str(Path(output_path).with_suffix(".csv"))
    energy = data["energy_eV"]
    site_spectra = data.get("site_spectra", {})
    site_keys = sorted(site_spectra)
    with Path(csv_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["energy_eV", *[f"site_{key}" for key in site_keys], "mean"])
        for idx, energy_value in enumerate(energy):
            row = [energy_value]
            for key in site_keys:
                values = site_spectra.get(key, [])
                row.append(values[idx] if idx < len(values) else "")
            row.append(data["mean_spectrum"][idx])
            writer.writerow(row)
    return csv_path


def _write_comparison_csv(
    energy: list[float],
    spectra: list[tuple[str, list[float]]],
    output_path: str,
) -> str:
    csv_path = str(Path(output_path).with_suffix(".csv"))
    with Path(csv_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["energy_eV", *[f"mean_{material_id}" for material_id, _ in spectra]]
        )
        for idx, energy_value in enumerate(energy):
            writer.writerow(
                [
                    energy_value,
                    *[values[idx] if idx < len(values) else "" for _, values in spectra],
                ]
            )
    return csv_path


def _predict(material_id: str, absorbing_element: str, spectroscopy_type: str) -> dict:
    from lightshowai.models import predict
    doc, structure = _fetch_material_doc_and_structure(material_id)
    spectra = predict(structure, absorbing_element, spectroscopy_type)
    energy = _ENE_GRID[absorbing_element].tolist()
    return {
        "material_id": material_id,
        "absorbing_element": absorbing_element,
        "spectroscopy_type": spectroscopy_type,
        **_material_metadata(doc, structure),
        **_energy_metadata(energy),
        "energy_eV": energy,
        "site_spectra": {str(k): v.tolist() for k, v in spectra.items()},
        "mean_spectrum": np.mean(list(spectra.values()), axis=0).tolist(),
        "n_sites": len(spectra),
    }

# --- MCP server --------------------------------------------------------------
mcp = FastMCP("lightshowai")

XASBLOCKS_PATH = _LIGHTSHOWAI_DIR / "model_checkpoints" / "xasblock" / "v1.1.1"


@mcp.tool()
def list_available_models() -> str:
    """List all available element / spectroscopy-type combinations."""
    combos = sorted(f.stem for f in XASBLOCKS_PATH.glob("*.ckpt"))
    elements = sorted(_ENE_START.keys())
    return json.dumps({
        "available_models": combos,
        "supported_elements": elements,
        "spectroscopy_types": ["FEFF", "VASP"],
        "note": "VASP models available for Ti and Cu only; FEFF for all 8 elements.",
    }, indent=2)


@mcp.tool()
def predict_xanes(
    material_id: str,
    absorbing_element: str,
    spectroscopy_type: str = "FEFF",
) -> str:
    """Predict XANES spectrum for a Materials Project structure.

    Args:
        material_id: MP material ID, e.g. 'mp-149'.
        absorbing_element: Element symbol for the absorbing site (Ti, V, Cr, Mn, Fe, Co, Ni, Cu).
        spectroscopy_type: 'FEFF' (default, all elements) or 'VASP' (Ti and Cu only).
    """
    try:
        result = _predict(material_id, absorbing_element, spectroscopy_type)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def plot_xanes(
    material_id: str,
    absorbing_element: str,
    spectroscopy_type: str = "FEFF",
    output_path: str = "",
    open_browser: bool = True,
) -> str:
    """Predict XANES and save an interactive HTML plot.

    Args:
        material_id: MP material ID, e.g. 'mp-149'.
        absorbing_element: Absorbing element symbol.
        spectroscopy_type: 'FEFF' or 'VASP'.
        output_path: Where to save the HTML file. Defaults to ~/tmp/<material_id>_xanes.html.
        open_browser: Automatically open the plot in the default browser.
    """
    import plotly.graph_objects as go

    try:
        data = _predict(material_id, absorbing_element, spectroscopy_type)
    except Exception as e:
        return json.dumps({"error": str(e)})

    energy = data["energy_eV"]
    fig = go.Figure()

    # per-site spectra (lighter traces)
    for site_idx, spectrum in data["site_spectra"].items():
        fig.add_trace(go.Scatter(
            x=energy, y=spectrum,
            mode="lines",
            name=f"Site {site_idx}",
            line=dict(width=1),
            opacity=0.5,
        ))

    # mean spectrum (bold)
    fig.add_trace(go.Scatter(
        x=energy, y=data["mean_spectrum"],
        mode="lines",
        name="Mean",
        line=dict(width=2.5, color="black"),
    ))

    title = (f"{data['formula']} ({material_id}) — "
             f"{absorbing_element} K-edge XANES ({spectroscopy_type})")
    fig.update_layout(
        title=title,
        xaxis_title="Energy (eV)",
        yaxis_title="Intensity (arb. units)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    if not output_path:
        out_dir = Path.home() / "tmp"
        out_dir.mkdir(exist_ok=True)
        output_path = str(out_dir / f"{material_id}_{absorbing_element}_{spectroscopy_type}_xanes.html")
    else:
        # Expand ~ and resolve so callers can pass "~/tmp/foo.html" directly.
        output_path = str(Path(os.path.expanduser(output_path)).resolve())
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fig.write_html(output_path)
    spectrum_csv = _write_spectrum_csv(data, output_path)

    if open_browser:
        subprocess.Popen(["open", output_path])

    return json.dumps({
        "saved_to": output_path,
        "spectrum_csv": spectrum_csv,
        "material_id": material_id,
        "formula": data["formula"],
        "absorbing_element": absorbing_element,
        "spectroscopy_type": spectroscopy_type,
        "n_sites": data["n_sites"],
        "crystal_system": data.get("crystal_system"),
        "space_group": data.get("space_group"),
        "space_group_number": data.get("space_group_number"),
        "energy_above_hull_eV_per_atom": data.get("energy_above_hull_eV_per_atom"),
        "band_gap_eV": data.get("band_gap_eV"),
        "is_stable": data.get("is_stable"),
        "energy_start_eV": data.get("energy_start_eV"),
        "energy_end_eV": data.get("energy_end_eV"),
        "energy_n_points": data.get("energy_n_points"),
        "energy_step_eV": data.get("energy_step_eV"),
    }, indent=2)


@mcp.tool()
def compare_xanes(
    material_ids: str,
    absorbing_element: str,
    spectroscopy_type: str = "FEFF",
    output_path: str = "",
    open_browser: bool = True,
) -> str:
    """Compare mean XANES spectra for multiple materials on one plot.

    Args:
        material_ids: Comma-separated MP material IDs, e.g. 'mp-149,mp-22862'.
        absorbing_element: Absorbing element symbol (must be present in all structures).
        spectroscopy_type: 'FEFF' or 'VASP'.
        output_path: Where to save the HTML file.
        open_browser: Automatically open the plot in the default browser.
    """
    import plotly.graph_objects as go

    ids = [m.strip() for m in material_ids.split(",") if m.strip()]
    if len(ids) < 2:
        return json.dumps({"error": "Provide at least 2 comma-separated material IDs."})

    fig = go.Figure()
    results = []
    mean_spectra: list[tuple[str, list[float]]] = []

    for mid in ids:
        try:
            data = _predict(mid, absorbing_element, spectroscopy_type)
            fig.add_trace(go.Scatter(
                x=data["energy_eV"],
                y=data["mean_spectrum"],
                mode="lines",
                name=f"{data['formula']} ({mid})",
                line=dict(width=2),
            ))
            mean_spectra.append((mid, data["mean_spectrum"]))
            results.append({
                "material_id": mid,
                "formula": data["formula"],
                "n_sites": data["n_sites"],
                "crystal_system": data.get("crystal_system"),
                "space_group": data.get("space_group"),
                "space_group_number": data.get("space_group_number"),
                "energy_above_hull_eV_per_atom": data.get("energy_above_hull_eV_per_atom"),
                "band_gap_eV": data.get("band_gap_eV"),
                "is_stable": data.get("is_stable"),
            })
        except Exception as e:
            results.append({"material_id": mid, "error": str(e)})

    fig.update_layout(
        title=f"{absorbing_element} K-edge XANES comparison ({spectroscopy_type})",
        xaxis_title="Energy (eV)",
        yaxis_title="Intensity (arb. units)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    if not output_path:
        out_dir = Path.home() / "tmp"
        out_dir.mkdir(exist_ok=True)
        label = "_".join(ids)[:60]
        output_path = str(out_dir / f"compare_{absorbing_element}_{label}_xanes.html")
    else:
        output_path = str(Path(os.path.expanduser(output_path)).resolve())
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fig.write_html(output_path)
    spectrum_csv = ""
    if mean_spectra:
        spectrum_csv = _write_comparison_csv(
            _ENE_GRID[absorbing_element].tolist(),
            mean_spectra,
            output_path,
        )

    if open_browser:
        subprocess.Popen(["open", output_path])

    return json.dumps({
        "saved_to": output_path,
        "spectrum_csv": spectrum_csv,
        "absorbing_element": absorbing_element,
        "spectroscopy_type": spectroscopy_type,
        **_energy_metadata(_ENE_GRID[absorbing_element].tolist()),
        "results": results,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
