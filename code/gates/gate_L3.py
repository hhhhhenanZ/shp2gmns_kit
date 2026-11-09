"""L3 Assignment -> 04_assignment/

Identity: VMT = sum_a v_a L_a; VHT = sum_a v_a t_a; t_a from the TAPLite VDF of 03_supply.
Number:   VMT, VHT, VHD by facility type, model / CMAP; relative gap and iterations.

Steps
  build      node.csv, link.csv, demand_<class>.csv, mode_type.csv, settings.csv and settings.yaml
             (the declared run settings: classes, memory limit, VDF, tolls, preload)
  run        TAPLite in 04_assignment/ (engine from region file > assignment > engine)
  summarize  L3_vmt_vht.csv from link_performance.csv; vehicles = sum of mod_vol_<class>;
             CMAP: v = DATA1 (ref_volume, vehicles), t = timau; VHD = sum v (t - t0), t0 = vdf_fftt
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from .common import folder, kit_path, load_region, record, worklog, write_csv

SCRIPT = "code/gates/gate_L3.py"


def build(region_file: Path, run_dir: Path, period: str) -> Path:
    cfg = load_region(region_file)
    a, p = cfg["assignment"], cfg["periods"][period]
    out = folder(run_dir, "assignment")
    shutil.copyfile(run_dir / "01_topology" / "node.csv", out / "node.csv")
    link = pd.read_csv(run_dir / "03_supply" / "link.csv", low_memory=False)
    mt = pd.read_csv(run_dir / "02_demand" / "mode_type.csv")
    merge = a.get("merge_classes") or {}
    merged = {m for ms in merge.values() for m in ms}
    rows, files = [], []
    for name, members in merge.items():            # merged classes: OD summed, allowed if all members allowed
        od = None
        for m in members:
            d = pd.read_csv(run_dir / "02_demand" / f"demand_{m}_{period}.csv").set_index(["o_zone_id", "d_zone_id"]).volume
            od = d if od is None else od.add(d, fill_value=0)
        f = out / f"demand_{name}.csv"
        od.rename("volume").reset_index().to_csv(f, index=False)
        files.append(f)
        sub = mt[mt.mode_type.isin(members)]
        rows.append({"mode_type": name, "name": " + ".join(members), "vot": sub.vot.max(),
                     "pce": float(sub.pce.iloc[0]), "occ": 1.0, "demand_file": f.name})
        allowed = link.allowed_use.fillna("").str.split(";")
        ok = allowed.apply(lambda u: all(m in u for m in members))
        link["allowed_use"] = [f"{name};{u}" if k else u for u, k in zip(link.allowed_use, ok)]
    for r in mt.itertuples():
        if r.mode_type in merged:
            continue
        f = out / f"demand_{r.mode_type}.csv"
        shutil.copyfile(run_dir / "02_demand" / r.demand_file, f)
        files.append(f)
        rows.append({"mode_type": r.mode_type, "name": r.name, "vot": r.vot, "pce": r.pce,
                     "occ": r.occ, "demand_file": f.name})
    m2 = pd.DataFrame(rows)
    m2.insert(0, "mode_type_id", range(1, len(m2) + 1))
    write_csv(m2, out / "mode_type.csv")
    write_csv(link, out / "link.csv")
    pd.DataFrame([{"number_of_iterations": a["iterations"], "number_of_processors": a["processors"],
                   "demand_period_starting_hours": p["start_hour"], "demand_period_ending_hours": p["end_hour"],
                   "first_through_node_id": a["first_through_node_id"], "base_demand_mode": 0,
                   "route_output": 0, "vehicle_output": 0, "log_file": 0, "odme_mode": 0,
                   "odme_vmt": 0, "demand_format": 0}]).to_csv(out / "settings.csv", index=False)
    declared = {
        "period": f"{period} {p['start_hour']}-{p['end_hour']} h",
        "classes": m2.mode_type.tolist(),
        "merged_classes": merge,
        "memory_limit_gb": a["memory_limit_gb"],
        "reason_for_merge": "8 classes need about 8.5 GB; limit is 8 GB. No tolls, same allowed links, pce 1: "
                            "link volumes unchanged; per-car-class volumes not produced.",
        "vdf": {k: cfg["taplite_vdf"][k] for k in ("form", "alpha", "beta", "plf", "fixed_time_codes")},
        "tolls": a["tolls"],
        "bus_preload": cfg["taplite_vdf"].get("bus_preload", "none"),
        "iterations": a["iterations"], "processors": a["processors"],
        "first_through_node_id": a["first_through_node_id"],
        "engine": a["engine"],
    }
    with open(out / "settings.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(declared, f, sort_keys=False, allow_unicode=True)
    names = ["node.csv", "link.csv", "mode_type.csv", "settings.csv", "settings.yaml"]
    record(run_dir, [out / n for n in names] + files, SCRIPT,
           "01_topology/node.csv; 03_supply/link.csv; 02_demand; region file assignment")
    worklog(run_dir, f"L3 build: {len(m2)} classes ({', '.join(m2.mode_type)})")
    return out


def run(region_file: Path, run_dir: Path, exe: Path | None = None) -> None:
    cfg = load_region(region_file)
    eng = kit_path(region_file, "../" + cfg["assignment"]["engine"]) if exe is None else exe
    if eng.is_dir():
        eng = eng / ("TAPLite_ftt.exe" if shutil.which("cmd") else "taplite")
    subprocess.run([str(eng)], cwd=folder(run_dir, "assignment"), check=True)


def summarize(region_file: Path, run_dir: Path, engine_note: str = "") -> Path:
    out = folder(run_dir, "assignment")
    lp = pd.read_csv(out / "link_performance.csv", low_memory=False)
    lk = pd.read_csv(out / "link.csv", low_memory=False)[["link_id", "vdf_code", "facility_type", "vdf_length_mi", "ref_time"]]
    lp = lp.merge(lk, on="link_id", how="left")
    veh = lp.filter(like="mod_vol_").sum(axis=1)
    L, t, t0 = lp.vdf_length_mi, lp.travel_time, lp.vdf_fftt
    v_c, t_c = lp.ref_volume, lp.ref_time
    lp = lp.assign(vmt=veh * L, vht=veh * t / 60, vhd=veh * (t - t0).clip(lower=0) / 60,
                   vmt_c=v_c * L, vht_c=v_c * t_c / 60, vhd_c=v_c * (t_c - t0).clip(lower=0) / 60)
    rows = []
    groups = [(c, lp.vdf_code == c) for c in sorted(lp.vdf_code.dropna().unique())]
    groups += [("road", lp.vdf_code != 6), ("all", lp.vdf_code.notna())]
    for c, sel in groups:
        g = lp[sel]
        r = {"vdf_code": c, "facility_type": g.facility_type.iloc[0] if c not in ("road", "all")
             else ("road links (no connectors)" if c == "road" else "all links"), "links": len(g)}
        for k in ("vmt", "vht", "vhd"):
            r[f"{k}_model"], r[f"{k}_cmap"] = round(g[k].sum()), round(g[k + "_c"].sum())
            r[f"{k}_ratio"] = round(g[k].sum() / g[k + "_c"].sum(), 3) if g[k + "_c"].sum() else ""
        x, y = veh[sel], v_c[sel]
        r["volume_r2"] = round(float(x.corr(y) ** 2), 3)
        r["volume_slope_through_0"] = round(float((x * y).sum() / (y * y).sum()), 3)
        rows.append(r)
    res = pd.DataFrame(rows)
    log = (out / "summary_log_file.txt").read_text(errors="ignore") if (out / "summary_log_file.txt").exists() else ""
    gaps = re.findall(r"iter No = (\d+).*?gap = ([\d.]+) %", log)
    res["iterations"] = int(gaps[-1][0]) if gaps else ""
    res["relative_gap_pct"] = float(gaps[-1][1]) if gaps else ""
    path = out / "L3_vmt_vht.csv"
    write_csv(res, path)
    outs = [out / n for n in ("link_performance.csv", "summary_log_file.txt") if (out / n).exists()]
    record(run_dir, outs, f"TAPLite {engine_note}".strip(), "04_assignment inputs and settings.csv")
    record(run_dir, [path], SCRIPT, "04_assignment/link_performance.csv, link.csv")
    road = res[res.vdf_code == "road"].iloc[0]
    worklog(run_dir, f"L3: road VMT {road.vmt_ratio}, VHT {road.vht_ratio}, VHD {road.vhd_ratio} x CMAP; "
                     f"volume R2 {road.volume_r2}; gap {res.relative_gap_pct.iloc[0]} %")
    return path


def engine_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:10]
