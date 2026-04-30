"""MCP server exposing Materials Project data tools via FastMCP."""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from materials_project_client import MaterialsProjectClient

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    """Load .env values into the process environment."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        existing = os.environ.get(key, "")
        if key and (not existing or existing.startswith("${")):
            os.environ[key] = value


def _update_env(key: str, value: str) -> None:
    """Update or append a key=value pair in .env."""
    lines: list[str] = []
    found = False
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            if line.lstrip().startswith(f"export {key}=") or line.startswith(f"{key}="):
                prefix = "export " if line.lstrip().startswith("export ") else ""
                lines.append(f"{prefix}{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


def _fmt(data: object) -> str:
    """Format output for MCP clients."""
    return json.dumps(data, indent=2, default=str)


def _csv_to_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _range(min_value: float | int | None, max_value: float | int | None):
    if min_value is None and max_value is None:
        return None
    return (min_value, max_value)


_load_env()

mcp = FastMCP("materials-project")
client = MaterialsProjectClient()


@mcp.tool()
async def authenticate_materials_project(api_key: str) -> str:
    """Store a Materials Project API key for authenticated API calls.

    Args:
        api_key: API key from the Materials Project dashboard.
    """
    client.set_api_key(api_key)
    _update_env("MP_API_KEY", api_key)
    try:
        sample = await asyncio.to_thread(client.verify_api_key)
        material_id = sample.get("material_id", "unknown")
        formula = sample.get("formula_pretty", "unknown")
        return (
            f"Authenticated successfully. API key saved to {_ENV_FILE}. "
            f"Verified with {material_id} ({formula})."
        )
    except Exception as exc:
        return f"API key stored and saved to {_ENV_FILE}, but verification failed: {exc}"


@mcp.tool()
async def mp_get_summary(material_id: str, fields: str = "") -> str:
    """Get summary data for a single Materials Project material ID.

    Args:
        material_id: MP material ID, e.g. "mp-149".
        fields: Optional comma-separated fields to project.
    """
    try:
        result = await asyncio.to_thread(
            client.get_material_summary,
            material_id,
            _csv_to_list(fields) if fields else None,
        )
        if not result:
            return f"No summary document found for '{material_id}'."
        return _fmt(result)
    except Exception as exc:
        return f"Error fetching summary data for '{material_id}': {exc}"


@mcp.tool()
async def mp_search_materials(
    material_ids: str = "",
    formula: str = "",
    chemsys: str = "",
    elements: str = "",
    exclude_elements: str = "",
    band_gap_min: float | None = None,
    band_gap_max: float | None = None,
    energy_above_hull_min: float | None = None,
    energy_above_hull_max: float | None = None,
    is_stable: bool | None = None,
    is_metal: bool | None = None,
    num_elements_min: int | None = None,
    num_elements_max: int | None = None,
    num_sites_min: int | None = None,
    num_sites_max: int | None = None,
    spacegroup_symbol: str = "",
    fields: str = "material_id,formula_pretty,nsites,band_gap,energy_above_hull,is_stable,symmetry",
    limit: int = 10,
    sort_fields: str = "",
) -> str:
    """Search Materials Project summary data with common screening filters.

    Args:
        material_ids: Optional comma-separated material IDs.
        formula: Optional formula or comma-separated formulas, e.g. "Fe2O3" or "SiO2,TiO2".
        chemsys: Optional chemical system, e.g. "Li-Fe-O".
        elements: Optional comma-separated elements that must be present.
        exclude_elements: Optional comma-separated elements to exclude.
        band_gap_min: Minimum band gap in eV.
        band_gap_max: Maximum band gap in eV.
        energy_above_hull_min: Minimum energy above hull in eV/atom.
        energy_above_hull_max: Maximum energy above hull in eV/atom.
        is_stable: Filter for stable materials.
        is_metal: Filter for metals/non-metals.
        num_elements_min: Minimum number of elements.
        num_elements_max: Maximum number of elements.
        num_sites_min: Minimum number of sites.
        num_sites_max: Maximum number of sites.
        spacegroup_symbol: Optional space group symbol.
        fields: Comma-separated summary fields to return.
        limit: Maximum number of matching documents to return.
        sort_fields: Optional sort field, e.g. "-band_gap".
    """
    try:
        result = await asyncio.to_thread(
            client.search_materials,
            material_ids=_csv_to_list(material_ids) or None,
            formula=_csv_to_list(formula) or None,
            chemsys=_csv_to_list(chemsys) or None,
            elements=_csv_to_list(elements) or None,
            exclude_elements=_csv_to_list(exclude_elements) or None,
            band_gap=_range(band_gap_min, band_gap_max),
            energy_above_hull=_range(energy_above_hull_min, energy_above_hull_max),
            is_stable=is_stable,
            is_metal=is_metal,
            num_elements=_range(num_elements_min, num_elements_max),
            num_sites=_range(num_sites_min, num_sites_max),
            spacegroup_symbol=_csv_to_list(spacegroup_symbol) or None,
            fields=_csv_to_list(fields) if fields else None,
            limit=limit,
            sort_fields=sort_fields or None,
        )
        docs = result.get("data", [])
        if not docs:
            return "No matching materials found."
        return _fmt(result)
    except Exception as exc:
        return f"Error searching materials: {exc}"


@mcp.tool()
async def mp_get_structure(material_id: str, final: bool = True) -> str:
    """Get a material structure by MP material ID.

    Args:
        material_id: MP material ID, e.g. "mp-149".
        final: If True, return the final relaxed structure. If False, return initial structures.
    """
    try:
        structure = await asyncio.to_thread(client.get_structure, material_id, final)
        if not structure:
            return f"No structure found for '{material_id}'."
        return _fmt(structure)
    except Exception as exc:
        return f"Error fetching structure for '{material_id}': {exc}"


@mcp.tool()
async def mp_get_endpoint_data(
    endpoint: str,
    material_id: str,
    fields: str = "",
    limit: int = 10,
) -> str:
    """Get material data from a specific Materials Project endpoint.

    Args:
        endpoint: Endpoint under /materials, e.g. "dielectric", "elasticity",
            "thermo", "oxidation_states", or "electronic_structure/bandstructure".
        material_id: MP material ID, e.g. "mp-149".
        fields: Optional comma-separated fields to project.
        limit: Maximum number of matching documents to return.
    """
    try:
        result = await asyncio.to_thread(
            client.get_endpoint_data,
            endpoint,
            material_id,
            _csv_to_list(fields) if fields else None,
            limit,
        )
        docs = result.get("data", [])
        if not docs:
            return f"No '{endpoint}' data found for '{material_id}'."
        return _fmt(result)
    except Exception as exc:
        return f"Error fetching endpoint data from '{endpoint}' for '{material_id}': {exc}"


def _build_structure_figure(struct, supercell: list[int]) -> "go.Figure":
    """Build a plotly 3D figure for a pymatgen Structure."""
    import numpy as np
    import plotly.graph_objects as go
    from pymatgen.analysis.local_env import CrystalNN

    if supercell != [1, 1, 1]:
        struct = struct.make_supercell(supercell)

    lattice = struct.lattice.matrix
    species = [str(s.species_string) for s in struct]
    frac_coords = np.array([s.frac_coords for s in struct])
    cart_coords = struct.lattice.get_cartesian_coords(frac_coords)

    # Unit cell box
    corners = np.array(
        [[i, j, k] for i in [0, 1] for j in [0, 1] for k in [0, 1]], dtype=float
    )
    corner_cart = corners @ lattice
    edges = [(0,1),(0,2),(0,4),(1,3),(1,5),(2,3),(2,6),(3,7),(4,5),(4,6),(5,7),(6,7)]

    traces: list = []
    for a, b in edges:
        traces.append(go.Scatter3d(
            x=[corner_cart[a, 0], corner_cart[b, 0]],
            y=[corner_cart[a, 1], corner_cart[b, 1]],
            z=[corner_cart[a, 2], corner_cart[b, 2]],
            mode="lines",
            line=dict(color="#555", width=2),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Bonds via CrystalNN
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cnn = CrystalNN()
        drawn: set = set()
        bx, by, bz = [], [], []
        for i, site in enumerate(struct):
            if species[i] not in ("V", "Ti", "Fe", "Mn", "Cu", "Ni", "Co", "Cr"):
                # generic: draw bonds for all species
                pass
            for nb in cnn.get_nn_info(struct, i):
                j = nb["site_index"]
                key = (min(i, j), max(i, j))
                if key in drawn:
                    continue
                drawn.add(key)
                p1, p2 = cart_coords[i], cart_coords[j]
                bx += [p1[0], p2[0], None]
                by += [p1[1], p2[1], None]
                bz += [p1[2], p2[2], None]

    traces.append(go.Scatter3d(
        x=bx, y=by, z=bz,
        mode="lines",
        line=dict(color="#aaaaaa", width=3),
        name="Bonds",
        hoverinfo="skip",
    ))

    # Color palette for up to 10 species
    palette = [
        "#4C72B0", "#DD4444", "#55A868", "#C44E52", "#8172B2",
        "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
    ]
    unique_sp = list(dict.fromkeys(species))
    color_map = {sp: palette[i % len(palette)] for i, sp in enumerate(unique_sp)}
    size_map = {sp: max(6, 14 - i * 2) for i, sp in enumerate(unique_sp)}

    for sp in unique_sp:
        mask = np.array([s == sp for s in species])
        pts = cart_coords[mask]
        fc = frac_coords[mask]
        traces.append(go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2],
            mode="markers",
            marker=dict(
                size=size_map[sp],
                color=color_map[sp],
                line=dict(color="black", width=0.5),
            ),
            name=sp,
            text=[
                f"{sp}<br>frac: ({fc[k,0]:.3f}, {fc[k,1]:.3f}, {fc[k,2]:.3f})"
                for k in range(len(pts))
            ],
            hovertemplate="%{text}<extra></extra>",
        ))

    lat = struct.lattice
    sc_str = "×".join(str(s) for s in supercell)
    title = (
        f"{struct.composition.reduced_formula} | {sc_str} supercell<br>"
        f"a={lat.a:.3f} Å  b={lat.b:.3f} Å  c={lat.c:.3f} Å  "
        f"α={lat.alpha:.2f}°  β={lat.beta:.2f}°  γ={lat.gamma:.2f}°"
    )

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=13)),
        scene=dict(
            xaxis_title="x (Å)",
            yaxis_title="y (Å)",
            zaxis_title="z (Å)",
            aspectmode="data",
            bgcolor="#f4f4f4",
        ),
        legend=dict(x=0.02, y=0.95, font=dict(size=12)),
        margin=dict(l=0, r=0, t=90, b=0),
        paper_bgcolor="white",
    )
    return fig


def _visualize_structure_sync(
    material_id: str,
    supercell: list[int],
    output_path: str,
    api_key: str,
) -> str:
    try:
        from mp_api.client import MPRester
    except ImportError:
        return "mp-api is not installed. Run: pip install mp-api pymatgen plotly"

    try:
        with MPRester(api_key) as mpr:
            struct = mpr.get_structure_by_material_id(material_id)
    except Exception as exc:
        return f"Failed to fetch structure for '{material_id}': {exc}"

    try:
        fig = _build_structure_figure(struct, supercell)
    except Exception as exc:
        return f"Failed to build figure: {exc}"

    out = Path(os.path.expanduser(output_path)).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn")
    return str(out)


@mcp.tool()
async def mp_visualize_structure(
    material_id: str,
    supercell_a: int = 1,
    supercell_b: int = 1,
    supercell_c: int = 1,
    output_path: str = "",
) -> str:
    """Generate an interactive 3D HTML viewer for a Materials Project crystal structure.

    Creates a Plotly-based interactive viewer showing atoms, bonds, and the unit
    cell box. The viewer supports rotate, zoom, and pan; hovering an atom shows its
    species and fractional coordinates.

    Args:
        material_id: MP material ID, e.g. "mp-559445".
        supercell_a: Supercell repeat along a (default 1).
        supercell_b: Supercell repeat along b (default 1).
        supercell_c: Supercell repeat along c (default 1).
        output_path: Local path for the HTML file. Defaults to
            ~/Downloads/<material_id>_structure.html.
    """
    api_key = client.api_key
    if not api_key:
        return "No API key set. Call authenticate_materials_project() first."

    supercell = [max(1, supercell_a), max(1, supercell_b), max(1, supercell_c)]

    if not output_path:
        output_path = str(
            Path.home() / "Downloads" / f"{material_id}_{'x'.join(str(s) for s in supercell)}_structure.html"
        )

    result = await asyncio.to_thread(
        _visualize_structure_sync, material_id, supercell, output_path, api_key
    )

    if result.endswith(".html"):
        sc_str = "×".join(str(s) for s in supercell)
        return f"Interactive structure viewer saved to: {result}\nSupercell: {sc_str}. Open the HTML file in a browser to explore."
    return result


if __name__ == "__main__":
    mcp.run()
