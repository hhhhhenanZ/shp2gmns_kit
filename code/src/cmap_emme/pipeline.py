"""CMAP conversion stages, driven by ``code/main_convert.py``.

    python code/main_convert.py --region region.cmap.yaml --periods PM

Stages: 1 read, 2 join, 3 nodes, 4 links, 5 rules, 6 write, 7 checks, 8 report.
Output under ``output > root`` (data/output/cmap):

    network/<P>/node.csv, link.csv      the GMNS network
    network/link_geometry.csv           WKT, EPSG:4326, join on link_id
    network/link_excluded.csv           links not written (none expected)
    parameters/vdf_parameters.csv       CMAP functions, placeholder rule
    parameters/access_rule_check.csv    MODES -> allowed_use
    checks/*.csv                        gate_report, network_summary, vdf_reproduction, ...
    CONVERSION_REPORT.md, FIELD_PROVENANCE.csv, CONVERT_MANIFEST.json, region.resolved.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import access, checks, demand, emme_read, network, report, vdf
from .config import RESOLVED_NAME, CmapRegion
from scag_transcad.config import region_file_from_argv

KIT_ROOT = Path(__file__).resolve().parents[3]


def banner(text: str) -> None:
    print("=" * 72)
    print(text)
    print("=" * 72)


def write_csv(frame: pd.DataFrame, path: Path, bom: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig" if bom else "utf-8")


def summary_by_vdf(links: pd.DataFrame, region) -> pd.DataFrame:
    rows = []
    for code, grp in links.groupby("vdf_code"):
        real = grp[grp.capacity_source == "cmap_emcap"]
        rows.append({
            "vdf_code": int(code), "facility_type": grp.facility_type.iloc[0], "links": len(grp),
            "miles": round(grp.vdf_length_mi.sum(), 1),
            "lane_miles": round((grp.vdf_length_mi * grp.lanes).sum(), 1),
            "lanes_min": int(grp.lanes.min()), "lanes_median": float(grp.lanes.median()),
            "lanes_max": int(grp.lanes.max()),
            "capacity_vphpl_median": (round(float(real.capacity.median()), 1) if len(real)
                                      else f"placeholder {region.nocap['capacity_placeholder']}"),
            "capacity_vphpl_range": (f"{real.capacity.min():.0f}-{real.capacity.max():.0f}"
                                     if len(real) else "-"),
            "free_speed_mph_median": round(float(grp.vdf_free_speed_mph.median()), 1),
            "pm_vmt": round(float((grp.ref_volume * grp.vdf_length_mi).sum())),
        })
    return pd.DataFrame(rows)


def convert_period(region: CmapRegion, period: str, skip_demand: bool = False) -> int:
    out = region.output_root
    bom = bool(region.raw["output"].get("csv_bom", True))
    hours = float(region.periods[period]["hours"])
    t0 = time.perf_counter()

    banner(f"CMAP {period}: 1-2 read and join")
    raw_links, lines, reader = emme_read.read_links(region.input_path("links_shapefile", period))
    raw_nodes, _ = emme_read.read_nodes(region.input_path("nodes_shapefile", period))
    extra = emme_read.read_extra_attributes(region.input_path("extra_attributes", period))
    transaction = emme_read.read_transaction_counts(region.input_path("emme_network", period))
    print(f"  links {len(raw_links):,}  nodes {len(raw_nodes):,}  extra attributes {len(extra):,}"
          f"  (reader: {reader})")

    banner(f"CMAP {period}: 3-5 nodes, links, rules")
    nodes, crs_method = network.build_nodes(raw_nodes, region)
    links = network.build_links(raw_links, extra, region, hours)
    links = vdf.assign(links, region)
    links = network.finish_links(links)
    links, access_check = access.assign(links, region)
    params = vdf.parameter_table(region)
    reproduction = vdf.reproduction(links, region, hours)
    geometry, _ = network.geometry_table(links, lines)
    print(f"  reprojection: {crs_method}")

    banner(f"CMAP {period}: 6 write")
    net_dir = out / "network" / period
    write_csv(nodes[network.NODE_COLUMNS], net_dir / "node.csv", bom)
    write_csv(links[network.LINK_COLUMNS], net_dir / "link.csv", bom)
    write_csv(geometry, out / "network" / "link_geometry.csv", bom)
    write_csv(pd.DataFrame(columns=["org_link_id", "reason"]),
              out / "network" / "link_excluded.csv", bom)
    write_csv(params, out / "parameters" / "vdf_parameters.csv", bom)
    write_csv(access_check, out / "parameters" / "access_rule_check.csv", bom)
    summary = summary_by_vdf(links, region)
    write_csv(summary, out / "checks" / "network_summary.csv", bom)
    write_csv(reproduction, out / "checks" / "vdf_reproduction.csv", bom)

    banner(f"CMAP {period}: 7 checks")
    gates, extra_out = checks.run(nodes, links, region, reproduction, transaction, lines)

    dem = None
    if not skip_demand and "demand" in region.raw and period in region.raw["demand"]["periods"]:
        banner(f"CMAP {period}: 7b demand")
        dem = demand.write(region.raw["demand"], region, period, out, bom)
        write_csv(dem["summary"], out / "parameters" / "demand_summary.csv", bom)
        write_csv(dem["mode_types"], out / "parameters" / "mode_type_by_period.csv", bom)
        for _, r in dem["summary"].iterrows():
            print(f"  {r.mode_type:<5} {r.total_vehicles:>12,.0f} veh  written {r.cells_written:>10,} cells"
                  f"  kept {r.share_kept:.2%}")
        checks.demand_gates(gates, dem, nodes, links)
    gate_frame = gates.frame()
    write_csv(gate_frame, out / "checks" / "gate_report.csv", bom)
    keep = ["link_id", "org_link_id", "from_node_id", "to_node_id", "vdf_code", "lanes",
            "capacity", "capacity_source", "_speed", "vdf_free_speed_mph", "ref_volume"]
    write_csv(extra_out["capacity_zero"][keep], out / "checks" / "capacity_zero.csv", bom)
    write_csv(extra_out["zone_road_links"][keep], out / "checks" / "zone_road_links.csv", bom)
    write_csv(extra_out["free_speed_outliers"][keep], out / "checks" / "free_speed_outliers.csv", bom)
    write_csv(extra_out["ftime_rules"], out / "checks" / "ftime_vs_posted_speed.csv", bom)
    for _, r in gate_frame.iterrows():
        print(f"  {r.status:<4}  {r.gate:<4} {r.check}: {r.value}")

    banner(f"CMAP {period}: 8 report")
    manifest = {
        "region": region.name, "region_file": str(region.source.name), "period": period,
        "reader": reader, "reprojection": crs_method,
        "nodes": len(nodes), "links": len(links),
        "zones": int((nodes.node_type == "centroid").sum()),
        "placeholder_links": int((links.capacity_source == region.nocap["capacity_source_label"]).sum()),
        "gates": gate_frame.status.value_counts().to_dict(),
        "demand_vehicles": (None if dem is None else
                            {r.mode_type: r.total_vehicles for _, r in dem["summary"].iterrows()}),
        "seconds": round(time.perf_counter() - t0, 1), "finished_utc": report.now(),
        "outputs": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()),
    }
    write_csv(report.provenance(region), out / "FIELD_PROVENANCE.csv", bom)
    (out / "CONVERSION_REPORT.md").write_text(
        report.conversion_report(region, period, nodes, links, gate_frame, summary, reproduction,
                                 access_check, manifest, dem), encoding="utf-8")
    (out / "CONVERT_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / RESOLVED_NAME).write_text(json.dumps(region.raw, indent=2, default=str), encoding="utf-8")
    print(f"  written to {out}")
    print(f"  {manifest['gates']}  in {manifest['seconds']} s")
    return 1 if gates.failed else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CMAP (Emme) highway network -> GMNS")
    parser.add_argument("--region", type=Path)
    parser.add_argument("--periods", nargs="*")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--skip-demand", action="store_true", help="network only")
    args, _ = parser.parse_known_args(argv)
    region = CmapRegion.load(args.region or region_file_from_argv(argv, KIT_ROOT / "region.cmap.yaml"))
    if args.output_root:
        region.raw["output"]["root"] = str(args.output_root.resolve())
    periods = args.periods or list(region.periods)
    unknown = sorted(set(periods) - set(region.periods))
    if unknown:
        raise SystemExit(f"ERROR: periods {unknown} are not in {region.source.name}")
    status = 0
    for period in periods:
        status |= convert_period(region, period, args.skip_demand)
    if status:
        print("  One or more gates FAILED: read checks/gate_report.csv and CONVERSION_REPORT.md.")
    return status
