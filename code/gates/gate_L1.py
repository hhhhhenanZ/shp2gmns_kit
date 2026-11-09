"""L1 Demand -> 02_demand/L1_conservation.csv, L1_class_map.csv

Identity, per class and period:
    sum_j Q_ij = P_i,  sum_i Q_ij = A_j,  sum_ij Q_ij = source total.
Source Q = the agency trip tables in 00_raw, combined by the rule in the region file
(``demand > periods > <P> > tables``, CMAP ttables.mac). Written Q = 02_demand files.
Cells at or below ``demand > min_volume`` are not written (laptop memory and TAPLite run time).
So the check is: written + removed below threshold = source total, and P_i, A_j of the written
table = those of the source table with the below-threshold cells set to 0. A class passes when
nothing else is lost; the removed trips are reported, not hidden.
Number: removed trips and % by class; unexplained residual; external zones kept.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .common import KIT_ROOT, folder, load_region, record, worklog, write_csv
from .prepare import raw_location

sys.path.insert(0, str(KIT_ROOT / "code" / "src"))
from cmap_emme.demand import EmxReader, build_tables  # noqa: E402

SCRIPT = "code/gates/gate_L1.py"
TOL_PCT = 1e-3       # residual allowed, % of the class total (CSV rounding to 6 digits)


def run(region_file: Path, run_dir: Path, period: str) -> list[Path]:
    cfg = load_region(region_file)
    g, dcfg = cfg["gates"], cfg["demand"]
    dem = folder(run_dir, "demand")
    zones = int(dcfg["zones"])
    lo, hi = g["external_zones"]
    ext = np.zeros(zones, dtype=bool)
    ext[lo - 1:hi] = True
    emx = EmxReader(raw_location(run_dir, region_file, g["raw"]["demand_matrices"]), zones)
    tables, notes = build_tables(dcfg, period, emx)
    mt = pd.read_csv(dem / "mode_type.csv").set_index("mode_type")

    rows, cmap = [], []
    for m, src in tables.items():
        w = pd.read_csv(dem / f"demand_{m}_{period}.csv")
        o, d, v = w.o_zone_id.to_numpy() - 1, w.d_zone_id.to_numpy() - 1, w.volume.to_numpy()
        P_w = np.bincount(o, v, zones); A_w = np.bincount(d, v, zones)
        floor = float(dcfg["min_volume"])
        below = (src > 0) & (src <= floor)
        kept = np.where(src > floor, src, 0.0)
        P_s = kept.sum(axis=1); A_s = kept.sum(axis=0)
        tot_s, tot_w = float(src.sum()), float(v.sum())
        removed = float(src[below].sum())
        unexplained = tot_s - removed - tot_w
        res = 100 * unexplained / tot_s if tot_s else 0.0
        ext_s = int(((src.sum(axis=1) > 0) | (src.sum(axis=0) > 0))[ext].sum())
        ext_w = int(((P_w > 0) | (A_w > 0))[ext].sum())
        ext_trips_s = float(src[ext, :].sum() + src[:, ext].sum() - src[np.ix_(ext, ext)].sum())
        ext_trips_w = float(v[ext[o] | ext[d]].sum())
        rows.append({
            "period": period, "class": m, "threshold": floor,
            "source_total": round(tot_s, 1), "written_total": round(tot_w, 1),
            "removed_below_threshold": round(removed, 1),
            "removed_pct": round(100 * removed / tot_s, 2) if tot_s else 0.0,
            "unexplained_residual_pct": round(res, 5),
            "max_abs_P_residual": round(float(np.abs(P_w - P_s).max()), 4),
            "max_abs_A_residual": round(float(np.abs(A_w - A_s).max()), 4),
            "cells_positive_source": int((src > 0).sum()), "cells_below_threshold": int(below.sum()),
            "cells_written": int(len(w)), "negative_cells_source": int((src < 0).sum()),
            "external_zones_with_trips_source": ext_s, "external_zones_with_trips_written": ext_w,
            "external_trips_source": round(ext_trips_s, 1), "external_trips_written": round(ext_trips_w, 1),
            "pass": int(abs(res) <= TOL_PCT and ext_s == ext_w
                        and len(w) == int((src > floor).sum()) and not (src < 0).any()),
        })
        cmap.append({"class": m, "name": mt.loc[m, "name"], "cmap_rule": notes[m],
                     "pce": mt.loc[m, "pce"], "vot": mt.loc[m, "vot"], "occ": mt.loc[m, "occ"],
                     "demand_file": f"demand_{m}_{period}.csv"})
    out = pd.DataFrame(rows)
    S, W, Rm = out.source_total.sum(), out.written_total.sum(), out.removed_below_threshold.sum()
    tot = {"period": period, "class": "all", "threshold": float(dcfg["min_volume"]),
           "source_total": round(S, 1), "written_total": round(W, 1),
           "removed_below_threshold": round(Rm, 1), "removed_pct": round(100 * Rm / S, 2),
           "unexplained_residual_pct": round(100 * (S - Rm - W) / S, 5),
           "cells_positive_source": int(out.cells_positive_source.sum()),
           "cells_below_threshold": int(out.cells_below_threshold.sum()),
           "cells_written": int(out.cells_written.sum()), "pass": int(out["pass"].all())}
    out = pd.concat([out, pd.DataFrame([tot])], ignore_index=True)
    p1, p2 = dem / "L1_conservation.csv", dem / "L1_class_map.csv"
    write_csv(out, p1)
    write_csv(pd.DataFrame(cmap), p2)
    record(run_dir, [p1, p2], SCRIPT, "00_raw demand matrices (rule in region file); 02_demand files")
    worklog(run_dir, f"L1: source {tot['source_total']:,.1f}, written {tot['written_total']:,.1f}, "
                     f"removed below threshold {tot['removed_below_threshold']:,.1f}, "
                     f"unexplained {tot['unexplained_residual_pct']} %")
    return [p1, p2]
