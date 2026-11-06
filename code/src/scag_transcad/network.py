"""node.csv and link.csv for one period, for the Tier-1 network.

Tier 1: SCAG's trip tables are keyed by Tier-1 TAZ id, so only Tier-1 centroids (facility
type 100) carry zone ids. Tier-2 centroid connectors (facility 200) are closed to every
mode and carry no loaded flow, so by default they are not written and the nodes only they
touch are dropped with them (``output > keep_closed_links``).

Column order in link.csv: the TAPlite/GMNS columns the kernel reads, then the SCAG
classification columns this converter adds, then ``toll_<mode>``, then the shapefile's own
fields - by default only the ones that belong to this period (``output >
period_fields_only``), unchanged and under their shapefile names.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .dictionary import DAILY, period_of

METERS_PER_MILE = 1609.344
KPH_PER_MPH = 1.609344
TARGET_CRS = "EPSG:4326"
LEADING_COLUMNS = [
    "link_id", "from_node_id", "to_node_id", "dir_flag", "length", "lanes", "capacity",
    "free_speed", "toll", "link_type", "allowed_use", "vdf_type", "vdf_alpha", "vdf_beta",
    "vdf_plf", "ref_volume", "ref_cost", "vdf_free_speed_mph", "vdf_length_mi", "vdf_fftt",
    "crs", "geometry", "name", "org_link_id", "dir_side", "facility_type", "area_type",
    "posted_speed_mph", "vdf_group", "allowed_use_rule", "hourly_link_capacity",
]


def assign_node_ids(node_count: int, centroids: pd.DataFrame, first_road_id: int,
                    surviving: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Node ids, and which nodes go into node.csv.

    A centroid takes its zone_id; every other node that a written link touches is numbered
    from ``first_road_id`` upward, in first-appearance order. Nodes no written link touches
    (the Tier-2 centroids, once their connectors are dropped) are left out.
    """
    resolved = centroids[centroids["node_index"] >= 0]
    if int(first_road_id) <= int(centroids["zone_id"].max()):
        raise ValueError("topology > first_road_node_id must exceed the largest zone_id")
    kept = np.ones(node_count, dtype=bool) if surviving is None else np.zeros(node_count, dtype=bool)
    if surviving is not None:
        kept[np.asarray(surviving, dtype=np.int64)] = True
    centroid_nodes = resolved["node_index"].to_numpy()
    missing = centroid_nodes[~kept[centroid_nodes]]
    if len(missing):
        raise ValueError(f"{len(missing)} zone centroids are not touched by any written link; "
                         "they would lose their demand")
    ids = np.zeros(node_count, dtype=np.int64)
    is_centroid = np.zeros(node_count, dtype=bool)
    is_centroid[centroid_nodes] = True
    ids[centroid_nodes] = resolved["zone_id"].to_numpy()
    others = np.flatnonzero(~is_centroid & kept)
    ids[others] = int(first_road_id) + np.arange(len(others))
    return ids, kept


def node_lonlat(topology) -> tuple[np.ndarray, np.ndarray]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(topology.frame.crs, TARGET_CRS, always_xy=True)
    lon, lat = transformer.transform(topology.node_xy[:, 0], topology.node_xy[:, 1])
    return np.asarray(lon), np.asarray(lat)


def node_table(topology, node_ids: np.ndarray, centroids: pd.DataFrame,
               kept: np.ndarray | None = None) -> pd.DataFrame:
    lon, lat = node_lonlat(topology)
    count = topology.node_count
    table = pd.DataFrame({
        "node_id": node_ids,
        "zone_id": pd.array([pd.NA] * count, dtype="Int64"),
        "x_coord": np.round(lon, 7),
        "y_coord": np.round(lat, 7),
        "zone_type": "",
        "taz_id": pd.array([pd.NA] * count, dtype="Int64"),
        "centroid_method": "",
        "centroid_confidence": "",
    })
    resolved = centroids[centroids["node_index"] >= 0]
    rows = resolved["node_index"].to_numpy()
    table.loc[rows, "zone_id"] = resolved["zone_id"].to_numpy()
    table.loc[rows, "zone_type"] = resolved["zone_type"].to_numpy()
    table.loc[rows, "taz_id"] = resolved["taz_id"].to_numpy()
    table.loc[rows, "centroid_method"] = resolved["method"].to_numpy()
    table.loc[rows, "centroid_confidence"] = resolved["confidence"].to_numpy()
    if kept is not None:
        table = table[kept]
    return table.sort_values("node_id").reset_index(drop=True)


def geometry_wkt(topology, directed: pd.DataFrame, rows: np.ndarray) -> np.ndarray:
    """WGS84 WKT for directed rows; BA rows are reversed so they run from->to."""
    import shapely

    lines = np.asarray(topology.frame.geometry.to_crs(TARGET_CRS).values)
    record = directed["record"].to_numpy()[rows]
    geometry = lines[record]
    backward = (directed["side"].to_numpy()[rows] == "BA")
    geometry[backward] = shapely.reverse(geometry[backward])
    return shapely.to_wkt(geometry, rounding_precision=7, trim=True)


def tidy_original(attributes: pd.DataFrame) -> pd.DataFrame:
    """Shapefile attributes for output. A float column whose values are all whole numbers
    was an integer field read as float because of blanks; it is written as integers."""
    frame = attributes.copy()
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_float_dtype(series):
            valid = series.dropna()
            if len(valid) and bool((np.mod(valid, 1) == 0).all()) and valid.abs().max() < 2 ** 53:
                frame[column] = series.astype("Int64")
    return frame


