import numpy as np
from lightshowai.postprocess import compare_utils
from .math_utils import ene_grid

# All available metrics for display
ALL_METRICS = ["pearson", "spearman", "kendalltaub", "coss_deriv", "coss", "normed_wasserstein"]

# Short display names for table headers
METRIC_SHORT_NAMES = {
    "coss_deriv": "Cos(∂)",
    "pearson": "Pearson",
    "spearman": "Spearman",
    "coss": "Cosine",
    "kendalltaub": "Kendall",
    "normed_wasserstein": "Wasser.",
}

def get_spectrum_match_score(predicted_spectrum, exp_spectrum, element):
    """
    Compare predicted spectrum against experimental spectrum using
    lightshow.postprocess.compare_utils.compare_between_spectra.

    Returns comparison_range which is the energy range used for comparison.
    """
    try:
        ene = ene_grid[element]
        ml_spectrum = np.column_stack((ene, predicted_spectrum))
        exp_energy = np.array(exp_spectrum['energy'])
        exp_absorption = np.array(exp_spectrum['absorption'])
        expt_spectrum = np.column_stack((exp_energy, exp_absorption))

        opt_metric = "coss_deriv"
        other_metrics = ["pearson", "spearman", "coss", "kendalltaub", "coss_deriv", "normed_wasserstein"]

        erange = 35
        erange_threshold = 0.04
        truncation_strategy = "from_spect2"
        erange_lbound_delta = 5

        correlations, shift = compare_utils.compare_between_spectra(
            expt_spectrum,
            ml_spectrum,
            erange=erange,
            erange_threshold=erange_threshold,
            erange_lbound_delta=erange_lbound_delta,
            truncation_strategy=truncation_strategy,
            grid_interpolator=compare_utils.gridInterpolatorFixedSpacing(0.25),
            output_correlations=other_metrics,
            opt_strategy="grid_search_and_local_opt",
            accuracy=0.1,
            method=opt_metric,
            norm_y_axis=True
        )

        # Calculate the comparison range
        # The shift returned aligns ML spectrum to experimental spectrum
        # ML spectrum energy range after shift: (ene + shift)
        # The comparison uses erange (35 eV) starting from edge

        # For ML spectrum (spect2), find where edge starts
        ml_y_normalized = (ml_spectrum[:, 1] - np.min(ml_spectrum[:, 1])) / (np.max(ml_spectrum[:, 1]) - np.min(ml_spectrum[:, 1]))
        ml_edge_idx = np.argmax(ml_y_normalized > erange_threshold)
        ml_edge_energy = ml_spectrum[ml_edge_idx, 0]

        # The comparison range in the EXPERIMENTAL spectrum's energy scale
        # ML edge energy + shift = where ML edge aligns in exp energy scale
        comparison_start = ml_edge_energy + shift
        comparison_end = comparison_start + erange

        score = correlations.get(opt_metric, 0.0)
        if np.isnan(score) or np.isinf(score):
            score = 0.0

        return {
            'score': round(float(score), 3),
            'correlations': {k: round(float(v), 3) if not (np.isnan(v) or np.isinf(v)) else 0.0
                           for k, v in correlations.items()},
            'shift': round(float(shift), 2),
            'comparison_range': (round(float(comparison_start), 1), round(float(comparison_end), 1))
        }

    except Exception as e:
        print(f"Error in spectrum matching: {e}")
        import traceback
        traceback.print_exc()
        return {
            'score': 0.0,
            'correlations': {},
            'shift': 0.0,
            'comparison_range': None
        }

def build_matching_metadata(exp_data, scores, top_n=3):
    """
    Build metadata in the requested format:

    {
        experimental_spectrum_filename: {
            structure_name: {
                "pearson": score,
                "spearman": score
            },
            ...
        }
    }
    """
    if exp_data is None:
        raise ValueError("No experimental spectrum loaded")

    filename = exp_data.get("filename")
    if not filename:
        raise ValueError("Experimental spectrum filename is missing")

    if not scores:
        raise ValueError("No structure matching scores available")

    top_scores = scores[:top_n]

    structure_metadata = {}

    for entry in top_scores:
        structure_name = entry.get("structure_id", "unknown_structure")
        correlations = entry.get("correlations", {}) or {}

        structure_metadata[structure_name] = {
            "pearson": correlations.get("pearson"),
            "spearman": correlations.get("spearman"),
        }

    return {
        filename: structure_metadata
    }

def mark_active_structure_selected(scores, active_structure_id, only_active=True):
    """
    Mark the currently displayed structure as checked in the score table.

    If only_active=True, all other structures are unchecked so the table
    matches the structure currently shown in the viewer/plot.
    """
    if not scores or not active_structure_id:
        return scores

    active_structure_id = str(active_structure_id)

    for entry in scores:
        is_active = str(entry.get("structure_id")) == active_structure_id

        if is_active:
            entry["selected"] = True
        elif only_active:
            entry["selected"] = False

    return scores

def sort_scores_by_metric(scores, metric):
    """Sort scores list by the given metric. For normed_wasserstein, lower is better (sort ascending)."""
    if not scores:
        return scores

    reverse = metric != 'normed_wasserstein'

    def sort_key(entry):
        correlations = entry.get('correlations', {})
        val = correlations.get(metric, 0.0)
        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            return -999 if reverse else 999
        return val

    return sorted(scores, key=sort_key, reverse=reverse)
