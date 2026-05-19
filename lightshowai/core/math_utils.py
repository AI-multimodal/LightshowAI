import pathlib
import numpy as np
from lightshowai.postprocess.shakeup import loadShakeupKernel, shakeup as shakeupSpectrum
from lightshowai.models import predict

all_elements = ['Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu']
ene_start = {'Ti': 4964.504, 'V': 5464.097, 'Cr': 5989.168, 'Mn': 6537.886,
             'Fe': 7111.23, 'Co': 7709.282, 'Ni': 8332.181, 'Cu': 8983.173}
ene_grid = {el: np.linspace(start, start + 35, 141) for el, start in ene_start.items()}
xas_model_names = [f'{el} FEFF' for el in all_elements] + ['Ti VASP', 'Cu VASP']

_DAT_PATH = pathlib.Path(__file__).parent.parent / "postprocess" / "Rutile-spfcn_model.dat"
_Aw = loadShakeupKernel(str(_DAT_PATH))

def apply_shakeup_if_needed(specs, element, el_type, shakeup_val):
    """Returns a new specs dictionary with shakeup applied on-the-fly if toggled ON."""
    if not specs or shakeup_val != 'yes':
        return specs
        
    orig_ene = ene_grid.get(element, ene_grid['Ti'])
    new_specs = {}
    for k, v in specs.items():
        shaken = shakeupSpectrum(np.column_stack((orig_ene, v)), _Aw, pad_right=10, truncate_right=0.5)
        new_specs[k] = np.interp(orig_ene, shaken[:, 0], shaken[:, 1]).tolist()
    return new_specs

def decorate_structure_with_xas(st, el_type):
    absorbing_site, spectroscopy_type = el_type.split(' ')
    st_dict = st.as_dict()
    if absorbing_site in st.composition:
        print("XAS Spectrum generated for structure:", st, absorbing_site, spectroscopy_type)
        specs = predict(st, absorbing_site, spectroscopy_type)
        st_dict['xas'] = specs
    else:
        st_dict['xas'] = {}
    return st_dict
