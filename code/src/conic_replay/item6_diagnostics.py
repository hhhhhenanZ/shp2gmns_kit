"""Item 6 -- assignment diagnostics: convergence, runtime, corridors.

``item6_convergence.csv``  relative gap per iteration, per run
``item6_runtime.csv``      algorithm, stopping rule, processors, timings
``item6_corridors.csv``    named-corridor performance, Cube vs TAPlite

On the one-iteration run: the kernel emits no ``iter No =`` line at all, because a
relative gap needs a previous solution to compare against. ``item6_convergence.csv``
therefore carries a single explicit row for that run with a null gap and a stated
reason, rather than an empty section a reader would have to interpret. A
one-iteration all-or-nothing loading is also not a candidate solution -- it is the
starting point of the algorithm, and its network speed should be read that way.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import vdf_math
from .config import CORRIDORS

SIDES = ("cube", "taplite")


def assign_corridors(names: pd.Series) -> pd.Series:
    """Label each link with a named corridor, or NA.

    Patterns rather than exact names: one road can appear under several spellings
    (NVTA stores "I-495 - Capital Beltway" and "I-495 Capital Beltway"), and express lanes are a separate
    facility that must not be folded into the general-purpose lanes.
    """
    text = names.fillna("").astype(str)
    labels = pd.Series(pd.NA, index=names.index, dtype="object")
    for label, pattern in CORRIDORS:
        compiled = re.compile(pattern)
        match = text.str.match(compiled)
        labels = labels.where(labels.notna() | ~match, label)
    return labels


def build_convergence(runs: list) -> pd.DataFrame:
    """One row per (run, iteration). Runs that logged none get one explanatory row.

    ``relative_gap_pct`` is the kernel's own stored-path gap:
    ``(system TT - least-cost TT) / least-cost TT``. Both travel-time totals are
    carried so the gap can be recomputed rather than taken on trust.
    """
    rows = []
    for run in runs:
        log = run["log"]
        settings = run["settings"]
        base = {
            "config": run["config"],
            "period": run["period"],
            "run": run["label"],
            "iterations_requested": settings["_iterations"],
            "processors": settings["_processors"],
        }
        if not log["iterations"]:
            rows.append({
                **base,
                "iteration": None,
                "lambda": None,
                "system_vmt": None,
                "system_travel_time": None,
                "least_travel_time": None,
                "relative_gap_pct": None,
                "relative_gap_pct_recomputed": None,
                "cumulative_elapsed_sec": log["cpu_sec"],
                "iteration_elapsed_sec": None,
                "note": ("kernel logged no per-iteration gap: a relative gap needs a "
                         "previous solution, so a 1-iteration run emits none. The run "
                         "is an all-or-nothing free-flow loading, not a converged "
                         "assignment."),
            })
            continue
        for record in log["iterations"]:
            least = record["least_travel_time"]
            recomputed = (
                100.0 * (record["system_travel_time"] - least) / least
                if least else None
            )
            rows.append({
                **base,
                "iteration": record["iteration"],
                "lambda": record["lambda"],
                "system_vmt": record["system_vmt"],
                "system_travel_time": record["system_travel_time"],
                "least_travel_time": record["least_travel_time"],
                "relative_gap_pct": record["relative_gap_pct"],
                "relative_gap_pct_recomputed": recomputed,
                "cumulative_elapsed_sec": record["cumulative_elapsed_sec"],
                "iteration_elapsed_sec": record["iteration_elapsed_sec"],
                "note": "",
            })
    return pd.DataFrame(rows)


def build_runtime(runs: list) -> pd.DataFrame:
    """One row per run: what was asked for, what ran, and how long it took."""
    rows = []
    for run in runs:
        log = run["log"]
        settings = run["settings"]
        record = run["record"]
        iterations = log["iterations"]
        gaps = [i["relative_gap_pct"] for i in iterations]
        per_iteration = [i["iteration_elapsed_sec"] for i in iterations]
        kernel = record.get("kernel", {})
        rows.append({
            "config": run["config"],
            "period": run["period"],
            "run": run["label"],
            "algorithm": "Frank-Wolfe link-based TAP (predetermined step size)",
            "stopping_rule": (
                f"fixed iteration count = {settings['_iterations']}; "
                "no gap threshold is applied"
            ),
            "iterations_requested": settings["_iterations"],
            "iterations_logged": len(iterations),
            "number_of_processors": settings["_processors"],
            "period_hours": settings["_period_hours"],
            "nodes": log["nodes"],
            "zones": log["zones"],
            "links": log["links"],
            "setup_sec": log["setup_sec"],
            "cpu_sec": log["cpu_sec"],
            "elapsed_sec_from_run_record": record.get("elapsed_sec"),
            "wall_sec_from_run_record": record.get("wall_sec"),
            "mean_sec_per_iteration": float(np.mean(per_iteration)) if per_iteration else None,
            "max_sec_per_iteration": float(np.max(per_iteration)) if per_iteration else None,
            "first_gap_pct": gaps[0] if gaps else None,
            "final_gap_pct": gaps[-1] if gaps else None,
            "min_gap_pct": min(gaps) if gaps else None,
            "gap_is_monotone": bool(all(b <= a for a, b in zip(gaps, gaps[1:]))) if len(gaps) > 1 else None,
            # The plan expected a stored-path gap and a fresh-shortest-path gap.
            # This kernel build emits one only; summary_log_file.txt and
            # dtalite_run.log carry the same series at different precision. Rather
            # than leave a blank column, the gap is recomputed independently from
            # the kernel's own sys.TT and least-TT (item6_convergence.csv,
            # relative_gap_pct_recomputed) as a check on the reported figure.
            "gap_measures_emitted": 1,
            "gap_definition": "(system TT - least-cost TT) / least-cost TT, stored paths",
            "second_gap_available": False,
            "total_demand_loaded": float(sum(log["loaded_mode_volume"].values())),
            "kernel_distribution": kernel.get("distribution"),
            "kernel_version": kernel.get("installed_version"),
            "kernel_native_sha256": kernel.get("native_sha256"),
        })
    return pd.DataFrame(rows)


def build_corridors(measures_by_run: dict) -> pd.DataFrame:
    """Corridor performance, one row per (corridor, run), Cube beside TAPlite.

    Aggregation is VMT-weighted where a weighted quantity is meant: corridor speed
    is corridor VMT / corridor VHT, never a mean of link speeds. V/C is reported as
    a VMT-weighted mean, which is the only sensible way to state a corridor-level
    ratio across links of different length and capacity.
    """
    rows = []
    for (config, period, label), measures in measures_by_run.items():
        corridor = assign_corridors(measures["name"])
        frame = measures.assign(corridor=corridor)
        frame = frame[frame["corridor"].notna()]
        for name, group in frame.groupby("corridor"):
            row = {
                "config": config,
                "period": period,
                "run": label,
                "corridor": name,
                "n_links": int(len(group)),
                "directional_miles": float(group["length_mi"].sum()),
                "lane_miles": float((group["length_mi"] * group["lanes"]).sum()),
                "ftype_mix": ", ".join(
                    f"{k}:{v}" for k, v in
                    group["ftype_label"].value_counts().head(3).items()
                ),
                "is_managed_lane": bool(group["is_managed_lane"].any()),
                "is_hov": bool(group["is_hov"].any()),
                "is_closed_any": bool(group["is_closed"].any()),
                "n_closed_links": int(group["is_closed"].sum()),
            }
            for side in SIDES:
                total_vmt = float(group[f"{side}_VMT"].sum())
                total_vht = float(group[f"{side}_VHT"].sum())
                weights = group[f"{side}_VMT"]
                row[f"{side}_volume"] = float(group[f"{side}_volume"].sum())
                row[f"{side}_VMT"] = total_vmt
                row[f"{side}_VHT"] = total_vht
                row[f"{side}_PMT"] = float(group[f"{side}_PMT"].sum())
                row[f"{side}_PHT"] = float(group[f"{side}_PHT"].sum())
                row[f"{side}_speed_mph"] = vdf_math.network_speed(total_vmt, total_vht)
                row[f"{side}_travel_time_min"] = float(
                    group[f"{side}_travel_time_min"].sum()
                )
                row[f"{side}_free_flow_speed_mph"] = (
                    float(np.average(group["cube_free_speed_mph"], weights=weights))
                    if weights.sum() > 0 and "cube_free_speed_mph" in group else None
                )
            row["taplite_minus_cube_volume"] = row["taplite_volume"] - row["cube_volume"]
            row["taplite_over_cube_VMT"] = (
                row["taplite_VMT"] / row["cube_VMT"] if row["cube_VMT"] else None
            )
            row["taplite_minus_cube_speed_mph"] = (
                row["taplite_speed_mph"] - row["cube_speed_mph"]
            )
            rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    return table.sort_values(["corridor", "period", "run"]).reset_index(drop=True)


def build_corridor_vc(joined_by_run: dict) -> pd.DataFrame:
    """Corridor V/C, kept separate because it needs the item-4 join, not measures."""
    rows = []
    for (config, period, label), joined in joined_by_run.items():
        corridor = assign_corridors(joined["name"])
        frame = joined.assign(corridor=corridor)
        frame = frame[frame["corridor"].notna()]
        for name, group in frame.groupby("corridor"):
            vmt = group["cube_vol"] * group["vdf_length_mi"]
            tap_vmt = group["tap_volume"] * group["vdf_length_mi"]
            rows.append({
                "config": config, "period": period, "run": label, "corridor": name,
                "n_links": int(len(group)),
                "cube_vc_vmt_weighted": (
                    float(np.average(group["cube_vc"], weights=vmt))
                    if vmt.sum() > 0 else None),
                "cube_vc_max": float(group["cube_vc"].max()),
                "cube_share_over_capacity": float((group["cube_vc"] > 1.0).mean()),
                "taplite_doc_vmt_weighted": (
                    float(np.average(group["tap_doc"], weights=tap_vmt))
                    if tap_vmt.sum() > 0 else None),
                "taplite_doc_max": float(group["tap_doc"].max()),
                "taplite_share_over_capacity": float((group["tap_doc"] > 1.0).mean()),
            })
    return pd.DataFrame(rows)