def original_columns(dictionary, columns, period: str, options: dict) -> list[str]:
    """Which shapefile fields this period's link.csv keeps.

    With ``period_fields_only`` (the default): the fields that carry no period, plus this
    period's own, plus the daily totals when ``include_daily_fields``. Otherwise all of them.
    """
    if not options.get("period_fields_only", True):
        return list(columns)
    kept = []
    for column in columns:
        dbd, _ = dictionary.describe(column)
        tag = period_of(dbd or column)
        if tag == "" or tag == period.upper():
            kept.append(column)
        elif tag == DAILY and options.get("include_daily_fields", True):
            kept.append(column)
    return kept


def _int_or_blank(values: np.ndarray) -> pd.array:
    return pd.array(np.where(np.isfinite(values), np.round(values), np.nan),
                    dtype="Float64").astype("Int64")


def static_link_table(region, context: dict, node_ids: np.ndarray, vdf: dict,
                      allowed: np.ndarray, rule_name: np.ndarray,
                      write_mask: np.ndarray) -> pd.DataFrame:
    """Columns that do not change by period, one row per written link, sorted."""
    directed = context["directed"]
    rows = np.flatnonzero(write_mask)
    a = directed["a"].to_numpy()[rows]
    b = directed["b"].to_numpy()[rows]
    length_mi = context["length_mi"][rows]
    free_time = context["free_time"][rows]
    facility = context["facility_type"][rows]
    area = context["area_type"][rows]
    speed_mph = 60.0 * length_mi / free_time
    # SCAG rule: link_type = 1000 * area type + facility type, because SCAG's facility
    # codes reach 200 (NVTA's Cube converter uses 100, for facility types 0-6).
    # Decode with divmod(link_type, region.area_type_multiplier).
    link_type = region.area_type_multiplier * area + facility
    table = pd.DataFrame({
        "_row": rows,
        "from_node_id": node_ids[a],
        "to_node_id": node_ids[b],
        "dir_flag": 1,
        "length": length_mi * METERS_PER_MILE,
        "capacity": context["lane_capacity"][rows],
        "free_speed": speed_mph * KPH_PER_MPH,
        "toll": 0.0,
        "link_type": _int_or_blank(link_type),
        "allowed_use": allowed[rows],
        "vdf_type": vdf["vdf_type"][rows],
        "vdf_alpha": vdf["vdf_alpha"][rows],
        "vdf_beta": vdf["vdf_beta"][rows],
        "ref_cost": 0.0,
        "vdf_free_speed_mph": speed_mph,
        "vdf_length_mi": length_mi,
        "vdf_fftt": free_time,
        "crs": TARGET_CRS,
        "name": pd.Series(context["road_name"][rows]).fillna("").astype(str).to_numpy(),
        "org_link_id": context["link_ids"][directed["record"].to_numpy()[rows]],
        "dir_side": directed["side"].to_numpy()[rows],
        "facility_type": _int_or_blank(facility),
        "area_type": _int_or_blank(area),
        "posted_speed_mph": _int_or_blank(context["posted_speed"][rows]),
        "vdf_group": vdf["vdf_group"][rows],
        "allowed_use_rule": rule_name[rows],
    })
    table = table.sort_values(["from_node_id", "to_node_id", "org_link_id", "dir_side"],
                              kind="mergesort").reset_index(drop=True)
    table.insert(0, "link_id", np.arange(1, len(table) + 1))
    table["geometry"] = geometry_wkt(context["topology"], directed, table["_row"].to_numpy())
    return table


def period_link_table(region, static: pd.DataFrame, lanes: np.ndarray, vdf_plf: float,
                      include_geometry: bool = True) -> pd.DataFrame:
    rows = static["_row"].to_numpy()
    period_lanes = lanes[rows]
    table = static.copy()
    table["lanes"] = _int_or_blank(period_lanes)
    table["vdf_plf"] = vdf_plf
    # Left blank on purpose. SCAG stores no link total, only the eight class flows,
    # and those stay in this file as their own columns; anyone comparing an assignment
    # against SCAG sums them there and chooses the vehicle or PCE basis themselves.
    table["ref_volume"] = ""
    table["hourly_link_capacity"] = static["capacity"].to_numpy() * period_lanes
    for mode in region.modes:
        table[f"toll_{mode.mode_type}"] = 0.0
    leading = [c for c in LEADING_COLUMNS if include_geometry or c != "geometry"]
    tolls = [f"toll_{mode.mode_type}" for mode in region.modes]
    return table[["_row", *leading, *tolls]]


def write_csv(frame: pd.DataFrame, path: Path, bom: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n",
                 encoding="utf-8-sig" if bom else "utf-8")


def write_link_csv(path: Path, core: pd.DataFrame, original: pd.DataFrame,
                   record: np.ndarray, columns: list[str], bom: bool = True) -> int:
    rows = core["_row"].to_numpy()
    body = original.iloc[record[rows]][columns].reset_index(drop=True)
    frame = pd.concat([core.drop(columns="_row").reset_index(drop=True), body], axis=1)
    write_csv(frame, path, bom=bom)
    return len(frame)
