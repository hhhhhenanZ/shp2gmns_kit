"""Item 4 -- independent conical replay.

Three deliverables:

``item4_three_way.csv``          one row per link, Cube / independent / TAPlite
``item4_three_way_summary.csv``  the error distribution of each comparison
``item4_regression_ft_at.csv``   one row per populated FT x AT cell
``item4_missing_parameters.csv`` the zero-silent-fallback register

Why the independent calculation is evaluated **twice**. Cube and TAPlite assign
different volumes -- TAPlite re-runs the assignment, so its link volumes are its
own. Comparing "independent VDF" against both sides at a single volume would
confound two separate questions. Evaluated at Cube's volume it answers *does the
formula, with these parameters, reproduce Cube?* Evaluated at TAPlite's volume it
answers *does the kernel evaluate the formula correctly?* The second is the
stronger test and is the one that catches a unit or capacity-basis error inside the
kernel, which is the failure class the review is about.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import vdf_math
from .config import (
    ALPHA_INHERITED_CELLS,
    CONNECTOR_FTYPE,
    CONNECTOR_RULE,
    CUBE_FIELDS,
    DOCUMENTED_ATYPE_CODES,
    FTYPE_LABEL,
    CONIC_ALPHA,
    CONIC_ALPHA_BY_FT_AT,
    PERIOD_FACTOR,
    conic_alpha,
    spiess_beta,
)

# The comparisons the summary reports, as (column of absolute error, what it tests).
COMPARISONS = {
    "vdf_ratio_indep_vs_cube": "conical formula at Cube volume vs Cube travel-time ratio",
    "vc_indep_vs_cube": "recomputed V/C at Cube volume vs Cube V/C",
    "speed_indep_vs_cube": "conical speed at Cube volume vs Cube speed (mph)",
    "vdf_ratio_indep_vs_taplite": "conical formula at TAPlite volume vs kernel tt/fftt",
    "doc_indep_vs_taplite": "recomputed doc at TAPlite volume vs kernel doc",
    "speed_indep_vs_taplite": "conical speed at TAPlite volume vs kernel speed_mph",
    "volume_taplite_vs_cube": "TAPlite assigned volume vs Cube assigned volume (veh)",
}


def build_three_way(joined: pd.DataFrame, period: str, period_hours: float) -> pd.DataFrame:
    """Cube, independent-at-Cube-V, TAPlite, independent-at-TAPlite-V, per link."""
    frame = joined
    period_factor = PERIOD_FACTOR[period]
    out = pd.DataFrame(index=frame.index)

    # ---- keys and classification ----------------------------------------
    for column in ("link_id", "from_node_id", "to_node_id", "name", "FTYPE",
                   "ATYPE_CODE", "JUR", "TOLLGRP", "period_limit", "allowed_use"):
        out[column] = frame[column]
    out["ftype_label"] = frame["FTYPE"].map(FTYPE_LABEL)
    out["is_connector"] = frame["FTYPE"] == CONNECTOR_FTYPE

    # ---- parameters actually in the network ------------------------------
    out["lanes"] = frame["lanes"]
    out["lane_capacity"] = frame["capacity"]
    out["link_capacity"] = frame["capacity"] * frame["lanes"]
    out["vdf_type"] = frame["vdf_type"]
    out["vdf_alpha"] = frame["vdf_alpha"]
    out["vdf_beta"] = frame["vdf_beta"]
    out["vdf_plf"] = frame["vdf_plf"]
    out["vdf_fftt_min"] = frame["vdf_fftt"]
    out["vdf_free_speed_mph"] = frame["vdf_free_speed_mph"]
    out["length_mi"] = frame["vdf_length_mi"]
    out["period_factor_E"] = period_factor
    out["period_hours"] = period_hours

    # ---- Cube ------------------------------------------------------------
    out["cube_volume"] = frame["cube_vol"]
    out["cube_link_capacity"] = frame["cube_link_cap"]
    out["cube_lane_capacity"] = frame["cube_lane_cap"]
    out["cube_vc"] = frame["cube_vc"]
    out["cube_vdf_ratio"] = frame["cube_vdf"]
    out["cube_speed_mph"] = frame["cube_spd"]
    out["cube_free_speed_mph"] = frame["cube_ffspd"]
    out["cube_vmt"] = frame["cube_vmt"]

    # ---- independent, evaluated at Cube's volume -------------------------
    # x from Cube's own hourly link capacity and the period factor E -- this puts
    # the whole capacity chain under test, not just the VDF.
    x_cube = vdf_math.cube_vc(frame["cube_vol"], frame["cube_link_cap"], period_factor)
    ratio_cube = vdf_math.vdf_ratio(
        frame["vdf_type"], frame["vdf_alpha"], frame["vdf_beta"], x_cube
    )
    out["indep_at_cube_v_vc"] = x_cube
    out["indep_at_cube_v_vdf_ratio"] = ratio_cube
    out["indep_at_cube_v_travel_time_min"] = vdf_math.travel_time_min(
        frame["vdf_fftt"], ratio_cube
    )
    out["indep_at_cube_v_speed_mph"] = vdf_math.speed_mph(
        frame["vdf_free_speed_mph"], ratio_cube
    )

    # ---- TAPlite ---------------------------------------------------------
    out["taplite_volume"] = frame["tap_volume"]
    out["taplite_doc"] = frame["tap_doc"]
    out["taplite_fftt_min"] = frame["tap_vdf_fftt"]
    out["taplite_travel_time_min"] = frame["tap_travel_time"]
    out["taplite_speed_mph"] = frame["tap_speed_mph"]
    out["taplite_vmt"] = frame["tap_VMT"]
    out["taplite_vht"] = frame["tap_VHT"]
    # The ratio the kernel effectively applied, recovered from its own two columns.
    out["taplite_vdf_ratio"] = np.divide(
        frame["tap_travel_time"].to_numpy(dtype=float),
        frame["tap_vdf_fftt"].to_numpy(dtype=float),
        out=np.full(len(frame), np.nan),
        where=frame["tap_vdf_fftt"].to_numpy(dtype=float) > 0,
    )

    # ---- independent, evaluated at TAPlite's volume ----------------------
    x_tap = vdf_math.taplite_doc(
        frame["tap_volume"], frame["capacity"], frame["lanes"],
        frame["vdf_plf"], period_hours,
    )
    ratio_tap = vdf_math.vdf_ratio(
        frame["vdf_type"], frame["vdf_alpha"], frame["vdf_beta"], x_tap
    )
    out["indep_at_taplite_v_doc"] = x_tap
    out["indep_at_taplite_v_vdf_ratio"] = ratio_tap
    out["indep_at_taplite_v_travel_time_min"] = vdf_math.travel_time_min(
        frame["vdf_fftt"], ratio_tap
    )
    out["indep_at_taplite_v_speed_mph"] = vdf_math.speed_mph(
        frame["vdf_free_speed_mph"], ratio_tap
    )

    # ---- signed and absolute deltas --------------------------------------
    pairs = [
        ("vdf_ratio_indep_vs_cube", "indep_at_cube_v_vdf_ratio", "cube_vdf_ratio"),
        ("vc_indep_vs_cube", "indep_at_cube_v_vc", "cube_vc"),
        ("speed_indep_vs_cube", "indep_at_cube_v_speed_mph", "cube_speed_mph"),
        ("vdf_ratio_indep_vs_taplite", "indep_at_taplite_v_vdf_ratio", "taplite_vdf_ratio"),
        ("doc_indep_vs_taplite", "indep_at_taplite_v_doc", "taplite_doc"),
        ("speed_indep_vs_taplite", "indep_at_taplite_v_speed_mph", "taplite_speed_mph"),
        ("volume_taplite_vs_cube", "taplite_volume", "cube_volume"),
    ]
    for name, left, right in pairs:
        signed = out[left] - out[right]
        out[f"d_{name}"] = signed
        out[f"abs_{name}"] = signed.abs()

    out["ref_volume_echo_delta"] = frame["ref_volume_echo_delta"]
    return out


def summarise_three_way(three_way: pd.DataFrame) -> pd.DataFrame:
    """Error distribution per comparison, for all links and for road links only.

    Reported as a distribution rather than a pass/fail: no replay tolerance has
    been agreed, so the analysis states the error instead of judging it.
    """
    rows = []
    road = ~three_way["is_connector"]
    for name, description in COMPARISONS.items():
        for scope, mask in (("all_links", slice(None)), ("road_links_ftype_1_6", road)):
            values = three_way.loc[mask, f"abs_{name}"]
            stats = vdf_math.error_stats(values)
            signed = three_way.loc[mask, f"d_{name}"]
            signed = signed[np.isfinite(signed)]
            rows.append({
                "comparison": name,
                "tests": description,
                "scope": scope,
                "n": stats.get("n", 0),
                "median_abs_error": stats.get("median"),
                "p95_abs_error": stats.get("p95"),
                "p99_abs_error": stats.get("p99"),
                "max_abs_error": stats.get("max"),
                "share_within_0.001": stats.get("share_within_0.001"),
                "share_within_0.01": stats.get("share_within_0.01"),
                "share_within_0.1": stats.get("share_within_0.1"),
                "mean_signed_error": float(signed.mean()) if len(signed) else None,
                "share_positive": float((signed > 0).mean()) if len(signed) else None,
            })
    return pd.DataFrame(rows)


def conical_curvature(alpha, beta, x):
    """Second derivative of the conical ratio with respect to x.

    With u = 1 - x,  d2/dx2 [ 2 + sqrt(a^2 u^2 + b^2) - a u - b ]
                   = a^2 b^2 / (a^2 u^2 + b^2)^(3/2)

    Strictly positive: the conical function is convex everywhere, and its curvature
    peaks at x = 1. This is what makes the MSA hypothesis testable.
    """
    alpha = np.asarray(alpha, dtype=float)
    beta = np.asarray(beta, dtype=float)
    gap = 1.0 - np.asarray(x, dtype=float)
    return (alpha ** 2 * beta ** 2) / np.power(alpha ** 2 * gap ** 2 + beta ** 2, 1.5)


def build_residual_structure(three_way: pd.DataFrame) -> pd.DataFrame:
    """Test the MSA hypothesis for the Cube-vs-formula residual, before calling it error.

    The hypothesis: Cube reports an MSA-averaged VDF, i.e. a
    mean of per-iteration VDFs, against an MSA-averaged volume. Writing xbar for the
    reported V/C and Var(x) for the across-iteration spread, a second-order expansion
    of a convex function gives

        I4VDF  ~=  conical(xbar) + 0.5 * conical''(xbar) * Var(x)

    so the residual we measure, conical(xbar) - I4VDF, should be

        residual  ~=  -0.5 * conical''(xbar) * Var(x)

    Three predictions, all falsifiable with only Cube's stored output:

      1. SIGN      the residual is negative wherever curvature matters (Jensen --
                   the conical function is convex, so averaging inflates the VDF).
      2. SHAPE     |residual| tracks conical''(xbar), which peaks at V/C = 1 and
                   vanishes at low and very high V/C.
      3. SLOPE     regressing residual on curvature gives a negative slope whose
                   magnitude implies a plausible Var(x); the same slope should hold
                   across FTYPEs, since Var(x) is a property of the algorithm rather
                   than of the facility.

    Failing any of these would mean the tail is not MSA and has to be treated as
    error. The per-bin table below is the evidence; the regression rows carry the
    fitted slope and its R^2.
    """
    road = three_way[~three_way["is_connector"]].copy()
    road["curvature"] = conical_curvature(
        road["vdf_alpha"], road["vdf_beta"], road["indep_at_cube_v_vc"]
    )
    # residual as defined above: formula minus Cube
    road["residual"] = road["d_vdf_ratio_indep_vs_cube"]

    edges = [-np.inf, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2,
             1.4, np.inf]
    road["vc_bin"] = pd.cut(road["indep_at_cube_v_vc"], edges)

    rows = []
    for label, group in road.groupby("vc_bin", observed=True):
        residual = group["residual"]
        rows.append({
            "kind": "vc_bin",
            "vc_bin": str(label),
            "n_links": int(len(group)),
            "share_of_road_links": float(len(group) / len(road)),
            "mean_vc": float(group["indep_at_cube_v_vc"].mean()),
            "mean_curvature": float(group["curvature"].mean()),
            "mean_signed_residual": float(residual.mean()),
            "median_abs_residual": float(residual.abs().median()),
            "p95_abs_residual": float(residual.abs().quantile(0.95)),
            "share_negative": float((residual < 0).mean()),
            "share_abs_over_0.01": float((residual.abs() > 0.01).mean()),
            "implied_var_x": (
                float(-2.0 * residual.mean() / group["curvature"].mean())
                if group["curvature"].mean() > 0 else None
            ),
        })

    # Prediction 3: residual = slope * curvature, slope should be about -Var(x)/2.
    def regress(frame, label, kind):
        x = frame["curvature"].to_numpy(dtype=float)
        y = frame["residual"].to_numpy(dtype=float)
        keep = np.isfinite(x) & np.isfinite(y)
        x, y = x[keep], y[keep]
        if x.size < 10 or x.std() == 0:
            return None
        slope = float((x * y).sum() / (x * x).sum())   # through the origin
        predicted = slope * x
        ss_res = float(((y - predicted) ** 2).sum())
        ss_tot = float((y ** 2).sum())
        return {
            "kind": kind,
            "vc_bin": label,
            "n_links": int(x.size),
            "share_of_road_links": float(x.size / len(road)),
            "mean_vc": float(frame["indep_at_cube_v_vc"].mean()),
            "mean_curvature": float(x.mean()),
            "mean_signed_residual": float(y.mean()),
            "median_abs_residual": float(np.median(np.abs(y))),
            "p95_abs_residual": float(np.percentile(np.abs(y), 95)),
            "share_negative": float((y < 0).mean()),
            "share_abs_over_0.01": float((np.abs(y) > 0.01).mean()),
            "msa_slope": slope,
            "msa_implied_var_x": -2.0 * slope,
            "msa_r2_through_origin": 1.0 - ss_res / ss_tot if ss_tot > 0 else None,
        }

    overall = regress(road, "all road links", "msa_regression")
    if overall:
        rows.append(overall)
    for ftype, group in road.groupby("FTYPE"):
        fitted = regress(group, f"FTYPE {int(ftype)} ({FTYPE_LABEL.get(int(ftype))})",
                         "msa_regression_by_ftype")
        if fitted:
            rows.append(fitted)

    table = pd.DataFrame(rows)
    # A one-line verdict, so the reader does not have to assemble it from the rows.
    if overall:
        verdict_parts = []
        negative = float((road["residual"] < 0).mean())
        verdict_parts.append(
            f"sign: {negative:.1%} of road links have a negative residual "
            f"({'consistent' if negative > 0.8 else 'NOT consistent'} with Jensen)"
        )
        verdict_parts.append(
            f"slope: {overall['msa_slope']:.5f} "
            f"({'negative' if overall['msa_slope'] < 0 else 'POSITIVE - contradicts MSA'}), "
            f"R2={overall['msa_r2_through_origin']:.3f}, "
            f"implied Var(x)={overall['msa_implied_var_x']:.5f}"
        )
        table["msa_verdict"] = "; ".join(verdict_parts)
    return table


def build_regression_ft_at(three_way: pd.DataFrame) -> pd.DataFrame:
    """One row per populated FT x AT cell -- the committed regression baseline.

    This replaces the single link 3723->38488 named in the review, which does not
    exist in any period network. A stratified cell table is a strictly stronger
    check: it covers every combination the parameters are applied to rather than
    one arbitrary link, and it re-runs and diffs on any parameter change.
    """
    rows = []
    grouped = three_way.groupby(["FTYPE", "ATYPE_CODE"], dropna=False)
    for (ftype, atype), cell in grouped:
        stats_cube = vdf_math.error_stats(cell["abs_vdf_ratio_indep_vs_cube"])
        stats_tap = vdf_math.error_stats(cell["abs_vdf_ratio_indep_vs_taplite"])
        alpha = cell["vdf_alpha"].unique()
        beta = cell["vdf_beta"].unique()
        rows.append({
            "FTYPE": int(ftype),
            "ftype_label": FTYPE_LABEL.get(int(ftype), "unknown"),
            "ATYPE_CODE": int(atype) if pd.notna(atype) else None,
            "link_type": int(atype) * 100 + int(ftype) if pd.notna(atype) else None,
            "n_links": int(len(cell)),
            "vdf_type": int(cell["vdf_type"].iloc[0]),
            "alpha": float(alpha[0]) if len(alpha) == 1 else None,
            "beta": float(beta[0]) if len(beta) == 1 else None,
            "alpha_is_uniform_in_cell": bool(len(alpha) == 1),
            "mean_lane_capacity": float(cell["lane_capacity"].mean()),
            "mean_free_speed_mph": float(cell["vdf_free_speed_mph"].mean()),
            "cube_vc_median": float(cell["cube_vc"].median()),
            "cube_vc_p95": float(cell["cube_vc"].quantile(0.95)),
            "vs_cube_median_abs_err": stats_cube.get("median"),
            "vs_cube_p95_abs_err": stats_cube.get("p95"),
            "vs_cube_max_abs_err": stats_cube.get("max"),
            "vs_cube_share_within_0.01": stats_cube.get("share_within_0.01"),
            "vs_cube_share_within_0.1": stats_cube.get("share_within_0.1"),
            "vs_taplite_median_abs_err": stats_tap.get("median"),
            "vs_taplite_p95_abs_err": stats_tap.get("p95"),
            "vs_taplite_max_abs_err": stats_tap.get("max"),
            "vs_taplite_share_within_0.01": stats_tap.get("share_within_0.01"),
        })
    return pd.DataFrame(rows).sort_values(["FTYPE", "ATYPE_CODE"]).reset_index(drop=True)


def build_missing_parameters(joined: pd.DataFrame, three_way: pd.DataFrame,
                             period: str, period_hours: float) -> pd.DataFrame:
    """Zero-silent-fallback register.

    Every case where a parameter was substituted, defaulted, or is outside its
    documented domain. A *declared* substitution (the connector rule) is listed too,
    so the file is a complete account rather than only a list of problems --
    ``severity`` separates the two.
    """
    rows = []

    def record(case, severity, n_links, expected, detail):
        rows.append({
            "case": case,
            "severity": severity,
            "n_links": int(n_links),
            "expected": expected,
            "as_expected": (str(n_links) == str(expected)) if expected != "n/a" else None,
            "detail": detail,
        })

    connectors = joined["FTYPE"] == CONNECTOR_FTYPE
    record(
        "ftype_0_connector_rule_applied", "declared", connectors.sum(), "15986",
        f"vdf_type={CONNECTOR_RULE['vdf_type']}, vdf_alpha={CONNECTOR_RULE['vdf_alpha']}, "
        f"vdf_beta={CONNECTOR_RULE['vdf_beta']}; reproduces Cube {CUBE_FIELDS[period]['vdf']}==1 "
        "exactly. No conical (alpha,beta) can return 1.",
    )

    record(
        "conic_a_column_absent_alias_used", "declared",
        (~connectors).sum(), str(int((~connectors).sum())),
        "link.csv carries no conic_a/conic_b; the kernel reads vdf_alpha/vdf_beta as "
        "the conic a/b (TAPLite.cpp:7936). Deliberate, so no new column names appear.",
    )

    unknown_ftype = ~joined["FTYPE"].isin(list(CONIC_ALPHA) + [CONNECTOR_FTYPE])
    record("alpha_missing_for_ftype", "error", unknown_ftype.sum(), "0",
           f"FTYPE values with no conic alpha: {sorted(joined.loc[unknown_ftype, 'FTYPE'].unique())}")

    record("period_factor_missing", "error",
           0 if period in PERIOD_FACTOR else len(joined), "0",
           f"E({period}) = {PERIOD_FACTOR.get(period)}")

    # alpha/beta on road links must match the table exactly -- no rounding drift.
    # The lookup is on the (FTYPE, area type) cell, so this also verifies that the
    # link_type decode used at conversion time agrees with the one used here.
    road = joined[~connectors]
    expected_alpha = pd.Series(
        [conic_alpha(f, a)[0] for f, a in zip(road["FTYPE"], road["ATYPE_CODE"])],
        index=road.index, dtype=float,
    )
    alpha_bad = (road["vdf_alpha"] - expected_alpha).abs() > 1e-9
    record("alpha_differs_from_table", "error", alpha_bad.sum(), "0",
           "vdf_alpha in link.csv vs CONIC_ALPHA_BY_FT_AT[FTYPE][ATYPE]")

    inherited = pd.Series(
        [(int(f), int(a)) in ALPHA_INHERITED_CELLS
         for f, a in zip(road["FTYPE"], road["ATYPE_CODE"])],
        index=road.index,
    )
    record("alpha_inherited_from_pooled_ftype", "declared",
           inherited.sum(), str(int(inherited.sum())),
           "cells whose own links cannot determine alpha, so they carry the pooled "
           "facility-type value: "
           + "; ".join(f"FT {ft} AT {at} ({reason})"
                       for (ft, at), reason in ALPHA_INHERITED_CELLS.items()))

    cells_used = {(int(f), int(a)) for f, a in zip(road["FTYPE"], road["ATYPE_CODE"])}
    missing_cells = sorted(
        cell for cell in cells_used
        if cell[1] not in CONIC_ALPHA_BY_FT_AT.get(cell[0], {})
    )
    record("ft_at_cell_absent_from_table", "error", len(missing_cells), "0",
           f"cells present in the network but not in the alpha table: {missing_cells}"
           if missing_cells else
           f"all {len(cells_used)} populated road cells are in the table")
    expected_beta = expected_alpha.map(lambda a: spiess_beta(a) if pd.notna(a) else np.nan)
    beta_bad = (road["vdf_beta"] - expected_beta).abs() > 1e-9
    record("beta_differs_from_spiess", "error", beta_bad.sum(), "0",
           "vdf_beta vs (2a-1)/(2a-2)")

    # vdf_plf must equal E / H on every link, which is how the Cube period basis
    # reaches the kernel without a capacity_period column.
    expected_plf = PERIOD_FACTOR[period] / period_hours
    plf_bad = (joined["vdf_plf"] - expected_plf).abs() > 1e-6
    record("vdf_plf_differs_from_E_over_H", "error", plf_bad.sum(), "0",
           f"expected {expected_plf:.6f} = {PERIOD_FACTOR[period]} / {period_hours}")

    atype_undocumented = ~joined["ATYPE_CODE"].isin(DOCUMENTED_ATYPE_CODES)
    record("atype_code_outside_documented_range", "finding",
           atype_undocumented.sum(), "n/a",
           f"link_type//100 observed {sorted(joined['ATYPE_CODE'].dropna().unique().tolist())}; "
           f"region.yaml documents area types {DOCUMENTED_ATYPE_CODES}. Not remapped.")

    record("zero_lane_capacity_on_road_link", "error",
           ((road["capacity"] <= 0) | road["capacity"].isna()).sum(), "0",
           "lane capacity; a zero would make doc undefined")
    record("zero_lanes_on_road_link", "error",
           ((road["lanes"] <= 0) | road["lanes"].isna()).sum(), "0", "lanes")
    record("zero_free_flow_time", "error",
           ((joined["vdf_fftt"] <= 0) | joined["vdf_fftt"].isna()).sum(), "0",
           "vdf_fftt drives every travel time")
    record("zero_length", "finding",
           ((joined["vdf_length_mi"] <= 0) | joined["vdf_length_mi"].isna()).sum(), "n/a",
           "vdf_length_mi; zero-length links contribute no VMT")
    record("cube_volume_missing", "error", joined["cube_vol"].isna().sum(), "0",
           CUBE_FIELDS[period]["vol"])

    record("ref_volume_echo_mismatch", "error",
           (joined["ref_volume_echo_delta"] > 1e-4).sum(), "0",
           "link.csv ref_volume vs the kernel's echo in link_performance.csv; "
           "proves the kernel read the column the overlay wrote")

    missing_columns = joined.attrs.get("missing_performance_columns", [])
    record("link_performance_columns_absent", "finding", len(missing_columns), "n/a",
           f"requested but not emitted: {missing_columns}" if missing_columns
           else "all requested columns present")

    nan_ratio = three_way["taplite_vdf_ratio"].isna().sum()
    record("taplite_vdf_ratio_not_recoverable", "finding", nan_ratio, "n/a",
           "tt/fftt undefined because the kernel reported fftt <= 0")

    # The kernel's speed_mph column is not always length / travel_time. On a small
    # set of links it reports a value snapped to a 10-mph QVDF speed-profile anchor
    # while travel_time itself is correct and uncongested. Relative tolerance, not
    # absolute: travel_time is written to 4 decimals, so a tight absolute test would
    # flag ~2,000 links that are only output rounding.
    implied = np.divide(
        joined["vdf_length_mi"].to_numpy(dtype=float) * 60.0,
        joined["tap_travel_time"].to_numpy(dtype=float),
        out=np.full(len(joined), np.nan),
        where=joined["tap_travel_time"].to_numpy(dtype=float) > 0,
    )
    reported = joined["tap_speed_mph"].to_numpy(dtype=float)
    relative = np.abs(reported - implied) / np.where(implied > 0, implied, np.nan)
    inconsistent = np.nan_to_num(relative, nan=0.0) > 0.005
    record("kernel_speed_mph_inconsistent_with_travel_time", "finding",
           inconsistent.sum(), "n/a",
           "link_performance.csv speed_mph differs from length_mi*60/travel_time by "
           ">0.5%; the reported values are exact multiples of 10 mph (QVDF speed "
           "anchors) while travel_time is correct. Consequence: VHT must be computed "
           "as volume*travel_time/60, never as VMT/speed_mph. item5 reports both.")

    return pd.DataFrame(rows)
