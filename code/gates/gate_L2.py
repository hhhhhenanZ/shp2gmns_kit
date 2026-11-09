"""L2 Supply -> 03_supply/

Identity: Cap_a = Cap(facility type) x lanes; C_period = c x lanes x H x f; every VDF
parameter has a source.

Files:
  link.csv              the network TAPLite reads: 01_topology/link.csv with the TAPLite VDF
                        (region file > taplite_vdf) and CMAP's own values in cmap_* columns
  link_vdf.csv          per link: CMAP function and parameters, capacity, the TAPLite VDF
  capacity_lookup.csv   per VDF code: capacity rule and source, capacity per lane (min/median/max)
  L2_unmatched.csv      links with no VDF entry or no capacity where one is needed
  L2_replay.csv         at CMAP's own volume (DATA1): VHT from timau, from CMAP fd1-fd8, and
                        from the TAPLite VDF, by VDF code. This is the supply check without
                        any assignment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from .common import KIT_ROOT, folder, load_region, record, worklog, write_csv

sys.path.insert(0, str(KIT_ROOT / "code" / "src"))
from cmap_emme import taplite_vdf  # noqa: E402

SCRIPT = "code/gates/gate_L2.py"


def run(region_file: Path, run_dir: Path, period: str) -> list[Path]:
    cfg = load_region(region_file)
    funcs = cfg["vdf"]["functions"]
    tcfg = cfg["taplite_vdf"]
    hours = float(cfg["periods"][period]["hours"])
    sup = folder(run_dir, "supply")
    link = pd.read_csv(folder(run_dir, "topology") / "link.csv", low_memory=False)

    known = link.vdf_code.isin([int(c) for c in funcs])
    needs_cap = ~link.vdf_code.isin(tcfg["fixed_time_codes"])
    bad = link[~known | (needs_cap & ~(link.capacity > 0))]
    write_csv(bad[["link_id", "from_node_id", "to_node_id", "vdf_code", "capacity", "lanes"]],
              sup / "L2_unmatched.csv")

    net = taplite_vdf.apply(link, tcfg, funcs)
    write_csv(net, sup / "link.csv")

    cols = ["link_id", "vdf_code", "facility_type", "lanes", "capacity", "capacity_source",
            "cmap_vdf_function", "cmap_alpha", "cmap_beta", "cmap_capacity_factor",
            "cmap_capacity_add", "cmap_min_term", "cmap_signal_delay",
            "vdf_type", "vdf_alpha", "vdf_beta", "vdf_plf"]
    write_csv(net[cols], sup / "link_vdf.csv")

    rows = []
    for c, f in sorted(funcs.items(), key=lambda kv: int(kv[0])):
        g = net[net.vdf_code == int(c)]
        real = g[g.capacity_source == "cmap_emcap"]
        rows.append({
            "vdf_code": int(c), "facility_type": f["name"], "links": len(g),
            "capacity_source": "@emcap, veh/h/lane [G]" if len(real) else "placeholder, no constraint",
            "capacity_per_lane_min": real.capacity.min() if len(real) else "",
            "capacity_per_lane_median": real.capacity.median() if len(real) else "",
            "capacity_per_lane_max": real.capacity.max() if len(real) else "",
            "cmap_period_capacity": (f"{f['capacity_factor']} x @emcap x lanes x {hours:g} h"
                                     + (f" + {f['capacity_add']}" if f["capacity_add"] else "")),
            "taplite_period_capacity": f"capacity x lanes x {hours:g} h / plf {tcfg['plf']}",
            "cmap_function": f["form"], "source": f["page"],
            "taplite_vdf": ("fixed time" if int(c) in tcfg["fixed_time_codes"]
                            else f"{tcfg['form']} alpha {tcfg['alpha']} beta {tcfg['beta']}"),
        })
    write_csv(pd.DataFrame(rows), sup / "capacity_lookup.csv")

    rep = taplite_vdf.replay(net, funcs, hours)
    write_csv(rep, sup / "L2_replay.csv")

    paths = [sup / n for n in ("link.csv", "link_vdf.csv", "capacity_lookup.csv",
                               "L2_unmatched.csv", "L2_replay.csv")]
    record(run_dir, paths, SCRIPT, "01_topology/link.csv; region file vdf and taplite_vdf")
    road = rep[rep.vdf_code == "road"].iloc[0]
    worklog(run_dir, f"L2: {len(bad)} unmatched links; VHT at CMAP volume, road links: "
                     f"CMAP fd {road.vht_ratio_cmap_fd} x timau, TAPLite VDF {road.vht_ratio_taplite_vdf} x timau")
    return paths
