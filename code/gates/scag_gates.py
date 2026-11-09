"""SCAG (TransCAD) gate steps: raw, publish, L0, L1, L2.  Region file: region.yaml > gates.

Paths in region.yaml are relative to --data-root, the SCAG kit folder that holds data/input
and data/output. The network and demand of the run folder come from the conversion in
data/output (main_convert.py on region.yaml); L0 and L1 check them against SCAG's raw files.
Long steps (sha256 of the raw files, L0 reachability, L1 reading the 1.6 GB OD file) keep
their progress in _work/ and return False when the time budget runs out: run them again.
"""

from __future__ import annotations

import io
import json
import shutil
import struct
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .common import folder, load_region, record, sha256, worklog, write_csv
from .gate_L0 import reach

SCRIPT = "code/gates/scag_gates.py"
CONVERSION_OVERRIDE = None   # set by run_gates.py --conversion


def _conv(g: dict) -> str:
    return CONVERSION_OVERRIDE or g["conversion"]


def _p(root: Path, rel: str) -> Path:
    return (root / rel).resolve()


# ---------------------------------------------------------------- raw
def step_raw(region_file: Path, root: Path, run: Path, budget: float = 140) -> bool:
    t0 = time.time()
    g = load_region(region_file)["gates"]
    work = folder(run, "work")
    cache_f = work / "sha_cache.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    rows, done = [], True
    for role, e in g["raw"].items():
        src = _p(root, e["file"])
        key = f"{src}|{src.stat().st_size}|{int(src.stat().st_mtime)}"
        if key not in cache:
            if time.time() - t0 > budget:
                done = False
                break
            cache[key] = sha256(src)
            cache_f.write_text(json.dumps(cache))
        rows.append({"role": role, "file": src.name, "original_path": e["file"],
                     "bytes": src.stat().st_size, "sha256": cache[key], "source": "SCAG"})
    if done:
        write_csv(pd.DataFrame(rows), folder(run, "raw") / "EXTERNAL.csv")
        worklog(run, "raw: SCAG files listed in 00_raw/EXTERNAL.csv with sha256 (read in place)")
    return done


# ---------------------------------------------------------------- publish
def step_publish(region_file: Path, root: Path, run: Path, period: str) -> None:
    g = load_region(region_file)["gates"]
    conv = _p(root, _conv(g))
    topo, dem = folder(run, "topology"), folder(run, "demand")
    src_note = f"{_conv(g)} (main_convert.py on region.yaml; CONVERT_MANIFEST.json; zone nodes split in stage 4b)"
    for n in ("node.csv", "link.csv"):
        s_, d = conv / "network" / period / n, topo / n
        if not d.exists() or d.stat().st_size != s_.stat().st_size:
            shutil.copyfile(s_, d)
    if (conv / "network" / "zone_split.csv").exists():
        shutil.copyfile(conv / "network" / "zone_split.csv", topo / "zone_split.csv")
    zc = pd.read_csv(conv / "parameters" / "zone_centroids.csv", encoding="utf-8-sig")
    z = zc[["zone_id", "taz_id", "node_id", "zone_type", "x_coord", "y_coord"]].copy()
    z["external"] = (z.zone_type == "external").astype(int)
    write_csv(z, topo / "zone.csv")
    record(run, [topo / n for n in ("node.csv", "link.csv", "zone.csv", "zone_split.csv") if (topo / n).exists()], SCRIPT, src_note)
    mt = pd.read_csv(conv / "parameters" / "mode_type_by_period.csv", encoding="utf-8-sig")
    mt = mt[mt.period == period].drop(columns="period").copy()
    outs = []
    dsrc = _p(root, g.get("demand_from", g["conversion"]))
    for m in mt.mode_type:
        s, d = dsrc / "demand" / period / f"{m}_{period}.csv", dem / f"demand_{m}_{period}.csv"
        if not d.exists() or d.stat().st_size != s.stat().st_size:
            shutil.copyfile(s, d)
        outs.append(d)
    mt["demand_file"] = [f"demand_{m}_{period}.csv" for m in mt.mode_type]
    write_csv(mt, dem / "mode_type.csv")
    record(run, outs + [dem / "mode_type.csv"], SCRIPT,
           f"{g.get('demand_from', g['conversion'])} (main_convert.py demand stage, 2026-09-26)")
    worklog(run, f"publish: SCAG {period} network and demand from {_conv(g)}")


