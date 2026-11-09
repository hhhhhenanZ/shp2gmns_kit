"""L0 Topology -> 01_topology/L0_counts.csv

Identity: disconnected zones = 0.
Number:   node, link, zone counts (against the agency files in 00_raw); unreachable
          positive-demand OD pairs by class and period.

Reachability is checked per class on the links whose ``allowed_use`` lists that class.
A path may start at its origin zone and end at its destination zone but may not pass
through any other zone centroid (each centroid is split into a source and a sink copy).
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

from .common import folder, load_region, record, worklog, write_csv
from .prepare import raw_location

SCRIPT = "code/gates/gate_L0.py"
CHUNK = 300


def dbf_records(zip_path: Path, member: str) -> int:
    """Record count from a dBASE header (bytes 4-7), read inside the agency zip."""
    with zipfile.ZipFile(zip_path) as zf, zf.open(member) as f:
        head = f.read(8)
    return struct.unpack("<I", head[4:8])[0]


def reach(n_nodes, zones_node, frm, to, centroid):
    """Boolean [origin zone, destination zone]: reachable without passing other centroids."""
    nz = len(zones_node)
    src_id = n_nodes + np.arange(nz)                      # source copy of each centroid
    pos = {nd: i for i, nd in enumerate(zones_node)}
    from_c = centroid[frm]
    # edges leaving a centroid start from its source copy; all other edges unchanged
    f2 = np.where(from_c, [src_id[pos[x]] if c else 0 for x, c in zip(frm, from_c)], frm)
    g = csr_matrix((np.ones(len(frm)), (f2, to)), shape=(n_nodes + nz, n_nodes + nz))
    out = np.zeros((nz, nz), dtype=bool)
    for a in range(0, nz, CHUNK):
        d = dijkstra(g, directed=True, indices=src_id[a:a + CHUNK], unweighted=True)
        out[a:a + CHUNK] = np.isfinite(d[:, zones_node])
    return out


def run(region_file: Path, run_dir: Path, period: str) -> Path:
    cfg = load_region(region_file)
    g = cfg["gates"]
    topo, dem = folder(run_dir, "topology"), folder(run_dir, "demand")
    node = pd.read_csv(topo / "node.csv")
    link = pd.read_csv(topo / "link.csv", low_memory=False)
    zone = pd.read_csv(topo / "zone.csv")
    mt = pd.read_csv(dem / "mode_type.csv")

    shp = raw_location(run_dir, region_file, g["raw"]["network_shapefile"])
    raw_links = dbf_records(shp, "emme_links.dbf")
    raw_nodes = dbf_records(shp, "emme_nodes.dbf")
    lo, hi = cfg["zones"]["first_zone_id"], cfg["zones"]["last_zone_id"]
    rows = [
        {"item": "nodes", "class": "all", "value": len(node), "reference": raw_nodes,
         "identity": "= records in 00_raw emme_nodes.dbf"},
        {"item": "links", "class": "all", "value": len(link), "reference": raw_links,
         "identity": "= records in 00_raw emme_links.dbf"},
        {"item": "zones", "class": "all", "value": len(zone), "reference": hi - lo + 1,
         "identity": f"= zone range {lo}-{hi} in the region file (CMAP zone system)"},
        {"item": "external zones", "class": "all", "value": int(zone.external.sum()),
         "reference": g["external_zones"][1] - g["external_zones"][0] + 1,
         "identity": f"= external zone range {g['external_zones']}"},
    ]

    # node index
    ids = node.node_id.to_numpy()
    idx = pd.Series(np.arange(len(ids)), index=ids)
    frm = idx[link.from_node_id].to_numpy()
    to = idx[link.to_node_id].to_numpy()
    centroid = np.zeros(len(ids), dtype=bool)
    zones_node = idx[zone.node_id].to_numpy()
    centroid[zones_node] = True
    zone_ids = zone.zone_id.to_numpy()

    # disconnected zones: all-class graph, a zone must reach and be reached by every other zone
    allowed = link.allowed_use.fillna("").str.split(";")
    r_all = reach(len(ids), zones_node, frm, to, centroid)
    np.fill_diagonal(r_all, True)
    bad = (~r_all.all(axis=1)) | (~r_all.all(axis=0))
    rows.append({"item": "disconnected zones", "class": "all", "value": int(bad.sum()),
                 "reference": 0, "identity": "disconnected zones = 0 (each zone reaches and is reached by all zones)"})
    if bad.any():
        write_csv(pd.DataFrame({"zone_id": zone_ids[bad]}), topo / "L0_disconnected_zones.csv")

    zpos = pd.Series(np.arange(len(zone_ids)), index=zone_ids)
    cache = {}
    for m in mt.mode_type:
        mask = allowed.apply(lambda u: m in u).to_numpy()
        key = mask.tobytes()
        if key not in cache:
            cache[key] = reach(len(ids), zones_node, frm[mask], to[mask], centroid)
        r = cache[key]
        d = pd.read_csv(dem / f"demand_{m}_{period}.csv")
        d = d[d.volume > 0]
        o, t = zpos[d.o_zone_id].to_numpy(), zpos[d.d_zone_id].to_numpy()
        intra = o == t
        unreach = ~r[o, t] & ~intra
        rows.append({"item": "positive-demand OD pairs", "class": m, "value": int(len(d)),
                     "reference": "", "identity": f"rows of demand_{m}_{period}.csv with volume > 0"})
        rows.append({"item": "unreachable positive-demand OD pairs", "class": m,
                     "value": int(unreach.sum()), "reference": 0,
                     "identity": f"unreachable pairs = 0 on links allowing {m} (intrazonal excluded)"})
        rows.append({"item": "unreachable trips", "class": m,
                     "value": round(float(d.volume[unreach].sum()), 3), "reference": 0,
                     "identity": "trips on unreachable pairs = 0"})
        rows.append({"item": "links allowing class", "class": m, "value": int(mask.sum()),
                     "reference": "", "identity": "allowed_use contains the class"})

    out = pd.DataFrame(rows)
    out.insert(0, "period", period)
    out["value"] = [int(v) if float(v).is_integer() else v for v in out.value]
    out["pass"] = [("" if r == "" else int(v == r)) for v, r in zip(out.value, out.reference)]
    path = topo / "L0_counts.csv"
    write_csv(out, path)
    paths = [path] + ([topo / "L0_disconnected_zones.csv"] if bad.any() else [])
    record(run_dir, paths, SCRIPT, "01_topology/node.csv link.csv zone.csv; 02_demand; 00_raw shapefile zip")
    worklog(run_dir, f"L0: {int(bad.sum())} disconnected zones; written {path.name}")
    return path
