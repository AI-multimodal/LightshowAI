---
description: Predict and benchmark Ti K-edge XANES spectra using LightshowAI and Materials Project, with Pearson/Spearman/Cos(∂) similarity metrics and energy-shift optimization against experimental standards
user-invocable: true
---

# XANES Analysis Skill

Run an end-to-end Ti K-edge XANES benchmarking workflow:
1. Retrieve candidate structures from the Materials Project
2. Predict spectra with LightshowAI (VASP or FEFF model)
3. Compare to experimental `.dat` standards using shift-optimized Pearson r, Spearman ρ, Cos(∂), Cosine, and Kendall τ
4. Rank structures per experimental standard and generate an interactive comparison figure

## Arguments

The user may specify any of:
- **Formula / chemical system** — e.g. `TiO2`, `Fe2O3`, `VO2` (default: `TiO2`)
- **Absorbing element** — e.g. `Ti`, `Fe`, `V` (default: inferred from formula)
- **Model** — `VASP` or `FEFF` (default: `VASP` if available for the element, else `FEFF`)
- **Hull threshold** — max eV/atom above convex hull (default: `0.05`)
- **Experimental data directory** — folder containing `*.dat` files (default: current working directory or `experiments/`)
- **Output directory** — where to save HTML figure and PNG (default: the `Current question output directory` injected by the Chainlit app, otherwise `~/tmp/xanes_analysis`)
- **Max structures** — max number of Materials Project results to include (default: `5`; do not exceed `10` unless the user explicitly asks)

## Step 0: Check available models

Call `list_available_models` to confirm which (element, model) combinations are supported before proceeding. If the requested element/model is not available, inform the user and suggest the closest alternative.

## Step 1: Retrieve structures

Use `mp_search_materials` with:
- `formula` = user formula
- `is_stable` = True for the first pass
- `energy_above_hull_max` = hull threshold
- `fields` = `"material_id,formula_pretty,energy_above_hull,symmetry,band_gap,is_stable"`
- `sort_fields` = `"energy_above_hull"`
- `limit` = max structures

If the initial search with `is_stable=True` returns fewer than 3 results, expand to `energy_above_hull_max=0.05` automatically.

Present retrieved structures in a table:
```
| MP ID | Phase / Space Group | Hull (eV/atom) |
```

## Step 2: Predict spectra

For each structure, call `plot_xanes`:
- `material_id` = MP ID
- `absorbing_element` = absorbing element
- `spectroscopy_type` = VASP or FEFF
- `open_browser` = False
- `output_path` = `<output_dir>/<mpid>_<formula>_<element>_<model>.html`

Use the `Current question output directory` from the message when present. If it
is not present and the user does not name an output directory, use
`~/tmp/xanes_analysis` so the Chainlit UI can discover and render generated HTML
files.

Report success/failure per structure. Skip silently failed structures with a warning.

## Step 3: Load experimental standards

If the user uploaded `.dat` files, the Chainlit app adds their stable local paths
to the message. Use those exact paths or their parent directories immediately.
Do not ask the user for a path when uploaded `.dat` paths are listed.

Scan the experimental data directory for `*.dat` files. Each file is one experimental standard named by the phase (e.g. `anatase.dat`, `rutile.dat`). Load each:
- Two columns: energy (eV) and intensity
- Skip header/comment lines (non-numeric)
- Report energy range and number of points for each standard

If no uploaded `.dat` paths are listed and no `.dat` files are found in the
requested/default directory, ask the user to upload files or provide a directory.

## Step 4: Extract predicted spectra from HTML

For each LightshowAI HTML output, extract the mean/VASP spectrum using Plotly JSON parsing:

```python
import json, re, numpy as np

def extract_spectrum_from_html(html_path):
    text = open(html_path).read()
    matches = list(re.finditer(r'Plotly\.newPlot\(\s*["\']([^"\']*)["\'],\s*(\[)', text))
    m = matches[-1]
    start = m.start(2)
    depth, i = 0, start
    while i < len(text):
        if text[i] == '[': depth += 1
        elif text[i] == ']':
            depth -= 1
            if depth == 0: break
        i += 1
    traces = json.loads(text[start:i+1])
    for trace in reversed(traces):
        if trace.get("name","").startswith("Mean") or trace.get("name","") == "VASP":
            return np.array(trace["x"]), np.array(trace["y"])
    t = traces[-1]
    return np.array(t["x"]), np.array(t["y"])
```

## Step 5: Compute similarity metrics with energy-shift optimization

For each (structure, experimental standard) pair:

