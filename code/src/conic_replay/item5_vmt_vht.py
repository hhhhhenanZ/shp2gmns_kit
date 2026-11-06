"""Item 5 -- VMT, VHT, PMT, PHT and network speed.

Definitions, applied identically to the Cube side and the TAPlite side::

    VMT = volume * length_mi
    VHT = volume * travel_time_min / 60          ( == VMT / speed )
    PMT = sum_over_modes( mode_volume * occ ) * length_mi
    PHT = sum_over_modes( mode_volume * occ ) * travel_time_min / 60

    network speed = total VMT / total VHT

PMT and PHT use the per-mode volumes rather than a single average occupancy,
because occupancy differs by mode (sov 1, hov2 2, hov3 3.5, com 1, trk 1,
apv 1.6) and the mode mix differs by link. A network-average occupancy applied to
link VMT gives a different -- wrong -- answer wherever the mix is not the network
mix.

Network speed is total VMT / total VHT. The arithmetic mean of link speeds is a
different quantity entirely; it is reported beside the right one and explicitly
labelled, which is what stops it being reintroduced later.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import vdf_math
from .config import (
    CLOSED_LIMIT_CODE,
    CONNECTOR_FTYPE,
    FTYPE_LABEL,
    HOV3_OCCUPANCY_SENSITIVITY,
    HOV_LIMIT_CODES,
    LIMIT_LABEL,
    MODES,
)

MEASURES = ("VMT", "VHT", "PMT", "PHT")
SIDES = ("cube", "taplite")


def _person_volume(frame: pd.DataFrame, prefix: str, occupancy: dict) -> pd.Series:
    """Occupancy-weighted volume: sum over modes of mode_volume * occ."""
    total = pd.Series(0.0, index=frame.index)
    for mode in MODES:
        column = f"{prefix}{mode}"
        if column in frame.columns:
            total = total + frame[column].fillna(0.0) * float(occupancy[mode])
    return total


def build_link_measures(joined: pd.DataFrame, occupancy: dict) -> pd.DataFrame:
    """Per-link VMT / VHT / PMT / PHT for both sides, plus per-mode VMT.

    Every measure is computed here from the definitions. The kernel's own VMT / VHT
    / PMT / PHT columns are carried alongside and differenced, so the identities are
    demonstrated rather than trusted.
    """
    frame = joined
    out = pd.DataFrame(index=frame.index)

    for column in ("link_id", "from_node_id", "to_node_id", "name", "FTYPE",
                   "ATYPE_CODE", "JUR", "TOLLGRP", "period_limit", "allowed_use",
                   "lanes"):
        out[column] = frame[column]
    out["ftype_label"] = frame["FTYPE"].map(FTYPE_LABEL)
    out["limit_label"] = frame["period_limit"].map(LIMIT_LABEL)
    out["is_connector"] = frame["FTYPE"] == CONNECTOR_FTYPE
    out["is_managed_lane"] = frame["TOLLGRP"].fillna(0) > 0
    out["is_hov"] = frame["period_limit"].isin(HOV_LIMIT_CODES)
    out["is_closed"] = frame["period_limit"] == CLOSED_LIMIT_CODE

    length = frame["vdf_length_mi"]
    out["length_mi"] = length

    # ---- Cube ------------------------------------------------------------
    cube_volume = frame["cube_vol"]
    cube_speed = frame["cube_spd"]
    # Cube stores no travel time; it is recovered from length and speed. On
    # connectors speed == free speed, so this is exact there too.
    cube_time_min = np.divide(
        length.to_numpy(dtype=float) * 60.0,
        cube_speed.to_numpy(dtype=float),
        out=np.zeros(len(frame)),
        where=cube_speed.to_numpy(dtype=float) > 0,
    )
    out["cube_volume"] = cube_volume
    out["cube_speed_mph"] = cube_speed
    out["cube_free_speed_mph"] = frame["cube_ffspd"]
    out["cube_travel_time_min"] = cube_time_min
    out["cube_VMT"] = vdf_math.vmt(cube_volume, length)
    out["cube_VHT"] = vdf_math.vht(cube_volume, cube_time_min)
    cube_person = _person_volume(frame, "cube_vol_", occupancy)
    out["cube_person_volume"] = cube_person
    out["cube_PMT"] = vdf_math.vmt(cube_person, length)
    out["cube_PHT"] = vdf_math.vht(cube_person, cube_time_min)
    # Cube's own stored VMT, for the identity check.
    out["cube_VMT_stored"] = frame["cube_vmt"]
    out["cube_VMT_delta_vs_stored"] = out["cube_VMT"] - frame["cube_vmt"]

    # ---- TAPlite ---------------------------------------------------------
    tap_volume = frame["tap_volume"]
    tap_time_min = frame["tap_travel_time"]
    out["taplite_volume"] = tap_volume
    out["taplite_speed_mph"] = frame["tap_speed_mph"]
    out["taplite_travel_time_min"] = tap_time_min
    out["taplite_VMT"] = vdf_math.vmt(tap_volume, length)
    out["taplite_VHT"] = vdf_math.vht(tap_volume, tap_time_min)
    tap_person = _person_volume(frame, "tap_mod_vol_", occupancy)
    out["taplite_person_volume"] = tap_person
    out["taplite_PMT"] = vdf_math.vmt(tap_person, length)
    out["taplite_PHT"] = vdf_math.vht(tap_person, tap_time_min)

    # VHT by the other route, VMT / speed. Two definitions, one column each.
    out["taplite_VHT_from_speed"] = np.divide(
        out["taplite_VMT"].to_numpy(dtype=float),
        frame["tap_speed_mph"].to_numpy(dtype=float),
        out=np.zeros(len(frame)),
        where=frame["tap_speed_mph"].to_numpy(dtype=float) > 0,
    )
    out["taplite_VHT_delta_two_routes"] = out["taplite_VHT"] - out["taplite_VHT_from_speed"]

    # The kernel's own columns, differenced against ours.
    for measure in MEASURES:
        kernel_column = f"tap_{measure}"
        if kernel_column in frame.columns:
            out[f"kernel_{measure}"] = frame[kernel_column]
            out[f"kernel_{measure}_delta"] = out[f"taplite_{measure}"] - frame[kernel_column]

    # ---- per-mode VMT, both sides ----------------------------------------
    for mode in MODES:
        cube_column = f"cube_vol_{mode}"
        tap_column = f"tap_mod_vol_{mode}"
        if cube_column in frame.columns:
            out[f"cube_VMT_{mode}"] = vdf_math.vmt(frame[cube_column].fillna(0.0), length)
        if tap_column in frame.columns:
            out[f"taplite_VMT_{mode}"] = vdf_math.vmt(frame[tap_column].fillna(0.0), length)

    # ---- hov3 occupancy sensitivity --------------------------------------
    # occ 3.5 comes from mode_type.csv but has no located source; 3.0 is the
    # conventional lower bound. Both are published so the reader can see the span.
    for occ_value in HOV3_OCCUPANCY_SENSITIVITY:
        alternative = dict(occupancy, hov3=occ_value)
        tag = f"hov3occ{str(occ_value).replace('.', 'p')}"
        cube_alt = _person_volume(frame, "cube_vol_", alternative)
        tap_alt = _person_volume(frame, "tap_mod_vol_", alternative)
        out[f"cube_PMT_{tag}"] = vdf_math.vmt(cube_alt, length)
        out[f"cube_PHT_{tag}"] = vdf_math.vht(cube_alt, cube_time_min)
        out[f"taplite_PMT_{tag}"] = vdf_math.vmt(tap_alt, length)
        out[f"taplite_PHT_{tag}"] = vdf_math.vht(tap_alt, tap_time_min)

    return out


def _totals(measures: pd.DataFrame, mask=None) -> dict:
    frame = measures if mask is None else measures[mask]
    result = {}
    for side in SIDES:
        for measure in MEASURES:
            result[f"{side}_{measure}"] = float(frame[f"{side}_{measure}"].sum())
    return result


def build_rollup(measures: pd.DataFrame, corridor_column: pd.Series | None = None,
                 period: str = "am") -> pd.DataFrame:
    """Long-format rollup over every dimension, each reconciling to one total.

    A dimension that partitions the links (FTYPE, area type, jurisdiction,
    facility class) must sum to the network total exactly. ``residual_vs_network``
    is written on the TOTAL row of every dimension so "sums once" is demonstrated,
    not asserted.

    The ``mode`` dimension partitions *volume*, not links, and also sums to the
    network total because the six mode volumes sum to the link volume.

    The ``corridor`` dimension is deliberately NOT a partition -- most links belong
    to no named corridor -- so its residual is expected to be large and its TOTAL
    row is labelled accordingly.
    """
    network = _totals(measures)
    rows = []

    def emit(dimension, category, frame, is_partition=True, n_links=None):
        row = {
            "period": period,
            "dimension": dimension,
            "category": category,
            "n_links": int(len(frame)) if n_links is None else int(n_links),
            "is_partition": is_partition,
        }
        for side in SIDES:
            for measure in MEASURES:
                row[f"{side}_{measure}"] = float(frame[f"{side}_{measure}"].sum())
        for side in SIDES:
            vmt_total = row[f"{side}_VMT"]
            vht_total = row[f"{side}_VHT"]
            row[f"{side}_speed_mph"] = vdf_math.network_speed(vmt_total, vht_total)
        row["taplite_VMT_share_of_cube"] = (
            row["taplite_VMT"] / network["cube_VMT"] if network["cube_VMT"] else None
        )
        rows.append(row)

    def emit_dimension(name, series, is_partition=True):
        for category, group in measures.groupby(series, dropna=False):
            emit(name, str(category), group, is_partition)
        emit(name, "TOTAL", measures, is_partition)

    emit_dimension("network", pd.Series("all_links", index=measures.index))
    emit_dimension("facility_type", measures["ftype_label"].fillna("unknown"))
    area_type = measures["ATYPE_CODE"].astype(str).replace("<NA>", "unknown")
    emit_dimension("area_type_code", area_type)
    emit_dimension("jurisdiction", measures["JUR"].fillna("unknown"))
    emit_dimension(
        "facility_class",
        np.where(measures["is_connector"], "centroid connector", "road link"),
    )
    emit_dimension(
        "ft_x_at",
        measures["ftype_label"].fillna("unknown") + " | AT " + area_type,
    )
    emit_dimension(
        "special_use",
        np.select(
            [measures["is_closed"], measures["is_managed_lane"], measures["is_hov"]],
            ["closed", "managed lane (TOLLGRP>0)", "HOV"],
            default="general purpose",
        ),
    )

    # mode partitions volume rather than links
    for mode in MODES:
        cube_column = f"cube_VMT_{mode}"
        tap_column = f"taplite_VMT_{mode}"
        if cube_column not in measures.columns:
            continue
        rows.append({
            "period": period,
            "dimension": "mode",
            "category": mode,
            "n_links": int((measures[tap_column] > 0).sum()),
            "is_partition": True,
            "cube_VMT": float(measures[cube_column].sum()),
            "taplite_VMT": float(measures[tap_column].sum()),
            "cube_VHT": None, "cube_PMT": None, "cube_PHT": None,
            "taplite_VHT": None, "taplite_PMT": None, "taplite_PHT": None,
            "cube_speed_mph": None, "taplite_speed_mph": None,
            "taplite_VMT_share_of_cube": (
                float(measures[tap_column].sum()) / network["cube_VMT"]
                if network["cube_VMT"] else None
            ),
        })
    rows.append({
        "period": period, "dimension": "mode", "category": "TOTAL",
        "n_links": int(len(measures)), "is_partition": True,
        "cube_VMT": float(sum(measures[f"cube_VMT_{m}"].sum() for m in MODES
                              if f"cube_VMT_{m}" in measures.columns)),
        "taplite_VMT": float(sum(measures[f"taplite_VMT_{m}"].sum() for m in MODES
                                 if f"taplite_VMT_{m}" in measures.columns)),
        "cube_VHT": None, "cube_PMT": None, "cube_PHT": None,
        "taplite_VHT": None, "taplite_PMT": None, "taplite_PHT": None,
        "cube_speed_mph": None, "taplite_speed_mph": None,
        "taplite_VMT_share_of_cube": None,
    })

    if corridor_column is not None:
        named = measures[corridor_column.notna()]
        for category, group in named.groupby(corridor_column.dropna(), dropna=False):
            emit("corridor", str(category), group, is_partition=False)
        emit("corridor", "TOTAL (named corridors only, NOT a partition)",
             named, is_partition=False)

    table = pd.DataFrame(rows)

    # Reconciliation: on every TOTAL row of a partitioning dimension the residual
    # against the network total must be zero to floating-point noise.
    for side in SIDES:
        for measure in MEASURES:
            column = f"{side}_{measure}"
            reference = network[column]
            residual = table[column] - reference
            is_total = table["category"].str.startswith("TOTAL") & table["is_partition"]
            table[f"residual_{column}"] = np.where(is_total, residual, np.nan)
            # The plan's acceptance test is relative, at 1e-6.
            table[f"residual_rel_{column}"] = np.where(
                is_total & (reference != 0), residual / reference if reference else np.nan,
                np.nan,
            )
    residual_relative = [c for c in table.columns if c.startswith("residual_rel_")]
    table["reconciles_to_1e-6"] = np.where(
        table["category"].str.startswith("TOTAL") & table["is_partition"],
        table[residual_relative].abs().max(axis=1) <= 1e-6,
        np.nan,
    )
    return table


def build_network_speed(measures: pd.DataFrame, period: str,
                        run_label: str) -> pd.DataFrame:
    """Network speed the right way and the wrong way, side by side."""
    rows = []
    scopes = {
        "all_links": pd.Series(True, index=measures.index),
        "road_links_only": ~measures["is_connector"],
        "connectors_only": measures["is_connector"],
        "freeway_only": measures["ftype_label"] == "freeway",
    }
    for scope, mask in scopes.items():
        subset = measures[mask]
        for side in SIDES:
            total_vmt = float(subset[f"{side}_VMT"].sum())
            total_vht = float(subset[f"{side}_VHT"].sum())
            speeds = subset[f"{side}_speed_mph"]
            speeds = speeds[np.isfinite(speeds)]
            weighted = subset.loc[speeds.index, f"{side}_VMT"]
            rows.append({
                "period": period,
                "run": run_label,
                "source": side,
                "scope": scope,
                "n_links": int(len(subset)),
                "total_volume": float(subset[f"{side}_volume"].sum()),
                "total_VMT": total_vmt,
                "total_VHT": total_vht,
                "total_PMT": float(subset[f"{side}_PMT"].sum()),
                "total_PHT": float(subset[f"{side}_PHT"].sum()),
                "network_speed_mph_CORRECT_vmt_over_vht": vdf_math.network_speed(
                    total_vmt, total_vht
                ),
                "person_speed_mph_pmt_over_pht": vdf_math.network_speed(
                    float(subset[f"{side}_PMT"].sum()),
                    float(subset[f"{side}_PHT"].sum()),
                ),
                "mean_link_speed_mph_INCORRECT_do_not_use": (
                    float(speeds.mean()) if len(speeds) else None
                ),
                # VHT by the VMT/speed route. Identical to the travel_time route
                # except on the links where the kernel's speed_mph is snapped to a
                # QVDF anchor -- see the item 4 register. Published so the size of
                # that effect is visible rather than inferred.
                "total_VHT_from_speed_mph": (
                    float(subset["taplite_VHT_from_speed"].sum())
                    if side == "taplite" else None
                ),
                "VHT_two_route_delta": (
                    float(subset["taplite_VHT_delta_two_routes"].sum())
                    if side == "taplite" else None
                ),
                # hov3 occupancy is unsourced; both candidates are published so the
                # span is visible rather than hidden inside a single PMT number.
                **{
                    f"total_{measure}_hov3occ{str(occ).replace('.', 'p')}":
                        float(subset[f"{side}_{measure}_hov3occ"
                                     f"{str(occ).replace('.', 'p')}"].sum())
                    for occ in HOV3_OCCUPANCY_SENSITIVITY
                    for measure in ("PMT", "PHT")
                },
                "vmt_weighted_link_speed_mph_equals_correct": (
                    float(np.average(speeds, weights=weighted))
                    if len(speeds) and weighted.sum() > 0 else None
                ),
            })
    table = pd.DataFrame(rows)
    # The unweighted mean is published only so it is visibly wrong; quantify by how
    # much, so nobody has to work it out.
    table["mean_link_speed_error_mph"] = (
        table["mean_link_speed_mph_INCORRECT_do_not_use"]
        - table["network_speed_mph_CORRECT_vmt_over_vht"]
    )
    return table
