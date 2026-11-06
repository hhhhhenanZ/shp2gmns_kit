"""Step 2 - convert the Cube shapefile and OMX demand into runnable TAPlite folders.

Everything comes from region.yaml. Nothing outside the output folder is written.

    python code/main_convert.py                      # all periods in region.yaml
    python code/main_convert.py --periods am         # one period

Stages
------
1  network     shapefile -> GMNS link.csv / node.csv   (original converter, QVDF schema)
2  parameters  vdf_alpha per facility x area type, and E per period, from Cube's output
3  conic       rewrite the VDF columns -> the Cube conical configuration
4  demand      OMX -> one CSV per mode
5  stage       runnable run folders: network + demand + settings.csv + mode_type.csv

Output
------
    <output>/region.resolved.json      the exact configuration used
    <output>/CONVERT_MANIFEST.json      what each stage did
    <output>/parameters/                alpha_by_ft_at.csv, period_factor.csv
    <output>/network/qvdf/<period>/     converter output
    <output>/network/conic/<period>/    conical network
    <output>/demand/<period>/           sov_am.csv ... apv_am.csv
    <output>/runs/LEGACY_CONICAL_REPLAY/<period>/

Demand and node files are hard-linked where the disk allows, so they are stored once.

A TransCAD region file (``region: {model: transcad_scag}``, e.g. SCAG) is converted by
``code/src/scag_transcad/pipeline.py`` instead; its stages and outputs are listed there.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = CODE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from conic_replay.region import DEFAULT_REGION_FILE, MODES, Region  # noqa: E402
from scag_transcad.config import region_is_scag  # noqa: E402
from cmap_emme.config import region_is_cmap  # noqa: E402

CONIC_CONFIG = "LEGACY_CONICAL_REPLAY"
QVDF_CONFIG = "CALIBRATED_QVDF_EXTENSION"


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


def apply_region_to_settings(region: Region) -> None:
    """Point the original settings generator at this region's periods and modes.

    ``dtalite_settings_config`` holds NVTA defaults as module-level dicts. They are
    replaced in memory for this run, so the original file stays unchanged.
    """
    from dtalite4cube.settings import dtalite_settings_config as cfg

    cfg.TIME_PERIODS.clear()
    cfg.MODE_TYPE_CONFIG.clear()
    for period, spec in region.periods.items():
        cfg.TIME_PERIODS[period] = {"start_hour": int(spec["start_hour"]),
                                    "end_hour": int(spec["end_hour"])}
        rows = {row["mode"]: row for row in region.raw["mode_types"][period]}
        cfg.MODE_TYPE_CONFIG[period] = [
            {"mode_type_id": index + 1, "mode_type": mode, "name": mode,
             "vot": rows[mode]["vot"], "pce": rows[mode]["pce"], "occ": rows[mode]["occ"]}
            for index, mode in enumerate(MODES)
        ]


def convert_network(args, region: Region, periods: list[str], target: Path) -> dict:
    from dtalite4cube.cube2gmns.funclib import get_gmns_from_cube
    from dtalite4cube.unit_contract import TAPLITE_GENERIC_LENGTH_UNIT, TAPLITE_GENERIC_SPEED_UNIT

    def convert(use_cache: bool) -> dict:
        return get_gmns_from_cube(
            str(region.network_shapefile), periods,
            length_unit=TAPLITE_GENERIC_LENGTH_UNIT, speed_unit=TAPLITE_GENERIC_SPEED_UNIT,
            district_id_assignment=True, capacity_adjustment=False, vdf_type="qvdf",
            output_dir=str(target), period_folder_output=True, target_crs=args.target_crs,
            conversion_workers=args.workers, reserve_cores=args.reserve_cores,
            adaptive=not args.no_adaptive, conversion_cache=use_cache, qvdf_profile_mode=2,
        )

    if args.no_cache:
        return convert(False)
    try:
        return convert(True)
    except Exception as error:  # noqa: BLE001 - the cache pickle is version-fragile
        print(f"WARNING: conversion cache unusable ({type(error).__name__}: {error}); "
              "rebuilding from the shapefile.")
        return convert(False)


def build_conic_network(region: Region, qvdf_dir: Path, conic_dir: Path,
                        periods: list[str]) -> dict:
    import pandas as pd

    from conic_replay.conic_vdf import apply_conic_overlay, load_parameters

    params = load_parameters(region)
    stats = {}
    for period in periods:
        source = qvdf_dir / period / "link.csv"
        if not source.is_file():
            raise FileNotFoundError(f"missing converted link.csv: {source}")
        frame = pd.read_csv(source, dtype=str, keep_default_na=False, low_memory=False)
        hours = region.period_hours(period)
        frame, period_stats = apply_conic_overlay(
            frame, period, hours, params, ref_volume_field=region.cube_field("volume", period))
        target = conic_dir / period
        target.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target / "link.csv", index=False)
        link_or_copy(qvdf_dir / period / "node.csv", target / "node.csv")
        stats[period] = period_stats
        print(f"  conic {period}: {period_stats['links']:,} links, "
              f"vdf_plf={period_stats['vdf_plf']:.6f} (E={period_stats['period_factor_E']}, "
              f"H={hours:g}), alpha from {period_stats['alpha_source_counts']}")
    return stats


def convert_demand(args, region: Region, periods: list[str], target: Path) -> dict:
    from dtalite4cube.omx2csv import get_gmns_demand_from_omx

    return get_gmns_demand_from_omx(
        str(region.demand_folder), periods, output_base_dir=target, period_folder_output=True,
        conversion_workers=args.workers, reserve_cores=args.reserve_cores,
        adaptive=not args.no_adaptive, output_format="csv",
    )


def stage_run_folder(config: str, period: str, network_dir: Path, demand_dir: Path,
                     runs_root: Path, iterations: int, processors: int) -> dict:
    from dtalite4cube.settings.generate_dtalite_settings import generate_dtalite_input_files

    target = runs_root / config / period
    target.mkdir(parents=True, exist_ok=True)
    staged = {name: link_or_copy(network_dir / period / name, target / name)
              for name in ("link.csv", "node.csv")}
    demand_files = []
    for mode in MODES:
        name = f"{mode}_{period}.csv"
        source = demand_dir / period / name
        if not source.is_file():
            raise FileNotFoundError(f"missing demand file for staging: {source}")
        staged[name] = link_or_copy(source, target / name)
        demand_files.append(name)
    generate_dtalite_input_files(target, period, overrides={
        "number_of_iterations": iterations, "number_of_processors": processors})
    return {"config": config, "period": period, "folder": str(target),
            "demand_files": demand_files, "staged_as": staged}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--region", type=Path, help="default: region.yaml at the kit root")
    parser.add_argument("--periods", nargs="+", help="default: every period in region.yaml")
    parser.add_argument("--output-root", type=Path, help="default: output > root in region.yaml")
    parser.add_argument("--vdf-mode", choices=["conic", "both"], default="conic",
                        help="'both' also stages QVDF run folders")
    parser.add_argument("--skip-demand", action="store_true",
                        help="reuse demand CSVs already in <output>/demand")
    parser.add_argument("--skip-stage", action="store_true", help="do not build run folders")
    parser.add_argument("--target-crs", default="EPSG:4326")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--reserve-cores", type=int, default=1)
    parser.add_argument("--no-adaptive", action="store_true")
    parser.add_argument("--no-cache", action="store_true",
                        help="read the shapefile fresh instead of the conversion cache")
    return parser


def main() -> int:
    if region_is_cmap(sys.argv[1:], DEFAULT_REGION_FILE):
        from cmap_emme.pipeline import main as convert_cmap  # CMAP (Emme): region.cmap.yaml
        return convert_cmap(sys.argv[1:])
    if region_is_scag(sys.argv[1:], DEFAULT_REGION_FILE):
        from scag_transcad.pipeline import main as convert_scag
        return convert_scag(sys.argv[1:])
    args = build_arg_parser().parse_args()
    region = Region.load(args.region)
    if args.output_root:
        region.raw["output"]["root"] = str(args.output_root.resolve())
    periods = [p.lower() for p in (args.periods or region.periods)]
    unknown = sorted(set(periods) - set(region.periods))
    if unknown:
        raise SystemExit(f"ERROR: periods {unknown} are not defined in region.yaml")
    if not region.network_shapefile.is_file():
        raise SystemExit(f"ERROR: shapefile not found: {region.network_shapefile}\n"
                         "Check input > network_shapefile in region.yaml.")

    root = region.output_root
    qvdf_dir, conic_dir = root / "network" / "qvdf", root / "network" / "conic"
    demand_dir, runs_root = root / "demand", root / "runs"
    root.mkdir(parents=True, exist_ok=True)
    assignment = region.assignment
    iterations = max(int(v) for v in assignment.get("iterations", [10]))
    processors = int(assignment.get("processors", 8))
    apply_region_to_settings(region)

    started = time.perf_counter()
    manifest: dict = {"region": region.name, "region_file": str(region.source),
                      "shapefile": str(region.network_shapefile),
                      "demand_folder": str(region.demand_folder), "output_root": str(root),
                      "periods": periods, "stages": {}}

    def banner(text):
        print("=" * 72)
        print(text)
        print("=" * 72)

    banner(f"STAGE 1  network: shapefile -> GMNS   [{region.name}: {', '.join(periods)}]")
    manifest["stages"]["network"] = convert_network(args, region, periods, qvdf_dir)

    banner("STAGE 2  parameters: vdf_alpha by facility x area type, E by period")
    from conic_replay.parameters import write_parameters
    manifest["stages"]["parameters"] = write_parameters(region, qvdf_dir / periods[0] / "link.csv")
    print(json.dumps(manifest["stages"]["parameters"], indent=2, default=str))

    banner("STAGE 3  conic overlay")
    manifest["stages"]["conic"] = build_conic_network(region, qvdf_dir, conic_dir, periods)

    if not args.skip_demand:
        banner("STAGE 4  demand: OMX -> per-mode CSV")
        manifest["stages"]["demand"] = convert_demand(args, region, periods, demand_dir)

    if not args.skip_stage:
        banner("STAGE 5  stage run folders")
        configs = [(CONIC_CONFIG, conic_dir)]
        if args.vdf_mode == "both":
            configs.append((QVDF_CONFIG, qvdf_dir))
        staged = []
        for config, source_dir in configs:
            for period in periods:
                if not (demand_dir / period).is_dir():
                    print(f"  skip {config}/{period}: no demand for this period")
                    continue
                info = stage_run_folder(config, period, source_dir, demand_dir, runs_root,
                                        iterations, processors)
                staged.append(info)
                print(f"  staged {config}/{period} ({info['staged_as']['link.csv']})")
        manifest["stages"]["staged_runs"] = staged

    region.write_resolved({"periods_converted": periods,
                           "parameters": manifest["stages"]["parameters"]})
    manifest["elapsed_sec"] = time.perf_counter() - started
    (root / "CONVERT_MANIFEST.json").write_text(json.dumps(manifest, indent=2, default=str),
                                                encoding="utf-8")
    banner(f"Done in {manifest['elapsed_sec']:.1f}s -> {root}")
    print("Next: python code/main_replay.py   (in the TAPlite environment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