1. **Optimize energy shift**: Try shifts from −2.0 to +2.0 eV in 0.1 eV steps. At each shift, apply to ML prediction, find the common valid energy range (no zero-padding), max-normalize both spectra, compute Pearson r. Select the shift `δ*` that maximizes Pearson.

2. **Compute all metrics** at `δ*`:
   - **Pearson r** — linear shape correlation
   - **Spearman ρ** — rank-order correlation (robust to monotonic distortions)
   - **Kendall τ** — concordance of rank pairs
   - **Cosine similarity** — dot product of normalized vectors
   - **Cos(∂)** — cosine similarity of first derivative (sensitive to peak positions and slopes)

```python
from scipy.stats import pearsonr, spearmanr, kendalltau

def compare(ex, ey, ee, ei, shift, n_grid=400):
    ex_s = ex + shift
    e_lo = max(ex_s.min(), ee.min())
    e_hi = min(ex_s.max(), ee.max())
    if e_hi - e_lo < 5.0:
        return None
    grid = np.linspace(e_lo, e_hi, n_grid)
    from scipy.interpolate import interp1d
    yp = interp1d(ex_s, ey, bounds_error=False, fill_value=0)(grid)
    ye = interp1d(ee,   ei, bounds_error=False, fill_value=0)(grid)
    if yp.max() == 0 or ye.max() == 0: return None
    yp /= yp.max(); ye /= ye.max()
    return grid, yp, ye
```

## Step 6: Print results per experimental standard

For each experimental standard, print a ranked table sorted by:
- **Pearson r** if the standard name contains the formula of the #1 predicted structure (heuristic for "obvious" cases)
- **Spearman ρ** otherwise (more robust for ambiguous cases)

```
--- Experimental: <name> (sorted by <metric>) ---
  #  MP-ID       Shift   Cos(∂)   Pearson   Spearman   Cosine   Kendall
  1  mp-XXXX     -0.4    0.817    0.971      0.927     0.965    0.786  <-- best
  ...
```

Highlight the top-ranked structure per standard.

## Step 7: Generate comparison figure

Create an interactive Plotly figure with one panel per experimental standard:
- Each panel shows the experimental curve (dashed/dotted) and all predicted curves (solid)
- The best-matching structure uses a thicker line (width=2.5, opacity=1.0)
- All curves plotted at the optimal shift
- Save as `comparison_per_standard.html`.
- Take a Playwright screenshot as `figure_per_standard.png` only if Playwright is installed and launches quickly. If browser setup fails or takes longer than 15 seconds, skip the PNG and report that the interactive HTML was generated.

```python
# playwright screenshot
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 600})
    page.goto(f"file://{html_path.resolve()}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(png_path), full_page=False)
    browser.close()
```

## Step 8: Summary

Print a summary table:
```
| Standard | Best (Pearson) | Best (Spearman) | Identified phase |
```

Note any near-ties (structures within 0.01 Spearman of #1) — these indicate genuine spectral ambiguity requiring additional metrics or human expert review.

## Key Scientific Notes

- **Energy shifts of −0.3 to −0.8 eV are normal** for LightshowAI VASP predictions vs. experiment; do not flag as errors
- **Spearman ρ is generally more reliable than Pearson** for distinguishing polymorphs with similar edge shapes (e.g. Rutile vs TiO₂-II)
- **Cos(∂) is most sensitive to pre-edge fine structure** and can break ties when Pearson and Spearman disagree
- **Near-degenerate structures** (within 0.01 Spearman) should be flagged explicitly — the ranking can flip with small changes in shift or normalization
- **No single metric dominates across all edges** — always report all five and let the user decide which to trust for their specific system

## Validated Results (Ti K-edge, TiO₂)

For reference: correct phase assignments confirmed by Deyu (spectroscopist) using the same methodology:

| Standard | Correct MP ID | Best metric | Shift used |
|----------|--------------|-------------|------------|
| Anatase  | mp-390       | Pearson r   | −0.3 to −0.4 eV |
| Brookite | mp-1840      | Spearman ρ  | −0.7 eV (sensitive) |
| Rutile   | mp-2657      | Spearman ρ  | −0.1 to −0.4 eV |

## Output Files

After running, report the paths to:
- `<output_dir>/<mpid>_<formula>_<element>_<model>.html` — one per predicted structure
- `<output_dir>/comparison_per_standard.html` — interactive comparison figure
- `<output_dir>/figure_per_standard.png` — static PNG screenshot
- `<output_dir>/compare_xanes.py` — the analysis script (save for reproducibility)
