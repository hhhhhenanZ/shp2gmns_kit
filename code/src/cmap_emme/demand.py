"""CMAP PM vehicle OD tables -> one TAPLite demand file per mode_type.

Built as CMAP's own ``Database/macros/ttables.mac`` builds the period tables [C], with the
factors in ``region.cmap.yaml > demand`` (= tod_factors.p1-p8 = [G] TOD conversion table).
Work plans: CMAP_model/CMAP_OD_workplan.md (PM), CMAP_OD_8periods_workplan.md (8 periods).

Output ``demand/<P>/<mode_type>_<P>.csv``: ``o_zone_id,d_zone_id,volume``. Zone ids are
CMAP zones 1-3649 (= centroid node_id). Volume = vehicles in the whole period (PM: 2 h).
Medium and heavy trucks are written in vehicles; CMAP's x2 / x3 vehicle equivalents go to
``pce`` in mode_type. Airport trips (mf10) are their own class ``apv`` here; CMAP folds
them into SOV. Cells at or below ``min_volume`` are not written and not rescaled: the kept
share per mode is in parameters/demand_summary.csv.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HEADER = ["o_zone_id", "d_zone_id", "volume"]


class EmxReader:
    def __init__(self, zip_path: Path, zones: int):
        self.zip = zipfile.ZipFile(zip_path)
        self.n = zones
        self.sizes: dict[str, int] = {}
        self.sums: dict[str, float] = {}

    def __call__(self, name: str) -> np.ndarray:
        # Read on every call and not kept, so one period fits in a few GB of memory.
        raw = self.zip.read(f"{name}.emx")   # one member at a time
        self.sizes[name] = len(raw)
        arr = np.frombuffer(raw, dtype="<f4")   # stored as float32, as in the .emx
        if arr.size != self.n * self.n:
            raise ValueError(f"{name}.emx has {arr.size} values, expected {self.n}^2")
        return arr.reshape(self.n, self.n).astype(np.float64)

    def total(self, name: str) -> float:
        if name not in self.sums:
            self.sums[name] = float(self(name).sum())
        return self.sums[name]


def flags(cfg: dict, n: int) -> np.ndarray:
    f = np.zeros(n)
    lo, hi = cfg["zone_flags"]["cbd"]
    f[lo - 1:hi] = 1
    for zone, value in cfg["zone_flags"]["airport"].items():
        f[int(zone) - 1] = value
    return f


def build_table(cfg: dict, period: str, mode: str, emx: EmxReader) -> tuple[np.ndarray, str]:
    pc = cfg["periods"][period]
    spec = pc["tables"][mode]
    if spec == "airport":
        a = pc["airport"]
        f = flags(cfg, emx.n)
        mat = emx(a["matrix"])
        to_air = (f[None, :] >= 2)
        from_air = (f[:, None] >= 2) & (f[None, :] == 0)
        table = mat * to_air * a["to_airport_factor"] + mat * from_air * a["from_airport_factor"]
        note = (f"{a['matrix']} x {a['to_airport_factor']} to airport zones + "
                f"x {a['from_airport_factor']} from airport zones to unflagged zones")
        return table, note
    return sum(emx(m) * float(k) for m, k in spec), " + ".join(f"{k} x {m}" for m, k in spec)


def build_tables(cfg: dict, period: str, emx: EmxReader) -> tuple[dict, dict]:
    tables, notes = {}, {}
    for mode in cfg["periods"][period]["tables"]:
        tables[mode], notes[mode] = build_table(cfg, period, mode, emx)
    return tables, notes


def vot_classes(cfg: dict, period: str) -> dict:
    """SOV VOT1-3 matrices of the period (mf41y, mf42y, mf43y) and their VOT."""
    return cfg["periods"][period].get("sov_vot_classes", cfg["sov_vot_classes"])


def sov_vot(cfg: dict, period: str, emx: EmxReader) -> float:
    pc = cfg["periods"][period]
    vots = vot_classes(cfg, period)
    split = cfg["external_vot_split"]
    ext = sum(emx.total(m) * float(k) for m, k in pc["tables"]["sov"] if m not in vots)
    weights = {m: emx.total(m) + ext * s for m, s in zip(vots, split)}
    return sum(weights[m] * vots[m] for m in vots) / sum(weights.values())


def write(cfg: dict, region, period: str, out: Path, bom: bool) -> dict:
    emx = EmxReader(region.path(cfg["emmemat_zip"]), int(cfg["zones"]))
    floor = float(cfg["min_volume"])
    folder = out / "demand" / period
    folder.mkdir(parents=True, exist_ok=True)
    rows, notes = [], {}
    for mode in cfg["periods"][period]["tables"]:   # one table in memory at a time
        mat, notes[mode] = build_table(cfg, period, mode, emx)
        keep = mat > floor
        o, d = np.nonzero(keep)
        frame = pd.DataFrame({"o_zone_id": o + 1, "d_zone_id": d + 1, "volume": mat[o, d]})
        path = folder / f"{mode}_{period}.csv"
        frame.to_csv(path, index=False, float_format="%.6g",
                     encoding="utf-8-sig" if bom else "utf-8")
        total, kept = float(mat.sum()), float(mat[keep].sum())
        rows.append({
            "mode_type": mode, "rule": notes[mode], "total_vehicles": round(total, 1),
            "cells_positive": int(np.count_nonzero(mat > 0)), "cells_written": int(keep.sum()),
            "vehicles_written": round(kept, 1), "share_kept": round(kept / total, 4) if total else 1.0,
            "vehicles_dropped": round(total - kept, 1),
            "intrazonal_vehicles": round(float(np.trace(mat)), 1), "file": str(path.relative_to(out)),
        })
        del mat, keep, o, d, frame
    summary = pd.DataFrame(rows)
    vot_sov = round(sov_vot(cfg, period, emx), 2)
    mode_types = []
    for i, m in enumerate(cfg["mode_types"], start=1):
        mode_types.append({"mode_type_id": i, "mode_type": m["mode_type"], "name": m["name"],
                           "vot": vot_sov if m["vot"] == "weighted" else m["vot"],
                           "pce": m["pce"], "occ": m["occ"],
                           "demand_file": f"{m['mode_type']}_{period}.csv"})
    pc = cfg["periods"][period]
    sov_model = sum(emx.total(m) for m in vot_classes(cfg, period))
    return {"summary": summary, "mode_types": pd.DataFrame(mode_types),
            "sizes": dict(emx.sizes), "floor": floor,
            "sov_demand_model_total": float(sov_model),
            "expected_sov_demand_model_total": float(pc["expected_sov_demand_model_total"])}
