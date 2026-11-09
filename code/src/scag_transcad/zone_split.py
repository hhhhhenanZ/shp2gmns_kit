"""Split zone nodes that sit on the road network.

TAPLite does not route through zone centroids (first_through_node_id). In SCAG's network the
40 external stations, and a few other zones, use a road node as their centroid: a node with
road links in and out, or with a link to another zone's centroid. Paths cannot pass such a
node, so the road is cut there; zone 4140 (I-8 station) and 4181 (seaport, whose only
connector leads to zone 4179) end up isolated.

Split: every link of the zone node moves to a new station node at the same place
(id = station_id_base + zone node id), and the zone node is joined to the station node by
one connector pair (facility 100, no delay). The zone node becomes a leaf; roads stay whole.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ROAD_EXCLUDE = (100, 200)
MODES = "DA;SR2_HOV;SR3_HOV;LHDT;MHDT;HHDT;SR2_NONHOV;SR3_NONHOV"


def zones_to_split(link: pd.DataFrame, zone_nodes) -> list[int]:
    Z = set(int(z) for z in zone_nodes)
    road = ~link.facility_type.isin(ROAD_EXCLUDE)
    out = []
    for n in sorted(Z):
        f, t = link.from_node_id == n, link.to_node_id == n
        through = (road & t).any() and (road & f).any()
        to_zone = link.to_node_id[f].isin(Z).any() or link.from_node_id[t].isin(Z).any()
        if through or to_zone:
            out.append(n)
    return out


def split(node: pd.DataFrame, link: pd.DataFrame, zone_nodes, station_id_base: int = 200000):
    todo = zones_to_split(link, zone_nodes)
    node, link = node.copy(), link.copy()
    new_nodes, new_links, log = [], [], []
    next_id = int(link.link_id.max()) + 1
    for n in todo:
        s = station_id_base + n
        row = node[node.node_id == n].iloc[0].to_dict()
        row.update({"node_id": s})
        for col in ("zone_id", "zone_type", "taz_id", "centroid_method", "centroid_confidence"):
            if col in row:
                row[col] = np.nan
        row["node_type"] = "zone_split_station"
        new_nodes.append(row)
        moved = int((link.from_node_id == n).sum() + (link.to_node_id == n).sum())
        link.loc[link.from_node_id == n, "from_node_id"] = s
        link.loc[link.to_node_id == n, "to_node_id"] = s
        for a, b, side in ((n, s, "AB"), (s, n, "BA")):
            new_links.append({"link_id": next_id, "from_node_id": a, "to_node_id": b, "dir_flag": 1,
                              "length": 1.0, "lanes": 9, "capacity": 99999.0, "free_speed": 100.0,
                              "toll": 0.0, "link_type": 100, "allowed_use": MODES, "vdf_type": 7,
                              "vdf_alpha": 0.0, "vdf_beta": 1.0, "vdf_plf": 1.0,
                              "vdf_free_speed_mph": 62.14, "vdf_length_mi": 0.000621, "vdf_fftt": 0.0006,
                              "org_link_id": f"zone_split_{n}", "dir_side": side, "facility_type": 100,
                              "name": "zone split connector"})
            next_id += 1
        log.append({"zone_node": n, "station_node": s, "links_moved": moved, "connectors_added": 2})
    node = pd.concat([node, pd.DataFrame(new_nodes)], ignore_index=True)
    link = pd.concat([link, pd.DataFrame(new_links)], ignore_index=True)
    return node, link, pd.DataFrame(log)


def split_network_folder(network_dir, periods, station_id_base: int = 200000, bom: bool = True) -> pd.DataFrame:
    """Stage 4b on a written network folder: split zone nodes in <network_dir>/<P>/link.csv, node.csv."""
    from pathlib import Path
    network_dir = Path(network_dir)
    enc = "utf-8-sig" if bom else "utf-8"
    node_new, log_all = None, None
    for period in periods:
        folder = network_dir / period
        nd = pd.read_csv(folder / "node.csv", encoding="utf-8-sig")
        lk = pd.read_csv(folder / "link.csv", encoding="utf-8-sig", low_memory=False)
        if "zone_split" in str(lk.get("org_link_id", pd.Series(dtype=str)).astype(str).str.cat()):
            print(f"  {period}: already split")
            continue
        nd2, lk2, log = split(nd, lk, nd.loc[nd["zone_id"].notna(), "node_id"], station_id_base)
        tmp = folder / "link.csv.tmp"
        lk2.to_csv(tmp, index=False, encoding=enc)
        tmp.replace(folder / "link.csv")             # a new file: hard links to the old one are kept
        if node_new is None:
            node_new, log_all = nd2, log
        tmpn = folder / "node.csv.tmp"
        node_new.to_csv(tmpn, index=False, encoding=enc)
        tmpn.replace(folder / "node.csv")
        print(f"  {period}: {len(log)} zone nodes split -> {len(lk2):,} links, {len(nd2):,} nodes")
    if log_all is not None:
        log_all.to_csv(network_dir / "zone_split.csv", index=False, encoding=enc)
    return log_all


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Stage 4b alone: split zone nodes in a written SCAG network folder")
    ap.add_argument("network_dir")
    ap.add_argument("--periods", nargs="+", required=True)
    ap.add_argument("--station-id-base", type=int, default=200000)
    a = ap.parse_args()
    split_network_folder(a.network_dir, a.periods, a.station_id_base)
