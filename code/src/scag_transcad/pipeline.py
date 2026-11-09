"""SCAG conversion stages, driven by ``code/main_convert.py``.

    python code/main_convert.py                      # every period in region.yaml
    python code/main_convert.py --periods AM         # one period

Stages
------
1  network   shapefile -> nodes, directed links, capacity per lane
2  zones     Tier-1 zone centroids from the TAZ polygons and SCAG's loaded flows
3  rules     VDF, allowed_use, period capacity factor, and their checks
4  write     network/<P>/link.csv, node.csv
4b split     zone nodes on the road network -> network/zone_split.csv (zones > split_road_zone_nodes)
5  demand    demand/<P>/<mode_type>_<P>.csv
6  stage     runs/<config>/<P>/: network + demand + settings.csv + mode_type.csv
7  report    FIELD_PROVENANCE.csv, CONVERSION_REPORT.md, CONVERT_MANIFEST.json

Output
------
    <output>/region.resolved.json          the exact configuration used
    <output>/CONVERT_MANIFEST.json         what each stage did
    <output>/CONVERSION_REPORT.md          sources, gaps, checks, decisions
    <output>/FIELD_PROVENANCE.csv          every output column and where it comes from
    <output>/parameters/                   zone_centroids, period_factor, vdf_parameters,
                                           access_rule_check, on_ramp_function_check,
                                           mode_type_by_period
    <output>/network/<P>/                  link.csv, node.csv
    <output>/network/link_excluded.csv     directed links not written, with the reason
    <output>/demand/<P>/                   DA_<P>.csv ... SR3_NONHOV_<P>.csv
    <output>/runs/<config>/<P>/            runnable TAPlite folders
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import demand as demand_io
from . import network as net
from . import provenance, runfiles, zones
from . import vdf as vdf_rules
from .access import assign_allowed_use, check_against_loaded_flows
from .config import CLOSED, REGION_ENV, ScagRegion, fill
from .dictionary import NetworkDictionary
from .fields import LinkFields
from .topology import build_topology, directed_links, read_shapefile

KIT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGION = KIT_ROOT / "region.yaml"


def banner(text: str) -> None:
    print("=" * 72)
    print(text)
    print("=" * 72)


def link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def copy_without_bom(source: Path, target: Path, chunk: int = 8 << 20) -> str:
    """Copy a CSV, dropping a leading UTF-8 BOM.

    TAPlite matches header names literally (``GetValueByFieldName``) and its reader knows
    nothing about a BOM, so a file starting with EF BB BF hides its first column from the
    kernel. network/<P>/ keeps the BOM for Excel; the staged copy must not have it.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with source.open("rb") as reader, target.open("wb") as writer:
        head = reader.read(3)
        if head != b"\xef\xbb\xbf":
            writer.write(head)
        while True:
            block = reader.read(chunk)
            if not block:
                break
            writer.write(block)
    return "copy without BOM"


def _json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return str(value)


def _require(mask: np.ndarray, message: str) -> None:
    if mask.any():
        raise ValueError(f"{int(mask.sum())} {message}")


def _require_writable(root: Path, periods: list[str]) -> None:
    """Fail before stage 1 if an output file is locked.

    Opening link.csv in Excel takes an exclusive lock on Windows, and the write only fails
    at stage 4, after the shapefile, the zones and the rules are already done. Checking the
    targets first turns a ten-minute failure into an immediate message.
    """
    targets = [root / "CONVERT_MANIFEST.json", root / "CONVERSION_REPORT.md",
               root / "FIELD_PROVENANCE.csv", root / "region.resolved.json",
               root / "network" / "link_geometry.csv", root / "network" / "link_excluded.csv"]
    targets += [root / "network" / period / name
                for period in periods for name in ("link.csv", "node.csv")]
    locked = []
    for path in targets:
        if not path.is_file():
            continue
        try:
            with path.open("ab"):
                pass
        except OSError as error:
            locked.append(f"{path}  ({error.strerror or error})")
    if locked:
        listing = "".join(chr(10) + "  " + item for item in locked)
        raise SystemExit(
            "ERROR: these output files are open in another program (Excel takes an exclusive "
            "lock on a CSV it has open). Close them and run again:" + listing)


