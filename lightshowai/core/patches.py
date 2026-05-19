import numpy as np

def _patch_pymatgen_neighbors():
    try:
        from pymatgen.optimization import neighbors as pmg_neighbors
        _original_find_points = pmg_neighbors.find_points_in_spheres

        def _patched_find_points_in_spheres(
            all_coords, center_coords, r, pbc, lattice, tol=1e-8
        ):
            pbc = np.asarray(pbc, dtype=np.int64)
            return _original_find_points(
                all_coords, center_coords, r, pbc, lattice, tol
            )

        pmg_neighbors.find_points_in_spheres = _patched_find_points_in_spheres
        # print("Applied Windows int64 compatibility patch for pymatgen")
    except Exception as e:
        print(f"Warning: Could not apply pymatgen patch: {e}")

def apply_pymatgen_patch():
    _patch_pymatgen_neighbors()
