"""Gates G1-G12 (CMAP_network_workplan.md section 6) and the input check.

A gate is PASS, FAIL or INFO. Any FAIL stops main_convert.py after the report is written.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


class Gates:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, gate: str, name: str, ok: bool | None, value, expected) -> None:
        status = "INFO" if ok is None else ("PASS" if ok else "FAIL")
        self.rows.append({"gate": gate, "check": name, "status": status,
                          "value": value, "expected": expected})

    @property
    def failed(self) -> int:
        return sum(r["status"] == "FAIL" for r in self.rows)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def strongly_connected(node_ids: np.ndarray, frm: np.ndarray, to: np.ndarray) -> np.ndarray:
    """Component label per node (iterative Kosaraju; no scipy needed)."""
    index = {int(n): k for k, n in enumerate(node_ids)}
    n = len(node_ids)
    out, inn = defaultdict(list), defaultdict(list)
    for a, b in zip(frm, to):
        out[index[int(a)]].append(index[int(b)])
        inn[index[int(b)]].append(index[int(a)])
    seen, order = np.zeros(n, bool), []
    for s in range(n):
        if seen[s]:
            continue
        stack = [(s, iter(out[s]))]
        seen[s] = True
        while stack:
            v, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                order.append(v)
                stack.pop()
            elif not seen[nxt]:
                seen[nxt] = True
                stack.append((nxt, iter(out[nxt])))
    label = np.full(n, -1)
    comp = 0
    for s in reversed(order):
        if label[s] >= 0:
            continue
        stack = [s]
        label[s] = comp
        while stack:
            v = stack.pop()
            for w in inn[v]:
                if label[w] < 0:
                    label[w] = comp
                    stack.append(w)
        comp += 1
    return label


def run(nodes, links, region, reproduction, transaction, lines) -> tuple[Gates, dict]:
    c = region.checks
    g = Gates()
    extra = {}
    z = region.raw["zones"]
    zone_ids = nodes.loc[nodes.node_type == "centroid", "node_id"].to_numpy()
    expected_zones = np.arange(z["first_zone_id"], z["last_zone_id"] + 1)

    # G1
    g.add("G1", "node count", len(nodes) == c["expected_nodes"], len(nodes), c["expected_nodes"])
    g.add("G1", "link count", len(links) == c["expected_links"], len(links), c["expected_links"])
    g.add("G1", "zones flagged ISZONE = 1, ids contiguous",
          len(zone_ids) == c["expected_zones"] and np.array_equal(np.sort(zone_ids), expected_zones),
          f"{len(zone_ids)} zones, ids {zone_ids.min()}-{zone_ids.max()}",
          f"{c['expected_zones']} zones, ids {z['first_zone_id']}-{z['last_zone_id']}")
    known = set(nodes.node_id)
    dangling = (~links.from_node_id.isin(known) | ~links.to_node_id.isin(known)).sum()
    g.add("G1", "every link end is a node", dangling == 0, int(dangling), 0)

    # G2
    g.add("G2", "shapefile joined to extra attributes on (i, j)", bool(links._joined.all()),
          f"{int(links._joined.sum())} / {len(links)}", f"{len(links)} / {len(links)}")

    # G3
    g.add("G3", "lanes >= 1", bool((links.lanes >= 1).all()), int((links.lanes < 1).sum()), 0)

    # G4
    nocap_codes = set(region.nocap["vdf_codes"])
    road = ~links.vdf_code.isin(nocap_codes)
    zero = links[road & ~(links._emcap > 0)]
    extra["capacity_zero"] = zero
    g.add("G4", "@emcap > 0 on every VDF 1-5 and 8 link", len(zero) == 0, len(zero), 0)

    # G5
    ph = float(region.nocap["capacity_placeholder"])
    is_ph = links.capacity == ph
    expected_ph = links.vdf_code.isin(nocap_codes)
    alpha_ok = (links.loc[expected_ph, "vdf_alpha"].astype(float) == 0).all()
    g.add("G5", f"placeholder {int(ph)} only on VDF 6 and 7, alpha 0",
          bool((is_ph == expected_ph).all() and alpha_ok),
          f"{int(is_ph.sum())} links (VDF 6: {int((links.vdf_code == 6).sum())}, "
          f"VDF 7: {int((links.vdf_code == 7).sum())})", "VDF 6 + VDF 7 count")
    zone_set = set(zone_ids.tolist())
    touches = links.from_node_id.isin(zone_set) | links.to_node_id.isin(zone_set)
    ext_road = links[touches & road]
    g.add("G5", "road links touching a zone keep @emcap (not treated as connectors)",
          bool((ext_road.capacity_source == "cmap_emcap").all()),
          f"{len(ext_road)} links, VDF {sorted(ext_road.vdf_code.unique().tolist())}",
          "all cmap_emcap")
    extra["zone_road_links"] = ext_road

    # G6
    label = strongly_connected(nodes.node_id.to_numpy(), links.from_node_id.to_numpy(),
                               links.to_node_id.to_numpy())
    big = np.bincount(label).argmax()
    outside = int((label != big).sum())
    zones_out = int(((label != big) & (nodes.node_type == "centroid").to_numpy()).sum())
    g.add("G6", "one strongly connected network", outside == 0,
          f"{outside} nodes / {zones_out} zones outside the largest component", "0 / 0")
    extra["components"] = int(label.max() + 1)

    # G7
    has_out = set(links.from_node_id)
    has_in = set(links.to_node_id)
    bad = [z_ for z_ in zone_ids if z_ not in has_out or z_ not in has_in]
    g.add("G7", "every zone has an outgoing and an incoming link", not bad, len(bad), 0)

    # G8
    lat, lon = nodes.y_coord, nodes.x_coord
    inside = lat.between(*c["bbox_lat"]) & lon.between(*c["bbox_lon"])
    g.add("G8", "coordinates inside the CMAP region", bool(inside.all()),
          f"lat {lat.min():.3f}-{lat.max():.3f}, lon {lon.min():.3f}-{lon.max():.3f}",
          f"lat {c['bbox_lat']}, lon {c['bbox_lon']}")

    # G9
    dv = np.abs(links.ref_volume - links._vadt)
    dt = np.abs(links.ref_time - links._timau)
    g.add("G9", "ref_volume (DATA1) = @vadt", bool((dv <= 1e-3 * np.maximum(1, links._vadt)).all()),
          f"max diff {dv.max():.4g}", "equal")
    dt = np.maximum(dt, np.abs(links.timau - links._timau))
    g.add("G9", "ref_time and timau (TIMAU) = attribs timau", bool((dt <= 1e-3).all()),
          f"max diff {dt.max():.4g}", "equal")

    # G10
    tol = c["vdf_reproduced_median_error"]
    rep = reproduction[reproduction.variant == "as documented"]
    for _, r in rep.iterrows():
        code = int(r.vdf_code)
        if code in c["vdf_reproduced_codes"]:
            g.add("G10", f"VDF {code} {r['name']}: median error vs CMAP timau",
                  abs(float(r.median_rel_error)) < tol, r.median_rel_error, f"|e| < {tol}")
        else:
            g.add("G10", f"VDF {code} {r['name']}: median error vs CMAP timau", None,
                  r.median_rel_error, "reported")
    for _, r in reproduction[reproduction.variant != "as documented"].iterrows():
        g.add("G10", f"VDF {int(r.vdf_code)} {r['name']} ({r.variant})", None,
              r.median_rel_error, "reported")

    # G11
    nonconn = links[links.vdf_code != 6]
    lo, hi = c["free_speed_mph"]
    out_rng = nonconn[~nonconn.vdf_free_speed_mph.between(lo, hi)]
    g.add("G11", f"free speed {lo}-{hi} mph on non-connector links", None,
          f"{len(out_rng)} outside (listed in checks/free_speed_outliers.csv)", "reported")
    extra["free_speed_outliers"] = out_rng
    zero_speed = links[links._speed <= 0]
    g.add("G11", "links with @speed = 0", None,
          f"{len(zero_speed)} (VDF {sorted(zero_speed.vdf_code.unique().tolist())})", "reported")
    sp = links[(links._speed > 0) & (links.vdf_code != 6) & (links.vdf_fftt > 0)]
    ratio = sp.vdf_fftt / (sp.vdf_length_mi / sp._speed * 60)
    off = (np.abs(ratio - 1) > c["ftime_tolerance"])
    share = float((~off).mean())
    med = float(np.median(ratio))
    g.add("G11", "units: median @ftime / (LENGTH / @speed x 60) = 1 (min, mi, mph)",
          abs(med - 1) <= c["ftime_tolerance"],
          f"median {med:.4f}; {share:.4f} of {len(sp)} links exactly", "1.00 within 1%")
    rules = (sp.assign(off=off, implied_mph=(sp.vdf_length_mi / sp.vdf_fftt * 60).round(1))
             .groupby(["vdf_code", "facility_type", "_speed"])
             .agg(links=("off", "size"), links_differing=("off", "sum"),
                  free_speed_from_ftime_mph_median=("implied_mph", "median"),
                  free_speed_from_ftime_mph_min=("implied_mph", "min"),
                  free_speed_from_ftime_mph_max=("implied_mph", "max"))
             .reset_index())
    rules = rules[rules.links_differing > 0]
    extra["ftime_rules"] = rules
    g.add("G11", "links where @ftime follows a CMAP free-speed rule, not @speed", None,
          f"{int(off.sum())} links in {len(rules)} (VDF, posted speed) groups "
          "(checks/ftime_vs_posted_speed.csv)", "reported; @ftime is used as given")
    conn = links[(links.vdf_code == 6) & (links._speed > 0)]
    if len(conn):
        eff = float(np.median(conn.vdf_length_mi / conn.vdf_fftt * 60))
        g.add("G11", "connector effective speed LENGTH / @ftime", None, f"{eff:.1f} mph",
              "reported (posted 30)")
    xy = nodes.set_index("node_id")[["_x_ft", "_y_ft"]]
    a = xy.loc[links.from_node_id].to_numpy()
    b = xy.loc[links.to_node_id].to_numpy()
    straight_mi = np.hypot(*(a - b).T) / 5280.0
    okl = straight_mi > 0.01
    lr = float(np.median(links.vdf_length_mi[okl] / straight_mi[okl]))
    g.add("G11", "units: LENGTH (mi) vs straight-line node distance (US ft / 5280)",
          abs(lr - 1) <= c["length_tolerance"], f"median ratio {lr:.3f}",
          f"within {c['length_tolerance']:.0%} of 1")

    # G12
    tl = transaction["lanes"]
    g.add("G12", "node count = network_p7.txt", transaction["nodes"] == len(nodes),
          transaction["nodes"], len(nodes))
    g.add("G12", "link count = network_p7.txt", transaction["links"] == len(links),
          transaction["links"], len(links))
    m = links[["from_node_id", "to_node_id", "lanes"]].merge(
        tl, left_on=["from_node_id", "to_node_id"], right_on=["inode", "jnode"], how="left")
    same = (m.lanes_x == m.lanes_y).mean()
    g.add("G12", "lanes = network_p7.txt", bool(same == 1.0), f"{same:.4f} equal", "1.0000")
    empty_geom = sum(1 for c_ in lines if len(c_) < 2)
    g.add("G12", "every link has a line geometry", empty_geom == 0, empty_geom, 0)
    return g, extra


# ---- demand gates D1-D6 (CMAP_OD_workplan.md section 7) -------------------------------
def demand_gates(g: Gates, dem: dict, nodes, links) -> None:
    n = 3649
    sizes = dem["sizes"]
    bad = [k for k, v in sizes.items() if v != n * n * 4]
    g.add("D1", "every .emx is 3649 x 3649 float32", not bad,
          f"{len(sizes)} matrices read" + (f"; wrong size {bad}" if bad else ""), "53,260,804 bytes each")
    zones = set(nodes.loc[nodes.node_type == "centroid", "node_id"])
    g.add("D2", "zone ids 1-3649 are centroids in node.csv", zones == set(range(1, n + 1)),
          f"{len(zones)} centroids", "1-3649")
    s = dem["summary"].set_index("mode_type")
    g.add("D3", "every demand file has o_zone_id,d_zone_id,volume and > 0 rows",
          bool((s.cells_written > 0).all()), f"{len(s)} files", "8 files")
    ok = abs(dem["sov_demand_model_total"] - dem["expected_sov_demand_model_total"]) < 1.0
    g.add("D4", "mf417 + mf427 + mf437 = trip_roster PM2 mode 1", ok,
          f"{dem['sov_demand_model_total']:,.1f}", f"{dem['expected_sov_demand_model_total']:,.0f}")
    used = set()
    for a in links.allowed_use.unique():
        used |= set(str(a).split(";"))
    used.discard("closed")
    g.add("D5", "demand modes = allowed_use modes", used == set(s.index),
          f"demand {sorted(s.index)}", f"allowed_use {sorted(used)}")
    for mode, r in s.iterrows():
        g.add("D6", f"{mode}: share kept at volume > {dem['floor']}", None,
              f"{r.share_kept:.2%} ({r.vehicles_dropped:,.0f} veh dropped)", "reported")


# ---- input check, called by code/check_inputs.py --------------------------------
def main(argv: list[str]) -> int:
    from .config import CmapRegion, CmapRegionError
    from . import emme_read
    from scag_transcad.config import region_file_from_argv
    kit = Path(__file__).resolve().parents[3]
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))

    try:
        region = CmapRegion.load(region_file_from_argv(argv, kit / "region.cmap.yaml"))
        check("region file is complete", True, region.source.name)
    except (CmapRegionError, OSError) as error:
        print(f"  FAIL  region file: {error}")
        return 1
    for period in region.periods:
        for key in ("links_shapefile", "nodes_shapefile", "extra_attributes", "emme_network"):
            p = region.input_path(key, period)
            check(f"{period} {key}", p.is_file(), str(p.relative_to(region.root)))
        lp = region.input_path("links_shapefile", period)
        if lp.is_file():
            table = emme_read.read_dbf(lp.with_suffix(".dbf"))
            need = [region.links[k] for k in region.links]
            miss = [f for f in need if f not in table.columns]
            check(f"{period} link fields present", not miss, f"missing {miss}" if miss else
                  f"{len(table)} links")
            ep = region.input_path("extra_attributes", period)
            if ep.is_file():
                ex = emme_read.read_extra_attributes(ep)
                needx = [region.extra[k] for k in region.extra]
                missx = [f for f in needx if f not in ex.columns]
                check(f"{period} extra attribute fields present", not missx,
                      f"missing {missx}" if missx else f"{len(ex)} rows")
    for key, ref in region.raw["references"].items():
        target = region.path(ref["file"])
        present = target.is_file() or (target.is_dir() and any(target.iterdir()))
        check(f"reference [{key}] file", present, ref["file"])
    for mod in ("pyogrio", "pyproj"):
        try:
            __import__(mod)
            check(f"{mod} installed", True, "used")
        except ImportError:
            check(f"{mod} installed", True, "not installed: built-in fallback will be used")
    width = max(len(n) for n, _, _ in results)
    print()
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n  {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