def prepare_network(region: ScagRegion) -> dict:
    lf = region.link_field
    dictionary = NetworkDictionary.load(region.path("network_dictionary"))
    frame = read_shapefile(region.path("network_shapefile"))
    if frame.crs is None:
        raise ValueError("the network shapefile has no .prj; its CRS is needed for coordinates")
    topology_cfg = region.raw.get("topology", {}) or {}
    topology = build_topology(frame, int(topology_cfg.get("coordinate_decimals", 3)))
    attributes = pd.DataFrame(frame.drop(columns=frame.geometry.name))
    directed = directed_links(topology, dictionary.shapefile_name(lf("dir")))
    fields = LinkFields(attributes, dictionary, directed)

    mode_code = fields.per_direction(lf("mode"))
    highway = mode_code == float(region.access["highway_mode"])
    self_loop = (directed["a"] == directed["b"]).to_numpy()
    keep = highway & ~self_loop
    context = {
        "dictionary": dictionary, "topology": topology, "attributes": attributes,
        "directed": directed, "fields": fields, "mode_code": mode_code,
        "highway": highway, "self_loop": self_loop, "keep": keep,
        "link_ids": fields.per_record(lf("id")).astype(np.int64),
        "facility_type": fields.per_direction(lf("facility_type"), fallback_to_ab=True),
        "posted_speed": fields.per_direction(lf("posted_speed"), fallback_to_ab=True),
        "area_type": fields.per_direction(lf("area_type"), fallback_to_ab=True),
        "free_time": fields.per_direction(lf("free_time_min"), fallback_to_ab=True),
        "length_mi": fields.per_direction(lf("length_mi")),
        "toll_flag": np.nan_to_num(fields.per_direction(lf("toll_flag")), nan=0.0),
        "truck_prohibit": np.nan_to_num(fields.per_direction(lf("truck_prohibit")), nan=0.0),
        "road_name": fields.per_direction(lf("road_name"), numeric=False),
    }
    _require(keep & ~np.isfinite(context["facility_type"]), "highway links have no facility type")
    _require(keep & ~(np.isfinite(context["free_time"]) & (context["free_time"] > 0)),
             "highway links have no positive free-flow time")
    _require(keep & ~(np.isfinite(context["length_mi"]) & (context["length_mi"] > 0)),
             "highway links have no positive length")

    cap = region.capacity
    path = region.path("link_capacity_csv")
    table = pd.read_csv(path)
    id_field = cap["id_field"]
    if table[id_field].duplicated().any():
        raise ValueError(f"{path.name} repeats {id_field} values")
    missing = np.setdiff1d(np.unique(context["link_ids"]), table[id_field].to_numpy())
    if len(missing):
        raise ValueError(f"{len(missing)} link IDs have no row in {path.name}, e.g. "
                         f"{missing[:5].tolist()}")
    aligned = table.set_index(id_field).reindex(context["link_ids"])
    record = directed["record"].to_numpy()
    ab = aligned[fill(cap["hourly_capacity_field"], D="AB")].to_numpy(dtype=float)[record]
    ba = aligned[fill(cap["hourly_capacity_field"], D="BA")].to_numpy(dtype=float)[record]
    hourly = np.where(fields.is_ab, ab, ba)
    basis_lanes = fields.per_direction(lf("lanes"), P=str(cap["lanes_basis_period"]))
    with np.errstate(divide="ignore", invalid="ignore"):
        lane_capacity = hourly / basis_lanes
    _require(keep & ~(np.isfinite(lane_capacity) & (lane_capacity > 0)),
             "highway links have no positive capacity per lane")
    context.update(hourly_capacity=hourly, lane_capacity=lane_capacity)
    return context


