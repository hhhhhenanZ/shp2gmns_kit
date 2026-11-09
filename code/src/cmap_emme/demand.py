"""CMAP PM vehicle OD tables -> one TAPLite demand file per mode_type.

Built as CMAP's own ``Database/macros/ttables.mac`` builds the period tables [C], with the
factors in ``region.cmap.yaml > demand`` (= tod_factors.p7 = [G] TOD conversion table).
Work plan: CMAP_model/CMAP_OD_workplan.md.

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
        self.cache: dict[str, np.ndarray] = {}
        self.sizes: dict[str, int] = {}

    def __call__(self, name: str) -> np.ndarray:
        if name not in self.cache:
            raw = self.zip.read(f"{name}.emx")   # one member at a time
            self.sizes[name] = len(raw)
            arr = np.frombuffer(raw, dtype="<f4")
            if arr.size != self.n * self.n:
                raise ValueError(f"{name}.emx has {arr.size} values, expected {self.n}^2")
            self.cache[name] = arr.reshape(self.n, self.n)   # stored as float32, as in the .emx
        return self.cache[name].astype(np.float64)


def flags(cfg: dict, n: int) -> np.ndarray:
    f = np.zeros(n)
    lo, hi = cfg["zone_flags"]["cbd"]
    f[lo - 1:hi] = 1
    for zone, value in cfg["zone_flags"]["airport"].items():
        f[int(zone) - 1] = value
    return f


def build_tables(cfg: dict, period: str, emx: EmxReader) -> tuple[dict, dict]:
    pc = cfg["periods"][period]
    tables, notes = {}, {}
    for mode, spec in pc["tables"].items():
        if spec == "airport":
            a = pc["airport"]
            f = flags(cfg, emx.n)
            mat = emx(a["matrix"])
            to_air = (f[None, :] >= 2)
            from_air = (f[:, None] >= 2) & (f[None, :] == 0)
            tables[mode] = mat * to_air * a["to_airport_factor"] + mat * from_air * a["from_airport_factor"]
            notes[mode] = (f"{a['matrix']} x {a['to_airport_factor']} to airport zones + "
                           f"x {a['from_airport_factor']} from airport zones to unflagged zones")
        else:
            tables[mode] = sum(emx(m) * float(k) for m, k in spec)
            notes[mode] = " + ".join(f"{k} x {m}" for m, k in spec)
    return tables, notes


def sov_vot(cfg: dict, period: str, emx: EmxReader) -> float:
    pc = cfg["periods"][period]
    vots = cfg["sov_vot_classes"]
    split = cfg["external_vot_split"]
    ext = sum(emx(m).sum() * float(k) for m, k in pc["tables"]["sov"] if m not in vots)
    weights = {m: emx(m).sum() + ext * s for m, s in zip(vots, split)}
    return sum(weights[m] * vots[m] for m in vots) / sum(weights.values())


def write(cfg: dict, region, period: str, out: Path, bom: bool) -> dict:
    emx = EmxReader(region.path(cfg["emmemat_zip"]), int(cfg["zones"]))
    floor = float(cfg["min_volume"])
    tables, notes = build_tables(cfg, period, emx)
    folder = out / "demand" / period
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for mode, mat in tables.items():
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
    summary = pd.DataFrame(rows)
    vot_sov = round(sov_vot(cfg, period, emx), 2)
    mode_types = []
    for i, m in enumerate(cfg["mode_types"], start=1):
        mode_types.append({"mode_type_id": i, "mode_type": m["mode_type"], "name": m["name"],
                           "vot": vot_sov if m["vot"] == "weighted" else m["vot"],
                           "pce": m["pce"], "occ": m["occ"],
                           "demand_file": f"{m['mode_type']}_{period}.csv"})
    pc = cfg["periods"][period]
    sov_model = sum(emx(m).sum() for m in cfg["sov_vot_classes"])
    return {"summary": summary, "mode_types": pd.DataFrame(mode_types),
            "sizes": dict(emx.sizes), "floor": floor,
            "sov_demand_model_total": float(sov_model),
            "expected_sov_demand_model_total": float(pc["expected_sov_demand_model_total"])}
