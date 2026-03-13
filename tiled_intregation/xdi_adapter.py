# xdi_adapter.py
from io import StringIO
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import dask.dataframe
import pandas as pd

from tiled.adapters.array import ArrayAdapter
from tiled.adapters.core import Adapter
from tiled.catalog.orm import Node
from tiled.structures.core import Spec, StructureFamily
from tiled.structures.data_source import DataSource
from tiled.structures.table import TableStructure
from tiled.type_aliases import JSON
from tiled.utils import path_from_uri
from tiled.adapters.utils import init_adapter_from_catalog


class XDIAdapter(Adapter[TableStructure]):
    """Adapter for XDI (.xdi) spectroscopy files."""

    structure_family = StructureFamily.table

    def __init__(
        self,
        data_uri: str,
        structure: Optional[TableStructure] = None,
        *,
        metadata: Optional[JSON] = None,
        specs: Optional[List[Spec]] = None,
    ) -> None:
        filepath = path_from_uri(data_uri)
        df, xdi_metadata = _parse_xdi(str(filepath))

        if metadata is None:
            metadata = xdi_metadata
        else:
            metadata = {**xdi_metadata, **metadata}

        if specs is None:
            specs = [Spec("xdi")]

        self._ddf = dask.dataframe.from_pandas(df, npartitions=1)

        if structure is None:
            structure = TableStructure.from_dask_dataframe(self._ddf)

        super().__init__(structure, metadata=metadata, specs=specs)

    @classmethod
    def from_catalog(
        cls,
        data_source: DataSource[TableStructure],
        node: Node,
        /,
        **kwargs: Optional[Any],
    ) -> "XDIAdapter":
        return init_adapter_from_catalog(cls, data_source, node, **kwargs)

    @classmethod
    def from_uris(
        cls,
        *data_uris: str,
        **kwargs: Optional[Any],
    ) -> "XDIAdapter":
        return cls(data_uris[0], **kwargs)

    def read(self, fields: Optional[List[str]] = None) -> pd.DataFrame:
        df = self._ddf
        if fields is not None:
            df = df[fields]
        return df.compute()

    def read_partition(
        self, indx: int, fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        df = self._ddf
        if fields is not None:
            df = df[fields]
        return df.compute()

    def get(self, key: str) -> Optional[ArrayAdapter]:
        if key not in self.structure().columns:
            return None
        return ArrayAdapter.from_array(self.read([key])[key].values)

    def __getitem__(self, key: str) -> ArrayAdapter:
        return ArrayAdapter.from_array(self.read([key])[key].values)

    def items(self) -> Iterator[Tuple[str, ArrayAdapter]]:
        yield from (
            (key, ArrayAdapter.from_array(self.read([key])[key].values))
            for key in self._structure.columns
        )


def _parse_xdi(filepath: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Read an XDI file and return (DataFrame, metadata_dict)."""
    metadata: Dict[str, str] = {}
    colspec: Dict[int, str] = {}
    data_lines: List[str] = []

    in_data = False
    saw_triple_slash = False

    def strip_hash(line: str) -> str:
        s = line[1:]
        if s.startswith(" "):
            s = s[1:]
        return s.rstrip("\n")

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()

            if s.startswith("#"):
                payload = strip_hash(line).strip()

                if payload == "///":
                    saw_triple_slash = True
                    in_data = True
                    continue

                if payload.startswith("Column."):
                    try:
                        left, right = payload.split(":", 1)
                        _, n_str = left.split(".", 1)
                        colspec[int(n_str.strip())] = " ".join(right.strip().split())
                        continue
                    except Exception:
                        pass

                if ":" in payload:
                    k, v = payload.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k:
                        metadata[k] = v
                continue

            if not in_data and not saw_triple_slash:
                if s and (s[0].isdigit() or s[0] in "+-."):
                    in_data = True

            if in_data and s:
                if s.startswith("---"):
                    continue
                data_lines.append(line)

    if not data_lines:
        return pd.DataFrame(), metadata

    df = pd.read_csv(
        StringIO("".join(data_lines)),
        sep=r"\s+",
        header=None,
        engine="python",
    )

    if colspec:
        df.columns = [colspec.get(i + 1, f"col{i+1}") for i in range(df.shape[1])]
    else:
        df.columns = [f"col{i+1}" for i in range(df.shape[1])]

    return df, metadata