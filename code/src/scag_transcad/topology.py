"""Nodes and directed links from a TransCAD line layer exported to shapefile.

The export has no node layer and no A/B node fields, so nodes are the distinct end points
of the line geometries, matched on coordinates rounded to ``decimals`` (millimetres in
SCAG's UTM metres). A TransCAD line is one record with ``Dir`` (data dictionary):
0 carries traffic both ways, with ``AB_*`` and ``BA_*`` attributes; 1 is AB only;
-1 is BA only. AB runs from the first vertex to the last.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DIR_BOTH, DIR_AB, DIR_BA = 0, 1, -1


@dataclass
class Topology:
    frame: "object"          # the GeoDataFrame as read, record order, source CRS
    node_xy: np.ndarray      # (nodes, 2), source CRS
    record_first: np.ndarray # node index at each record's first vertex
    record_last: np.ndarray  # node index at each record's last vertex

    @property
    def node_count(self) -> int:
        return len(self.node_xy)


def read_shapefile(path):
    import geopandas as gpd

    try:
        return gpd.read_file(path, engine="pyogrio")
    except (TypeError, ValueError, ImportError):
        return gpd.read_file(path)


def build_topology(frame, decimals: int = 3) -> Topology:
    import shapely

    geometry = frame.geometry.values
    if pd.isna(geometry).any() or shapely.is_empty(geometry).any():
        raise ValueError("the network shapefile has records without geometry")
    kinds = set(shapely.get_type_id(geometry).tolist())
    if not kinds <= {1, 5}:  # LineString, MultiLineString
        raise ValueError(f"expected line geometries; found geometry type ids {sorted(kinds)}")
    first = shapely.get_point(shapely.get_geometry(geometry, 0), 0)
    last = shapely.get_point(shapely.get_geometry(geometry, -1), -1)
    ends = np.vstack([
        np.column_stack([shapely.get_x(first), shapely.get_y(first)]),
        np.column_stack([shapely.get_x(last), shapely.get_y(last)]),
    ])
    rounded = np.round(ends, decimals)
    codes, uniques = pd.MultiIndex.from_arrays([rounded[:, 0], rounded[:, 1]]).factorize()
    count = len(frame)
    return Topology(
        frame=frame,
        node_xy=np.asarray(uniques.to_list(), dtype=float),
        record_first=codes[:count].astype(np.int64),
        record_last=codes[count:].astype(np.int64),
    )


def directed_links(topology: Topology, dir_field: str) -> pd.DataFrame:
    """One row per travel direction: record, side (AB/BA), a (from node), b (to node)."""
    direction = pd.to_numeric(topology.frame[dir_field], errors="coerce")
    invalid = direction.isna() | ~direction.isin([DIR_BOTH, DIR_AB, DIR_BA])
    if invalid.any():
        raise ValueError(f"{int(invalid.sum())} records have a {dir_field} other than 0, 1, -1")
    record = np.arange(len(direction))
    ab = direction.isin([DIR_BOTH, DIR_AB]).to_numpy()
    ba = direction.isin([DIR_BOTH, DIR_BA]).to_numpy()
    return pd.concat([
        pd.DataFrame({"record": record[ab], "side": "AB",
                      "a": topology.record_first[ab], "b": topology.record_last[ab]}),
        pd.DataFrame({"record": record[ba], "side": "BA",
                      "a": topology.record_last[ba], "b": topology.record_first[ba]}),
    ], ignore_index=True)
