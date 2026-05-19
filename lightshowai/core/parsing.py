import re
import pathlib
import io
import json
import numpy as np
from base64 import b64decode
from pymatgen.core.structure import Structure

def parse_file_columns(contents, filename):
    """
    Parse uploaded file and extract all columns with their data.
    Supports XDI format with # Column.N: name headers.
    """
    if contents is None:
        return None

    content_type, content_string = contents.split(',')
    decoded = b64decode(content_string)

    try:
        if filename is None:
            filename = "unknown.dat"

        ext = pathlib.Path(filename).suffix.lower()
        print(f"=== DEBUG: Parsing file '{filename}' with extension '{ext}'")

        columns = []
        data = []

        auto_x_col = 0
        auto_y_col = 1

        if ext in ['.csv', '.dat', '.txt', '.xdi']:
            text = decoded.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

            comment_lines = []
            data_lines = []

            for line in lines:
                if line.startswith(('#', '%', '!')):
                    comment_lines.append(line)
                else:
                    data_lines.append(line)

            if len(data_lines) == 0:
                raise ValueError("No data lines found in file")

            xdi_columns = {}
            energy_col_candidates = []
            absorption_col_candidates = []

            for comment in comment_lines:
                xdi_match = re.match(r'#\s*Column\.(\d+):\s*(.+)', comment, re.IGNORECASE)
                if xdi_match:
                    col_num = int(xdi_match.group(1)) - 1
                    col_name = xdi_match.group(2).strip()
                    xdi_columns[col_num] = col_name
                    print(f"=== DEBUG: Found XDI column {col_num}: '{col_name}'")

                    col_lower = col_name.lower()
                    if any(term in col_lower for term in ['energy', ' e ', 'ev', 'photon']):
                        energy_col_candidates.append(col_num)

                    if any(term in col_lower for term in ['norm', 'absorption', 'abs', 'mu', 'flat']):
                        absorption_col_candidates.append(col_num)

            if comment_lines and not xdi_columns:
                last_comment = comment_lines[-1]
                header_text = last_comment.lstrip('#').strip()
                header_parts = header_text.split()

                if len(header_parts) >= 2 and ':' not in header_text:
                    print(f"=== DEBUG: Found inline header: {header_parts}")
                    for i, name in enumerate(header_parts):
                        xdi_columns[i] = name
                        name_lower = name.lower()
                        if name_lower in ['e', 'energy', 'ev']:
                            energy_col_candidates.append(i)
                        if name_lower in ['norm', 'flat', 'abs', 'mu', 'absorption']:
                            absorption_col_candidates.append(i)

            first_line = data_lines[0]

            if ',' in first_line:
                delimiter = ','
            else:
                delimiter = None

            first_parts = first_line.split(delimiter) if delimiter else first_line.split()
            num_columns = len(first_parts)

            try:
                float(first_parts[0].strip())
                header = None
                start_idx = 0
            except ValueError:
                header = [p.strip() for p in first_parts]
                start_idx = 1
                if not xdi_columns:
                    for i, name in enumerate(header):
                        xdi_columns[i] = name

            data = [[] for _ in range(num_columns)]

            for line in data_lines[start_idx:]:
                parts = line.split(delimiter) if delimiter else line.split()
                for i, part in enumerate(parts):
                    if i < num_columns:
                        try:
                            data[i].append(float(part.strip()))
                        except ValueError:
                            pass

            for i in range(num_columns):
                if i in xdi_columns:
                    col_name = xdi_columns[i]
                elif header and i < len(header):
                    col_name = header[i]
                else:
                    col_name = f"Column {i+1}"

                sample_values = data[i][:5] if len(data[i]) >= 5 else data[i]
                columns.append({
                    'index': i,
                    'name': col_name,
                    'num_values': len(data[i]),
                    'sample_values': sample_values
                })

            if energy_col_candidates:
                auto_x_col = energy_col_candidates[0]

            if absorption_col_candidates:
                for candidate in absorption_col_candidates:
                    col_name = xdi_columns.get(candidate, '').lower()
                    if 'norm' in col_name or 'flat' in col_name:
                        auto_y_col = candidate
                        break
                else:
                    auto_y_col = absorption_col_candidates[0]
            elif len(columns) > 1:
                auto_y_col = 1

        elif ext == '.mat':
            try:
                from scipy.io import loadmat
                mat_data = loadmat(io.BytesIO(decoded))

                data_keys = [k for k in mat_data.keys() if not k.startswith('__')]

                for i, key in enumerate(data_keys):
                    arr = mat_data[key]
                    if isinstance(arr, np.ndarray) and arr.size > 1:
                        flat_arr = arr.flatten().astype(float).tolist()
                        sample_values = flat_arr[:5] if len(flat_arr) >= 5 else flat_arr
                        columns.append({
                            'index': i,
                            'name': key,
                            'num_values': len(flat_arr),
                            'sample_values': sample_values
                        })
                        data.append(flat_arr)

                        key_lower = key.lower()
                        if any(term in key_lower for term in ['energy', 'e', 'ev']):
                            auto_x_col = i
                        if any(term in key_lower for term in ['absorption', 'abs', 'mu', 'norm']):
                            auto_y_col = i

            except ImportError:
                raise ValueError("scipy is required to read .mat files")

        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if len(columns) < 2:
            raise ValueError("File must have at least 2 columns for X and Y axes")
        
        for col in columns:
            name_lower = str(col['name']).lower().strip()
            if name_lower in ['energy', 'e', 'ev']:
                auto_x_col = col['index']
            elif name_lower in ['iff', 'if', 'fluor', 'it', 'trans', 'absorption', 'mu']:
                auto_y_col = col['index']

        auto_x_col = min(auto_x_col, len(columns) - 1)
        auto_y_col = min(auto_y_col, len(columns) - 1)
        if auto_x_col == auto_y_col and len(columns) > 1:
            auto_y_col = 1 if auto_x_col == 0 else 0

        print(f"=== DEBUG: Found {len(columns)} columns")
        print(f"=== DEBUG: Auto-selected X={auto_x_col}, Y={auto_y_col}")
        
        col_names_lower = [str(col['name']).lower().strip() for col in columns]
        is_new_csv = ("energy" in col_names_lower and "i0" in col_names_lower and 
                      any(c in col_names_lower for c in ["iff", "it", "ir"]))
        
        return {
            'columns': columns,
            'data': data,
            'filename': filename,
            'auto_x_col': auto_x_col,
            'auto_y_col': auto_y_col,
            'detected_format': 'new_xas_csv' if is_new_csv else 'generic_csv'
        }

    except Exception as e:
        print(f"Error parsing file columns: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}

def parse_structure_file(contents, filename):
    """
    Parse a structure file from base64-encoded contents.
    Supports CIF, VASP/POSCAR, and JSON formats.
    """
    try:
        content_type, content_string = contents.split(',')
        decoded = b64decode(content_string)

        ext = pathlib.Path(filename).suffix.lower()

        if ext in ['.cif']:
            # CIF format
            from pymatgen.io.cif import CifParser
            text = decoded.decode('utf-8')
            parser = CifParser.from_str(text)
            st = parser.parse_structures()[0]
        elif ext in ['.vasp', '.poscar', '']:
            # VASP/POSCAR format
            from pymatgen.io.vasp import Poscar
            text = decoded.decode('utf-8')
            poscar = Poscar.from_str(text)
            st = poscar.structure
        elif ext == '.json':
            # JSON format (pymatgen Structure dict)
            text = decoded.decode('utf-8')
            data = json.loads(text)
            st = Structure.from_dict(data)
        else:
            # Try to auto-detect format
            text = decoded.decode('utf-8')
            try:
                # Try CIF first
                from pymatgen.io.cif import CifParser
                parser = CifParser.from_str(text)
                st = parser.parse_structures()[0]
            except:
                try:
                    # Try POSCAR
                    from pymatgen.io.vasp import Poscar
                    poscar = Poscar.from_str(text)
                    st = poscar.structure
                except:
                    raise ValueError(f"Could not parse file format: {ext}")

        return st
    except Exception as e:
        print(f"Error parsing structure file {filename}: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_mpid_list(value):
    if not value:
        return []

    if isinstance(value, list):
        text = " ".join(str(x) for x in value if x)
    else:
        text = str(value)

    mpids = [m.lower() for m in re.findall(r"mp-\d+", text, flags=re.IGNORECASE)]

    # de-duplicate while preserving order
    seen = set()
    result = []
    for mpid in mpids:
        if mpid not in seen:
            seen.add(mpid)
            result.append(mpid)

    return result