# ---------------------------------------------------------------- L0
def _dbf_column(path: Path, name: str) -> tuple[int, np.ndarray]:
    with open(path, "rb") as f:
        head = f.read(32)
        n, hl, rl = struct.unpack("<IHH", head[4:12])
        fields, off = [], 1
        while True:
            d = f.read(32)
            if d[0] == 0x0D:
                break
            fields.append((d[:11].split(b"\0")[0].decode(), off, d[16]))
            off += d[16]
        if name is None:
            return n, np.array([])
        fo = [(o, w) for nm, o, w in fields if nm.upper() == name.upper()][0]
        f.seek(hl)
        raw = np.frombuffer(f.read(n * rl), dtype=np.uint8).reshape(n, rl)
    col = raw[:, fo[0]:fo[0] + fo[1]].tobytes()
    vals = [col[i * fo[1]:(i + 1) * fo[1]].strip() for i in range(n)]
    return n, np.array([float(v) if v else np.nan for v in vals])


def step_L0(region_file: Path, root: Path, run: Path, period: str, budget: float = 60) -> bool:
    t0 = time.time()
    g = load_region(region_file)["gates"]
    topo, dem, work = folder(run, "topology"), folder(run, "demand"), folder(run, "work")
    node = pd.read_csv(topo / "node.csv", encoding="utf-8-sig")
    link = pd.read_csv(topo / "link.csv", encoding="utf-8-sig", low_memory=False,
                       usecols=["link_id", "from_node_id", "to_node_id", "allowed_use"])
    zone = pd.read_csv(topo / "zone.csv")
    mt = pd.read_csv(dem / "mode_type.csv")
    ids = node.node_id.to_numpy()
    idx = pd.Series(np.arange(len(ids)), index=ids)
    frm, to = idx[link.from_node_id].to_numpy(), idx[link.to_node_id].to_numpy()
    zn = idx[zone.node_id].to_numpy()
    centroid = np.zeros(len(ids), bool)
    centroid[zn] = True
    allowed = link.allowed_use.fillna("").str.split(";")
    masks = {"all": np.ones(len(link), bool)}
    for m in mt.mode_type:
        masks[m] = allowed.apply(lambda u: m in u).to_numpy()
    done = True
    for key, mask in masks.items():
        f = work / f"L0_reach_{key}_{len(link)}.npy"
        if f.exists():
            continue
        same = [k for k in masks if k != key and (masks[k] == mask).all() and (work / f"L0_reach_{k}_{len(link)}.npy").exists()]
        if same:
            tmp = f.with_suffix(".tmp.npy")
            shutil.copyfile(work / f"L0_reach_{same[0]}_{len(link)}.npy", tmp)
            tmp.replace(f)
            continue
        if time.time() - t0 > budget:
            done = False
            break
        tmp = f.with_suffix(".tmp.npy")
        np.save(tmp, reach(len(ids), zn, frm[mask], to[mask], centroid))
        tmp.replace(f)                     # atomic: a stopped run leaves no half-written file
    if not done:
        print("  L0: reachability not finished; run the L0 step again")
        return False

    conv = _p(root, _conv(g))
    n_lines, dirs = _dbf_column(_p(root, g["raw"]["network_dbf"]["file"]), "DIR")
    expected = int(np.where(dirs == 0, 2, 1).sum())
    excluded = len(pd.read_csv(conv / "network" / "link_excluded.csv", encoding="utf-8-sig"))
    split_f = topo / "zone_split.csv"
    added = int(pd.read_csv(split_f).connectors_added.sum()) if split_f.exists() else 0
    n_taz, _ = _dbf_column(_p(root, g["raw"]["taz_t1_dbf"]["file"]), None)
    rows = [
        {"item": "raw network lines", "class": "all", "value": n_lines, "reference": "", "identity": "records in the SCAG loaded network .dbf"},
        {"item": "directed links written - split connectors + excluded", "class": "all", "value": len(link) - added + excluded, "reference": expected,
         "identity": "= lines x 2 where DIR = 0, else x 1 (link_excluded.csv: Tier-2 connectors and non-highway links; zone_split.csv: 2 connectors per split zone)"},
        {"item": "zone nodes split off the road network", "class": "all", "value": added // 2, "reference": "", "identity": "zone_split.csv"},
        {"item": "links written", "class": "all", "value": len(link), "reference": "", "identity": "link.csv rows"},
        {"item": "nodes", "class": "all", "value": len(node), "reference": "", "identity": "node.csv rows (line end points + zone centroids)"},
        {"item": "zones", "class": "all", "value": len(zone), "reference": "", "identity": "zone.csv rows: internal + external + seaport + airport"},
        {"item": "internal zones", "class": "all", "value": int((zone.zone_type == "internal").sum()), "reference": n_taz,
         "identity": "= records in T1TAZ_24RTP.dbf (Tier-1 zone polygons)"},
        {"item": "external zones", "class": "all", "value": int(zone.external.sum()), "reference": "", "identity": "zone_type = external"},
    ]
    r_all = np.load(work / f"L0_reach_all_{len(link)}.npy")
    np.fill_diagonal(r_all, True)
    off = ~np.eye(len(r_all), dtype=bool)
    bad = ~(r_all & off).any(axis=1) | ~(r_all & off).any(axis=0)
    rows.append({"item": "disconnected zones", "class": "all", "value": int(bad.sum()), "reference": 0,
                 "identity": "disconnected zones = 0 (a zone that reaches no other zone, or that no other zone reaches)"})
    weak = ((r_all & off).mean(axis=1) < 0.5) | ((r_all & off).mean(axis=0) < 0.5)
    rows.append({"item": "zones reaching or reached by fewer than half of the zones", "class": "all",
                 "value": int(weak.sum()), "reference": 0, "identity": "= 0; listed in L0_disconnected_zones.csv"})
    bad = bad | weak
    if bad.any():
        write_csv(zone[bad][["zone_id", "taz_id", "node_id", "zone_type"]].assign(
            share_of_zones_it_reaches=(r_all & off).mean(axis=1)[bad].round(4),
            share_of_zones_reaching_it=(r_all & off).mean(axis=0)[bad].round(4)),
            topo / "L0_disconnected_zones.csv")
    zpos = pd.Series(np.arange(len(zone)), index=zone.zone_id.to_numpy())
    for m in mt.mode_type:
        r = np.load(work / f"L0_reach_{m}_{len(link)}.npy")
        d = pd.read_csv(dem / f"demand_{m}_{period}.csv", encoding="utf-8-sig")
        d = d[d.volume > 0]
        o, t = zpos[d.o_zone_id].to_numpy(), zpos[d.d_zone_id].to_numpy()
        un = ~r[o, t] & (o != t)
        rows += [
            {"item": "positive-demand OD pairs", "class": m, "value": int(len(d)), "reference": "", "identity": f"rows of demand_{m}_{period}.csv"},
            {"item": "unreachable positive-demand OD pairs", "class": m, "value": int(un.sum()), "reference": 0,
             "identity": f"= 0 on links allowing {m}, no path through other centroids"},
            {"item": "unreachable trips", "class": m, "value": round(float(d.volume[un].sum()), 3), "reference": 0, "identity": "= 0"},
        ]
    out = pd.DataFrame(rows)
    out.insert(0, "period", period)
    out["value"] = pd.Series([int(v) if float(v).is_integer() else v for v in out.value], dtype=object)
    out["pass"] = [("" if r == "" else int(v == r)) for v, r in zip(out.value, out.reference)]
    path = topo / "L0_counts.csv"
    write_csv(out, path)
    extra = [topo / "L0_disconnected_zones.csv"] if bad.any() else []
    record(run, [path] + extra, SCRIPT, "01_topology; 02_demand; SCAG .dbf files (00_raw/EXTERNAL.csv)")
    worklog(run, f"L0: {int(bad.sum())} disconnected zones")
    return True


# ---------------------------------------------------------------- L1
def step_L1(region_file: Path, root: Path, run: Path, period: str, budget: float = 140) -> bool:
    t0 = time.time()
    cfg = load_region(region_file)
    g = cfg["gates"]
    floor = float(cfg["demand"]["min_volume"])
    dem, topo, work = folder(run, "demand"), folder(run, "topology"), folder(run, "work")
    zone = pd.read_csv(topo / "zone.csv")
    nz = int(zone.zone_id.max())
    taz2zone = dict(zip(zone.taz_id, zone.zone_id))
    cores = g["od_cores"]
    k = len(cores)
    st = work / "L1_state.npz"
    if st.exists():
        s = dict(np.load(st))
        off = int(s["offset"])
    else:
        s = {"tot": np.zeros(k), "pos": np.zeros(k), "below": np.zeros(k), "nbelow": np.zeros(k),
             "P": np.zeros((k, nz + 1)), "A": np.zeros((k, nz + 1)), "unmapped": np.zeros(k), "neg": np.zeros(k)}
        off = 0
    od = _p(root, g["raw"]["od_am"]["file"])
    size = od.stat().st_size
    tail = b""
    with open(od, "rb") as f:
        f.seek(off)
        while off < size:
            if time.time() - t0 > budget:
                break
            blk = f.read(1 << 27)
            if not blk:
                break
            cut = blk.rfind(b"\n") + 1 if off + len(blk) < size else len(blk)
            data, nxt = blk[:cut], off + cut
            f.seek(nxt)
            x = pd.read_csv(io.BytesIO(data), header=None).to_numpy(float)
            zo = pd.Series(x[:, 0]).map(taz2zone).to_numpy()
            zd = pd.Series(x[:, 1]).map(taz2zone).to_numpy()
            ok = ~(np.isnan(zo) | np.isnan(zd))
            for c in range(k):
                v = x[:, 2 + c]
                s["tot"][c] += v.sum()
                s["neg"][c] += (v < 0).sum()
                s["pos"][c] += (v > 0).sum()
                b = (v > 0) & (v <= floor)
                s["below"][c] += v[b].sum()
                s["nbelow"][c] += b.sum()
                s["unmapped"][c] += v[~ok].sum()
                keep = ok & (v > floor)
                s["P"][c] += np.bincount(zo[keep].astype(int), v[keep], nz + 1)
                s["A"][c] += np.bincount(zd[keep].astype(int), v[keep], nz + 1)
            off = nxt
    s["offset"] = np.array(off)
    np.savez(st, **s)
    if off < size:
        print(f"  L1: read {off / size:.0%} of the OD file; run the L1 step again")
        return False

    ext = np.zeros(nz + 1, bool)
    ext[zone.zone_id[zone.external == 1].to_numpy()] = True
    rows, cmap = [], []
    for c, m in enumerate(cores):
        w = pd.read_csv(dem / f"demand_{m}_{period}.csv", encoding="utf-8-sig")
        o, d, v = w.o_zone_id.to_numpy(), w.d_zone_id.to_numpy(), w.volume.to_numpy()
        Pw, Aw = np.bincount(o, v, nz + 1), np.bincount(d, v, nz + 1)
        tot, wr, rm = s["tot"][c], v.sum(), s["below"][c]
        unexpl = tot - rm - s["unmapped"][c] - wr
        res = 100 * unexpl / tot if tot else 0.0
        ext_s = int(((s["P"][c] > 0) | (s["A"][c] > 0))[ext].sum())
        ext_w = int(((Pw > 0) | (Aw > 0))[ext].sum())
        rows.append({
            "period": period, "class": m, "threshold": floor,
            "source_total": round(tot, 1), "written_total": round(wr, 1),
            "removed_below_threshold": round(rm, 1), "removed_pct": round(100 * rm / tot, 2) if tot else 0,
            "dropped_no_zone": round(s["unmapped"][c], 1),
            "unexplained_residual_pct": round(res, 5),
            "max_abs_P_residual": round(float(np.abs(Pw - s["P"][c]).max()), 3),
            "max_abs_A_residual": round(float(np.abs(Aw - s["A"][c]).max()), 3),
            "cells_positive_source": int(s["pos"][c]), "cells_below_threshold": int(s["nbelow"][c]),
            "cells_written": len(w), "negative_cells_source": int(s["neg"][c]),
            "external_zones_with_trips_source": ext_s, "external_zones_with_trips_written": ext_w,
            "pass": int(abs(res) <= 1e-2 and ext_s == ext_w and s["neg"][c] == 0
                        and len(w) == int(s["pos"][c] - s["nbelow"][c])),
        })
    out = pd.DataFrame(rows)
    S, W, R = out.source_total.sum(), out.written_total.sum(), out.removed_below_threshold.sum()
    out = pd.concat([out, pd.DataFrame([{"period": period, "class": "all", "threshold": floor,
        "source_total": round(S, 1), "written_total": round(W, 1), "removed_below_threshold": round(R, 1),
        "removed_pct": round(100 * R / S, 2), "unexplained_residual_pct": round(100 * (S - R - W) / S, 5),
        "pass": int(out["pass"].all())}])], ignore_index=True)
    mt = pd.read_csv(dem / "mode_type.csv").set_index("mode_type")
    for agency, members in g["agency_classes"].items():
        for m in members:
            cmap.append({"scag_core": m, "agency_class": agency, "pce": mt.loc[m, "pce"], "vot": mt.loc[m, "vot"],
                         "demand_file": f"demand_{m}_{period}.csv",
                         "source": "SCAG email 2026-10-15, Q4: merge HOV with NONHOV, keep other classes separate"})
    p1, p2 = dem / "L1_conservation.csv", dem / "L1_class_map.csv"
    write_csv(out, p1)
    write_csv(pd.DataFrame(cmap), p2)
    record(run, [p1, p2], SCRIPT, "SCAG AM_OD.mtx.csv (00_raw/EXTERNAL.csv); 02_demand files")
    worklog(run, f"L1: source {S:,.0f}, written {W:,.0f}, below threshold {R:,.0f}")
    return True


# ---------------------------------------------------------------- L2
def _bpr7(t0, x, alpha, beta, low):
    return t0 * (1 + alpha * np.power(x, np.where(x <= 1, low, beta)))


def step_L2(region_file: Path, root: Path, run: Path, period: str) -> list[Path]:
    cfg = load_region(region_file)
    g, vcfg = cfg["gates"], cfg["vdf"]
    E = float(cfg["vdf"]["period_capacity_factor"][period]) if "period_capacity_factor" in cfg["vdf"] else None
    sup = folder(run, "supply")
    L = pd.read_csv(folder(run, "topology") / "link.csv", encoding="utf-8-sig", low_memory=False)
    ramp_ft = vcfg["on_ramp"]["facility_types"]
    ramp = L.facility_type.isin(ramp_ft).to_numpy()
    before = L.vdf_type.copy()
    L.loc[ramp, "vdf_type"] = int(vcfg["on_ramp"]["vdf_type"])
    write_csv(L, sup / "link.csv")

    mt = pd.read_csv(folder(run, "demand") / "mode_type.csv").set_index("mode_type")
    side = L.dir_side.to_numpy()
    flow = np.zeros(len(L))
    for m, fld in g["flow_fields"].items():
        ab, ba = L[f"AB_{fld}"].fillna(0).to_numpy(float), L[f"BA_{fld}"].fillna(0).to_numpy(float)
        flow += mt.loc[m, "pce"] * np.where(side == "AB", ab, ba)
    t_scag = np.where(side == "AB", L[f"AB_{g['time_field']}"], L[f"BA_{g['time_field']}"]).astype(float)
    t0 = L.vdf_fftt.to_numpy(float)
    lanes = L.lanes.to_numpy(float)
    cap = L.capacity.to_numpy(float)
    if E is None:
        E = float(pd.read_csv(_p(root, _conv(g)) / "parameters" / "period_factor.csv").set_index("period").loc[period, "E"])
    with np.errstate(divide="ignore", invalid="ignore"):
        x = flow / (cap * lanes * E)
    alpha, beta = L.vdf_alpha.to_numpy(float), L.vdf_beta.to_numpy(float)
    low = float(vcfg["uncongested_beta"])
    t7 = _bpr7(t0, x, alpha, beta, low)
    plph = flow / lanes / E
    t8 = t0 + (plph / 120.0) * 5.0 * (1.0 + x) ** 8          # TAPLite vdf_type 8 (on-ramp meter)
    t_used = np.where(L.vdf_type.to_numpy() == 8, t8, t7)

    def grp(ft):
        if ft in (100, 200): return "connector"
        if ft in ramp_ft: return "on-ramp (82, 84)"
        if ft in (10, 20, 21, 22, 25): return "freeway and HOV"
        if ft in (30, 31, 32): return "expressway"
        return "all others"
    G = L.facility_type.map(grp).to_numpy()
    ok = np.isfinite(t_scag) & (t_scag > 0) & np.isfinite(t_used) & (lanes > 0)
    rows = []
    for name in ["freeway and HOV", "expressway", "on-ramp (82, 84)", "all others", "connector", "road (no connectors)"]:
        sel = ok & ((G != "connector") if name.startswith("road") else (G == name))
        if not sel.any():
            continue
        vht = lambda t: float((flow[sel] * t[sel]).sum() / 60)
        r = {"group": name, "links": int(sel.sum()),
             "vht_scag": round(vht(t_scag)), "vht_replay": round(vht(t_used)),
             "vht_ratio": round(vht(t_used) / vht(t_scag), 4),
             "median_time_ratio": round(float(np.median(t_used[sel] / t_scag[sel])), 4),
             "mean_abs_time_error_min": round(float(np.mean(np.abs(t_used[sel] - t_scag[sel]))), 4),
             "vdf_used": "type 7 (Table 16-2)" if name != "connector" else "type 7, alpha 0 (t = t0)"}
        if name.startswith("on-ramp"):
            r["vht_ratio_if_type8"] = round(float((flow[sel] * t8[sel]).sum() / 60) / vht(t_scag), 4)
            r["mean_abs_time_error_min_if_type8"] = round(float(np.mean(np.abs(t8[sel] - t_scag[sel]))), 4)
        rows.append(r)
    rep = pd.DataFrame(rows)
    write_csv(rep, sup / "L2_replay.csv")

    cols = ["link_id", "org_link_id", "dir_side", "facility_type", "area_type", "posted_speed_mph", "lanes",
            "capacity", "vdf_type", "vdf_alpha", "vdf_beta", "vdf_plf", "vdf_group"]
    lv = L[[c for c in cols if c in L.columns]].copy()
    lv["vdf_type_before"] = before
    lv["source"] = vcfg["source"]
    write_csv(lv, sup / "link_vdf.csv")
    road = L[~L.facility_type.isin([100, 200])]
    cl = (road.groupby(["facility_type", "area_type"])
          .agg(links=("link_id", "size"), capacity_per_lane_min=("capacity", "min"),
               capacity_per_lane_median=("capacity", "median"), capacity_per_lane_max=("capacity", "max"),
               vdf_alpha=("vdf_alpha", "first"), vdf_beta=("vdf_beta", "first"), vdf_type=("vdf_type", "first"))
          .reset_index())
    cl["capacity_rule"] = f"{{D}}_HRCAPAC / AM lanes, veh/h/lane (scag_link_hrcapac.csv); period capacity = x lanes x E ({E:g} for {period})"
    cl["vdf_source"] = vcfg["source"]
    write_csv(cl, sup / "capacity_lookup.csv")
    bad = L[(~L.facility_type.isin([100, 200])) & ~((L.capacity > 0) & (L.lanes > 0) & L.vdf_alpha.notna())]
    write_csv(bad[["link_id", "org_link_id", "dir_side", "facility_type", "lanes", "capacity"]], sup / "L2_unmatched.csv")
    paths = [sup / n for n in ("link.csv", "link_vdf.csv", "capacity_lookup.csv", "L2_unmatched.csv", "L2_replay.csv")]
    record(run, paths, SCRIPT, "01_topology/link.csv (SCAG loaded flows and times); region.yaml vdf")
    worklog(run, f"L2: {len(bad)} unmatched road links; ramps set to vdf_type {vcfg['on_ramp']['vdf_type']}")
    return paths


# ---------------------------------------------------------------- L3
def step_L3(region_file: Path, root: Path, run: Path, period: str) -> Path:
    """L3 from a finished TAPLite run (region.yaml > gates > assignment > run_folder).

    Model: vehicles = sum of mod_vol_<class>, t = travel_time. SCAG: vehicles = sum of the
    loaded class flows of the link's direction, t = <D>_TIME_<P>. VHD = sum v (t - t0).
    """
    cfg = load_region(region_file)
    g = cfg["gates"]
    a = g["assignment"]
    src = _p(root, a["run_folder"])
    out = folder(run, "assignment")
    for n in ("settings.csv", "mode_type.csv", "summary_log_file.txt", "RUN_RECORD.json", "link_performance.csv"):
        if (src / n).exists():
            d = out / n
            if not d.exists() or d.stat().st_size != (src / n).stat().st_size:
                shutil.copyfile(src / n, d)
    lp = pd.read_csv(out / "link_performance.csv", low_memory=False)
    L = pd.read_csv(folder(run, "topology") / "link.csv", encoding="utf-8-sig", low_memory=False)
    side = L.dir_side.to_numpy()
    veh_s = np.zeros(len(L))
    for m, fld in g["flow_fields"].items():
        veh_s += np.where(side == "AB", L[f"AB_{fld}"].fillna(0), L[f"BA_{fld}"].fillna(0))
    t_s = np.where(side == "AB", L[f"AB_{g['time_field']}"], L[f"BA_{g['time_field']}"]).astype(float)
    ref = pd.DataFrame({"link_id": L.link_id, "facility_type": L.facility_type, "len_mi": L.vdf_length_mi,
                        "t0": L.vdf_fftt, "veh_s": veh_s, "t_s": t_s})
    lp["veh_m"] = lp.filter(like="mod_vol_").sum(axis=1)
    x = ref.merge(lp[["link_id", "veh_m", "travel_time"]], on="link_id", how="inner")
    x = x[np.isfinite(x.t_s)]

    def grp(ft):
        if ft in (100, 200): return "connector"
        if ft in (82, 84): return "on-ramp (82, 84)"
        if ft in (10, 20, 21, 22, 25): return "freeway and HOV"
        if ft in (30, 31, 32): return "expressway"
        return "all others"
    x["group"] = x.facility_type.map(grp)
    rows = []
    for name in ["freeway and HOV", "expressway", "on-ramp (82, 84)", "all others", "connector", "road (no connectors)", "all"]:
        sel = (x.group != "connector") if name.startswith("road") else (x.group.notna() if name == "all" else x.group == name)
        y = x[sel]
        r = {"group": name, "links": len(y)}
        for k, (vm, tm, vs, ts) in {"vmt": (y.veh_m, None, y.veh_s, None)}.items():
            pass
        vmt_m, vmt_s = (y.veh_m * y.len_mi).sum(), (y.veh_s * y.len_mi).sum()
        vht_m, vht_s = (y.veh_m * y.travel_time).sum() / 60, (y.veh_s * y.t_s).sum() / 60
        vhd_m = (y.veh_m * (y.travel_time - y.t0).clip(lower=0)).sum() / 60
        vhd_s = (y.veh_s * (y.t_s - y.t0).clip(lower=0)).sum() / 60
        r.update({"vmt_model": round(vmt_m), "vmt_scag": round(vmt_s), "vmt_ratio": round(vmt_m / vmt_s, 3),
                  "vht_model": round(vht_m), "vht_scag": round(vht_s), "vht_ratio": round(vht_m / vht_s, 3),
                  "vhd_model": round(vhd_m), "vhd_scag": round(vhd_s),
                  "vhd_ratio": round(vhd_m / vhd_s, 3) if vhd_s else "",
                  "volume_r2": round(float(y.veh_m.corr(y.veh_s) ** 2), 3),
                  "volume_slope_through_0": round(float((y.veh_m * y.veh_s).sum() / (y.veh_s ** 2).sum()), 3)})
        rows.append(r)
    res = pd.DataFrame(rows)
    import re
    log = (out / "summary_log_file.txt").read_text(errors="ignore")
    gaps = re.findall(r"iter No = (\d+).*?gap = ([\d.]+) %", log)
    res["iterations"] = int(gaps[-1][0]) + 1 if gaps else ""
    res["relative_gap_pct"] = float(gaps[-1][1]) if gaps else ""
    path = out / "L3_vmt_vht.csv"
    write_csv(res, path)
    import yaml
    with open(out / "settings.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({k: v for k, v in a.items()}, f, sort_keys=False, allow_unicode=True)
    record(run, [out / n for n in ("settings.csv", "mode_type.csv", "summary_log_file.txt", "RUN_RECORD.json", "link_performance.csv") if (out / n).exists()],
           f"TAPLite ({a['engine']})", a["run_folder"])
    record(run, [path, out / "settings.yaml"], SCRIPT, "04_assignment/link_performance.csv; 01_topology/link.csv (SCAG loaded flows, times)")
    road = res[res.group == "road (no connectors)"].iloc[0]
    worklog(run, f"L3: road VMT {road.vmt_ratio}, VHT {road.vht_ratio} x SCAG; gap {res.relative_gap_pct.iloc[0]} %")
    return path