def run(region: ScagRegion, periods: list[str], *, skip_demand: bool = False,
        skip_stage: bool = False, chunksize: int = 2_000_000, iterations: int | None = None,
        processors: int | None = None) -> dict:
    started = time.perf_counter()
    root = region.output_root
    network_dir, demand_dir = root / "network", root / "demand"
    params_dir, runs_root = root / "parameters", root / "runs"
    params_dir.mkdir(parents=True, exist_ok=True)
    _require_writable(root, periods)
    manifest: dict = {"region": region.name, "model": "transcad_scag",
                      "region_file": str(region.source), "output_root": str(root),
                      "periods": periods, "stages": {},
                      "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    # ---- 1 ------------------------------------------------------------------
    banner(f"STAGE 1  network: shapefile -> nodes and directed links   [{region.name}]")
    stage = time.perf_counter()
    ctx = prepare_network(region)
    topology, directed, fields, keep = ctx["topology"], ctx["directed"], ctx["fields"], ctx["keep"]
    manifest["stages"]["network"] = {
        "shapefile": str(region.path("network_shapefile")),
        "records": int(len(ctx["attributes"])), "fields": int(ctx["attributes"].shape[1]),
        "source_crs": str(topology.frame.crs.name),
        "nodes": int(topology.node_count), "directed_links": int(len(directed)),
        "kept_directed_links": int(keep.sum()),
        "excluded_not_highway": int((~ctx["highway"]).sum()),
        "excluded_self_loops": int((ctx["highway"] & ctx["self_loop"]).sum()),
        "ba_values_taken_from_ab": dict(fields.fallbacks),
        "elapsed_sec": time.perf_counter() - stage,
    }
    print(json.dumps(manifest["stages"]["network"], indent=2, default=_json_default))

    # ---- 2 ------------------------------------------------------------------
    banner("STAGE 2  zones: Tier-1 centroids")
    stage = time.perf_counter()
    crosswalk = zones.load_crosswalk(region)
    resolve_period = str(region.zones["resolve"]["period"])
    print(f"  reading {resolve_period} trip ends from {region.demand_csv(resolve_period).name}")
    origins, destinations, ends_stats = demand_io.trip_ends(region, resolve_period, crosswalk,
                                                            chunksize)
    centroids, zone_notes = zones.resolve_centroids(region, topology, directed, fields, keep,
                                                    ctx["facility_type"], crosswalk,
                                                    origins, destinations)
    # Node ids wait for stage 3: which links are written decides which nodes survive.
    manifest["stages"]["zones"] = {**zone_notes, "trip_ends": ends_stats,
                                   "elapsed_sec": time.perf_counter() - stage}
    print(json.dumps(manifest["stages"]["zones"], indent=2, default=_json_default))

    # ---- 3 ------------------------------------------------------------------
    banner("STAGE 3  rules: VDF, allowed_use, period capacity factor")
    stage = time.perf_counter()
    vdf = vdf_rules.assign_vdf(region, ctx["facility_type"], ctx["posted_speed"], ctx["area_type"], keep)
    allowed, rule_name = assign_allowed_use(region, ctx["facility_type"], ctx["toll_flag"],
                                            ctx["truck_prohibit"], keep)
    factor = vdf_rules.period_factor_table(region)
    factor.to_csv(params_dir / "period_factor.csv", index=False)
    vdf_rules.parameter_table(region).to_csv(params_dir / "vdf_parameters.csv", index=False)
    ramp_check = vdf_rules.ramp_function_check(region, fields, keep, vdf, ctx["free_time"],
                                               ctx["lane_capacity"], factor)
    ramp_check.to_csv(params_dir / "on_ramp_function_check.csv", index=False)
    access_check = check_against_loaded_flows(region, fields, keep, allowed, rule_name)
    access_check.to_csv(params_dir / "access_rule_check.csv", index=False)
    pd.DataFrame([{"period": p, **row} for p in region.periods
                  for row in runfiles.mode_type_rows(region, p)]).to_csv(
        params_dir / "mode_type_by_period.csv", index=False)

    # Tier-1 output. Links closed to every mode (the Tier-2 centroid connectors) are left
    # out, and with them the nodes no remaining link touches - the Tier-2 centroids.
    options = region.output_options
    closed = keep & (allowed == CLOSED)
    write_mask = keep if options["keep_closed_links"] else (keep & ~closed)
    used_nodes = np.unique(np.r_[directed["a"].to_numpy()[write_mask],
                                 directed["b"].to_numpy()[write_mask]])
    first_road = int((region.raw.get("topology") or {}).get("first_road_node_id", 100001))
    node_ids, kept_nodes = net.assign_node_ids(topology.node_count, centroids, first_road,
                                               surviving=used_nodes)
    nodes = net.node_table(topology, node_ids, centroids, kept_nodes)
    lon, lat = net.node_lonlat(topology)
    located = (centroids["node_index"] >= 0).to_numpy()
    index = np.maximum(centroids["node_index"].to_numpy(), 0)
    centroids.insert(centroids.columns.get_loc("node_index") + 1, "node_id",
                     pd.array(np.where(located, node_ids[index], 0), dtype="Int64"))
    centroids.loc[~located, "node_id"] = pd.NA
    centroids["x_coord"] = np.where(located, np.round(lon[index], 7), np.nan)
    centroids["y_coord"] = np.where(located, np.round(lat[index], 7), np.nan)
    net.write_csv(centroids.drop(columns="node_index"), params_dir / "zone_centroids.csv",
                  bom=options["csv_bom"])
    print(f"  links written {int(write_mask.sum()):,} of {int(keep.sum()):,} "
          f"(closed left out: {int((closed & ~write_mask).sum()):,}); "
          f"nodes {int(kept_nodes.sum()):,} of {topology.node_count:,}")
    kept_types = pd.Series(vdf["vdf_type"][write_mask]).value_counts().sort_index()
    manifest["stages"]["rules"] = {
        "output_options": options,
        "link_type_rule": f"{region.area_type_multiplier} * area_type + facility_type",
        "links_written": int(write_mask.sum()),
        "closed_links_left_out": int((closed & ~write_mask).sum()),
        "nodes_written": int(kept_nodes.sum()),
        "nodes_left_out": int(topology.node_count - kept_nodes.sum()),
        "vdf_type_links": {int(k): int(v) for k, v in kept_types.items()},
        "allowed_use_rules": pd.Series(rule_name[write_mask]).value_counts().to_dict(),
        "period_factor": factor.to_dict("records"),
        "elapsed_sec": time.perf_counter() - stage,
    }
    print(factor[["period", "start_hour", "end_hour", "period_hours", "settings_start_hour",
                  "settings_end_hour", "E", "vdf_plf", "hours_x_plf", "E_source"]].to_string(index=False))
    if len(ramp_check):
        print(ramp_check[["period", "function", "loaded_delay_min_median",
                          "predicted_delay_min_median", "mean_abs_error_min"]].to_string(index=False))

    # ---- 4 ------------------------------------------------------------------
    banner(f"STAGE 4  write network: {', '.join(periods)}")
    stage = time.perf_counter()
    static = net.static_link_table(region, ctx, node_ids, vdf, allowed, rule_name, write_mask)
    original = net.tidy_original(ctx["attributes"])
    # Geometry is the same in every period, and 110 links have a WKT longer than Excel's
    # 32,767-character cell limit. Written once to its own file, link.csv stays readable
    # everywhere; TAPlite reads the column as optional and only echoes it.
    geometry_file = None
    in_link_csv = options["include_geometry"] and not options["geometry_separate_file"]
    if options["include_geometry"] and options["geometry_separate_file"]:
        geometry_file = network_dir / "link_geometry.csv"
        net.write_csv(static[["link_id", "org_link_id", "dir_side", "crs", "geometry"]],
                      geometry_file, bom=options["csv_bom"])
        print(f"  geometry -> {geometry_file} ({len(static):,} links)")
    record = directed["record"].to_numpy()
    plf = dict(zip(factor["period"], factor["vdf_plf"]))
    written: dict = {}
    node_template = None
    for period in periods:
        lanes = fields.per_direction(region.link_field("lanes"), P=period)
        rows = static["_row"].to_numpy()
        usable = np.isfinite(lanes[rows]) & (lanes[rows] > 0)
        core = net.period_link_table(region, static[usable], lanes, float(plf[period]),
                                     include_geometry=in_link_csv)
        columns = net.original_columns(ctx["dictionary"], list(original.columns), period, options)
        folder = network_dir / period
        count = net.write_link_csv(folder / "link.csv", core, original, record, columns,
                                   bom=options["csv_bom"])
        if node_template is None:
            net.write_csv(nodes, folder / "node.csv", bom=options["csv_bom"])
            node_template = folder / "node.csv"
        else:
            link_or_copy(node_template, folder / "node.csv")
        written[period] = {"links": int(count), "links_without_lanes": int((~usable).sum()),
                           "nodes": int(len(nodes)), "zones": int(nodes["zone_id"].notna().sum()),
                           "columns": int(len(core.columns) - 1 + len(columns)),
                           "scag_fields_kept": len(columns),
                           "vdf_plf": round(float(plf[period]), 6)}
        print(f"  {period}: {count:,} links, {len(nodes):,} nodes, "
              f"{written[period]['columns']} columns ({len(columns)} SCAG fields) -> {folder}")
    out_rows = np.flatnonzero(~write_mask)
    mode_text = np.array([f"{v:g}" if np.isfinite(v) else "blank"
                          for v in ctx["mode_code"][out_rows]])
    highway_row = ctx["highway"][out_rows]
    reason = np.where(
        closed[out_rows],
        "closed to every mode: " + pd.Series(rule_name[out_rows]).fillna("").to_numpy(),
        np.where(highway_row, "self-loop (from node = to node)",
                 np.char.add(np.char.add("MODE ", mode_text),
                             f" is not a highway link (MODE {region.access['highway_mode']})")))
    net.write_csv(pd.DataFrame({
        "org_link_id": ctx["link_ids"][record[out_rows]],
        "dir_side": directed["side"].to_numpy()[out_rows],
        "reason": reason,
        "facility_type": ctx["facility_type"][out_rows],
        "name": pd.Series(ctx["road_name"][out_rows]).fillna("").to_numpy(),
    }), network_dir / "link_excluded.csv", bom=options["csv_bom"])
    manifest["stages"]["write"] = written

    # ---- 4b -----------------------------------------------------------------
    # Zone nodes that sit on the road network are split off it (zone_split.py): TAPLite does
    # not route through zone centroids, so such a node cuts the road (zone 4140 on I-8) or
    # isolates a zone whose connector leads to another centroid (seaport 4181 via 4179).
    if region.raw.get("zones", {}).get("split_road_zone_nodes", False):
        banner("STAGE 4b zones: split zone nodes that sit on the road network")
        from .zone_split import split_network_folder
        base = int(region.raw["zones"].get("station_id_base", 200000))
        split_log = split_network_folder(network_dir, periods, base, bom=options["csv_bom"])
        for period in periods:
            written[period]["zone_nodes_split"] = int(len(split_log)) if split_log is not None else 0
        manifest["stages"]["zone_split"] = {"zones": int(len(split_log)), "station_id_base": base}
    manifest["stages"]["link_geometry_file"] = str(geometry_file) if geometry_file else None
    manifest["stages"]["write_elapsed_sec"] = time.perf_counter() - stage

    # ---- 5 ------------------------------------------------------------------
    demand_stats: dict = {}
    if not skip_demand:
        banner("STAGE 5  demand: TransCAD CSV -> one CSV per mode")
        resolved = centroids[centroids["node_id"].notna()]
        zone_of_taz = dict(zip(resolved["taz_id"].astype(np.int64), resolved["zone_id"].astype(np.int64)))
        for period in periods:
            if not region.demand_csv(period).is_file():
                print(f"  skip {period}: {region.demand_csv(period)} not found")
                continue
            stats = demand_io.convert_period(region, period, crosswalk, zone_of_taz,
                                             demand_dir / period, chunksize)
            demand_stats[period] = stats
            trips = sum(s["trips"] for s in stats["modes"].values())
            dropped = sum(s["dropped_trips"] for s in stats["modes"].values())
            positive = sum(s.get("positive_trips", 0.0) for s in stats["modes"].values())
            small_rows = sum(s.get("below_min_volume_rows", 0) for s in stats["modes"].values())
            small = sum(s.get("below_min_volume_trips", 0.0) for s in stats["modes"].values())
            share = f"{trips / positive:.1%}" if positive else "n/a"
            print(f"  {period}: {stats['matrix_rows']:,} matrix rows, {trips:,.1f} trips written "
                  f"({share} of the {positive:,.1f} positive), "
                  f"{small:,.1f} in {small_rows:,} cells below min_volume, "
                  f"{dropped:,.1f} dropped, {stats['elapsed_sec']:.0f}s")
    manifest["stages"]["demand"] = demand_stats

    # ---- 6 ------------------------------------------------------------------
    staged = []
    if not skip_stage:
        banner("STAGE 6  stage run folders")
        assignment = region.assignment
        iterations = iterations or max(int(v) for v in assignment.get("iterations", [20]))
        processors = processors or int(assignment.get("processors", 8))
        for period in periods:
            source = demand_dir / period
            names = [demand_io.demand_file_name(m.mode_type, period) for m in region.modes]
            if not all((source / name).is_file() for name in names):
                print(f"  skip {period}: demand files not in {source}")
                continue
            target = runs_root / region.run_config / period
            stage_file = copy_without_bom if options["csv_bom"] else link_or_copy
            linked = {name: stage_file(network_dir / period / name, target / name)
                      for name in ("link.csv", "node.csv")}
            linked.update({name: link_or_copy(source / name, target / name) for name in names})
            files = runfiles.write_run_files(target, region, period, iterations, processors)
            staged.append({"config": region.run_config, "period": period, "folder": str(target),
                           "staged_as": linked, "run_files": files})
            print(f"  staged {region.run_config}/{period}")
    manifest["stages"]["staged_runs"] = staged

    # ---- 7 ------------------------------------------------------------------
    banner("STAGE 7  report")
    manifest["elapsed_sec"] = time.perf_counter() - started
    manifest["stages"]["report"] = provenance.write(
        region, root, context=ctx, factor=factor, ramp_check=ramp_check, access_check=access_check,
        centroids=centroids, zone_notes=zone_notes, manifest=manifest, periods=periods)
    region.write_resolved({"periods_converted": periods, "zone_centroids": zone_notes,
                           "period_factor": factor.to_dict("records")})
    (root / "CONVERT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, default=_json_default), encoding="utf-8")
    banner(f"Done in {manifest['elapsed_sec']:.1f}s -> {root}")
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert the SCAG TransCAD network and trip tables into TAPlite run folders.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--region", type=Path, help="default: region.yaml at the kit root")
    parser.add_argument("--periods", nargs="+", help="default: every period in region.yaml")
    parser.add_argument("--output-root", type=Path, help="default: output > root in region.yaml")
    parser.add_argument("--skip-demand", action="store_true",
                        help="reuse demand CSVs already in <output>/demand")
    parser.add_argument("--skip-stage", action="store_true", help="do not build run folders")
    parser.add_argument("--chunksize", type=int, default=2_000_000,
                        help="trip-table rows read at a time")
    parser.add_argument("--iterations", type=int, help="default: max of assignment > iterations")
    parser.add_argument("--processors", type=int, help="default: assignment > processors")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    region = ScagRegion.load(args.region or Path(os.environ.get(REGION_ENV) or DEFAULT_REGION))
    if args.output_root:
        region.output_root = args.output_root
    known = {p.upper(): p for p in region.periods}
    periods = []
    for period in args.periods or list(region.periods):
        if period.upper() not in known:
            raise SystemExit(f"ERROR: period {period!r} is not in region.yaml "
                             f"({', '.join(region.periods)})")
        periods.append(known[period.upper()])
    run(region, periods, skip_demand=args.skip_demand, skip_stage=args.skip_stage,
        chunksize=args.chunksize, iterations=args.iterations, processors=args.processors)
    print("Next: python code/main_replay.py   (in the TAPlite environment)")
    return 0
