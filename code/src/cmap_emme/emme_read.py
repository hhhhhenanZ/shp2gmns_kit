"""Readers for CMAP's Emme exports.

* Period shapefiles (``emme_links``, ``emme_nodes``): pyogrio when installed, otherwise a
  small built-in reader for dBASE and PolyLine shapefiles, so the converter also runs in
  a bare Python environment. Both return the same columns.
* ``attribs_pX.txt``: Emme extra-attribute file, whitespace separated, header on line 1
  [G "Network and extra attribute file layout"].
* ``network_pX.txt``: Emme transaction file; only counts and lanes are read (gate G12).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pandas as pd


# ---- dBASE ------------------------------------------------------------------------
def read_dbf(path: Path) -> pd.DataFrame:
    with open(path, "rb") as handle:
        header = handle.read(32)
        n_rows, header_len, row_len = struct.unpack("<IHH", header[4:12])
        fields = []
        while True:
            desc = handle.read(32)
            if desc[0] == 0x0D:
                break
            name = desc[:11].split(b"\0")[0].decode("ascii")
            fields.append((name, chr(desc[11]), desc[16]))
        handle.seek(header_len)
        raw = handle.read(n_rows * row_len)
    dtype = np.dtype([("_del", "S1")] + [(n, f"S{w}") for n, _, w in fields])
    table = np.frombuffer(raw, dtype=dtype, count=n_rows)
    out = {}
    for name, kind, _ in fields:
        text = np.char.strip(table[name].astype(str))
        if kind in ("N", "F"):
            out[name] = pd.to_numeric(pd.Series(text), errors="coerce")
        else:
            out[name] = pd.Series(text)
    return pd.DataFrame(out)


# ---- PolyLine geometry -------------------------------------------------------------
def read_polylines(path: Path) -> list[np.ndarray]:
    """Vertices of every record, in file order (same order as the .dbf)."""
    data = Path(path).read_bytes()
    shape_type = struct.unpack("<i", data[32:36])[0]
    if shape_type not in (3, 13, 23):
        raise ValueError(f"{path.name}: shape type {shape_type} is not PolyLine")
    lines, pos = [], 100
    while pos < len(data):
        _, words = struct.unpack(">ii", data[pos:pos + 8])
        content = data[pos + 8: pos + 8 + 2 * words]
        pos += 8 + 2 * words
        if struct.unpack("<i", content[:4])[0] == 0:
            lines.append(np.empty((0, 2)))
            continue
        n_parts, n_points = struct.unpack("<ii", content[36:44])
        start = 44 + 4 * n_parts
        pts = np.frombuffer(content[start:start + 16 * n_points], dtype="<f8").reshape(-1, 2)
        lines.append(pts)
    return lines


def read_links(path: Path) -> tuple[pd.DataFrame, list[np.ndarray], str]:
    try:
        import pyogrio  # noqa: F401
        import shapely
        frame = pyogrio.read_dataframe(path)
        coords = [np.asarray(shapely.get_coordinates(g))[:, :2] for g in frame.geometry]
        table = pd.DataFrame(frame.drop(columns="geometry"))
        return table, coords, "pyogrio"
    except ImportError:
        return read_dbf(path.with_suffix(".dbf")), read_polylines(path), "built-in reader"


def read_nodes(path: Path) -> tuple[pd.DataFrame, str]:
    try:
        import pyogrio
        frame = pyogrio.read_dataframe(path, read_geometry=False)
        return pd.DataFrame(frame), "pyogrio"
    except ImportError:
        return read_dbf(path.with_suffix(".dbf")), "built-in reader"


# ---- Emme text files ---------------------------------------------------------------
def read_extra_attributes(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=r"\s+")
    return frame.drop(columns=[c for c in frame.columns if c == "result"])


def read_transaction_counts(path: Path) -> dict:
    """Nodes, links and the lanes column of an Emme transaction file."""
    section, nodes, lanes = None, 0, []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("t nodes"):
                section = "nodes"
            elif line.startswith("t links"):
                section = "links"
            elif line.startswith("a"):
                parts = line.split()
                if section == "nodes":
                    nodes += 1
                elif section == "links":
                    lanes.append((int(parts[1]), int(parts[2]), float(parts[6])))
    frame = pd.DataFrame(lanes, columns=["inode", "jnode", "lanes"])
    return {"nodes": nodes, "links": len(frame), "lanes": frame}
