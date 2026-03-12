"""
@from Claude
Custom Tiled adapter for XDI (X-ray Data Interchange) files.

XDI is a standard format for X-ray absorption spectroscopy data,
commonly used at synchrotron beamlines like NSLS-II BMM.

Reference: https://github.com/XraySpectroscopy/XDI

Usage with Tiled 0.2.x:
    - Place this file alongside your config.yml
    - Register the MIME type application/x-xdi for .xdi files
    - See config.yml for wiring details

Tiled 0.2.x requires adapters to be classes with from_uris() classmethod.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from tiled.adapters.table import TableAdapter
from tiled.structures.core import Spec


def _parse_xdi(filepath):
    """
    Parse an XDI file into a DataFrame and metadata dict.
    """
    filepath = Path(filepath)
    header_metadata = {}
    column_names = []
    data_start_line = 0

    with open(filepath, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # End-of-header markers
        if stripped == "# ///" or stripped.startswith("#---") or stripped.startswith("# ---"):
            continue

        if stripped.startswith("#"):
            # Parse column definitions: "# Column.N: name unit"
            col_match = re.match(r"^#\s*Column\.(\d+):\s*(.+)$", stripped)
            if col_match:
                col_info = col_match.group(2).strip()
                column_names.append(col_info.split()[0])
                continue

            # Parse key-value metadata: "# Namespace.key: value"
            kv_match = re.match(r"^#\s*([\w.]+):\s*(.+)$", stripped)
            if kv_match:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except (ValueError, OverflowError):
                    pass
                header_metadata[key] = value
                continue

            # Column header line (e.g., "#   e   norm   nbkg ...")
            if not stripped.startswith("# XDI") and len(stripped.split()) > 2:
                potential_cols = stripped.lstrip("#").split()
                if not column_names and all(not c[0].isdigit() for c in potential_cols):
                    column_names = potential_cols
        else:
            if stripped:
                data_start_line = i
                break

    df = pd.read_csv(
        filepath,
        comment="#",
        sep=r"\s+",
        header=None,
        skiprows=data_start_line,
    )

    if column_names and len(column_names) == len(df.columns):
        df.columns = column_names
    elif column_names and len(column_names) < len(df.columns):
        extra = [f"col_{i}" for i in range(len(column_names), len(df.columns))]
        df.columns = column_names + extra
    else:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]

    # Add convenience keys
    if "Element.symbol" in header_metadata:
        header_metadata["element"] = header_metadata["Element.symbol"]
    if "Element.edge" in header_metadata:
        header_metadata["edge"] = header_metadata["Element.edge"]
    if "Sample.name" in header_metadata:
        header_metadata["sample_name"] = header_metadata["Sample.name"]

    return df, header_metadata


class XDIAdapter(TableAdapter):
    """
    Tiled 0.2.x compatible adapter for XDI files.

    Provides from_uris() classmethod required by the catalog registration API.
    """

    @classmethod
    def from_uris(
        cls,
        *uris,
        structure=None,
        metadata=None,
        specs=None,
        access_policy=None,
        **kwargs,
    ):
        """
        Create an XDIAdapter from one or more file URIs.

        Parameters
        ----------
        uris : str
            File URIs (e.g., "file:///path/to/file.xdi")
        structure : optional
            Pre-computed structure (ignored, we compute from file)
        metadata : dict, optional
            Additional metadata
        specs : list, optional
            Tiled specs
        """
        # Convert URI to filepath
        filepath = urlparse(uris[0]).path

        df, xdi_metadata = _parse_xdi(filepath)

        if metadata is None:
            metadata = {}
        merged_metadata = {**xdi_metadata, **metadata}

        if specs is None:
            specs = []
        specs = list(specs) + [Spec("xdi")]

        return cls.from_pandas(
            df,
            npartitions=1,
            metadata=merged_metadata,
            specs=specs,
        )