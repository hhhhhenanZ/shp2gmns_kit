"""Analysis driver for the conic replay runs — review items 4, 5 and 6.

Third stage of the replay pipeline, after ``main_convert.py`` (network + demand)
and ``main_replay.py`` (assignment). Read-only over everything those two produced:
it opens run folders, never writes into them, and never re-runs the kernel.

    python code/main_analyze.py                       # everything, from region.yaml
    python code/main_analyze.py --periods am --items 4 5 6

Run in the conversion environment (pandas, numpy, matplotlib). Nothing here imports
the TAPlite kernel.

Outputs, all under ``<replay-root>/analysis/``:

    item4_three_way.csv           per link: Cube / independent / TAPlite / independent
    item4_three_way_summary.csv   error distribution of each comparison
    item4_regression_ft_at.csv    one row per populated FT x AT cell
    item4_missing_parameters.csv  zero-silent-fallback register
    item5_link_measures.csv       per link VMT / VHT / PMT / PHT, both sides
    item5_rollup.csv              every rollup dimension, with reconciliation
    item5_network_speed.csv       total VMT / total VHT, and the wrong way beside it
    item6_convergence.csv         relative gap per iteration
    item6_runtime.csv             algorithm, stopping rule, timings
    item6_corridors.csv           named-corridor performance
    item6_corridor_vc.csv         corridor V/C, Cube vs TAPlite
    ANALYSIS_MANIFEST.json        inputs, row counts, headline numbers
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import os  # noqa: E402

import pandas as pd  # noqa: E402

from conic_replay.region import REGION_ENV, Region  # noqa: E402


def _region_from_argv(argv):
    """Find --region before argparse runs: the analysis modules read it at import."""
    for index, token in enumerate(argv):
        if token == "--region" and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--region="):
            return token.split("=", 1)[1]
    return None


# Analyse against the configuration that built the network, when it has been written.
REGION = Region.load(_region_from_argv(sys.argv))
_RESOLVED = REGION.resolved_path
os.environ[REGION_ENV] = str(_RESOLVED if _RESOLVED.is_file() else REGION.source)

from conic_replay import (  # noqa: E402
    figures, item4_vdf, item5_vmt_vht, item6_diagnostics, loaders,
)
from conic_replay.config import PERIOD_FACTOR  # noqa: E402

ITER_FOLDER = re.compile(r"^iter(\d+)$")


def discover_runs(replay_root: Path, configs, periods, iterations) -> list:
    """Find every ``runs/<config>/<period>/iter<NN>`` folder that actually ran."""
    found = []
    runs_root = replay_root / "runs"
    for config in configs:
        for period in periods:
            staged = runs_root / config / period
            if not staged.is_dir():
                continue
            for child in sorted(staged.iterdir()):
                match = ITER_FOLDER.match(child.name)
                if not (child.is_dir() and match):
                    continue
                count = int(match.group(1))
                if iterations and count not in iterations:
                    continue
                if not (child / "link_performance.csv").is_file():
                    print(f"  skip {config}/{period}/{child.name}: no link_performance.csv")
                    continue
                found.append({
                    "config": config,
                    "period": period,
                    "label": child.name,
                    "iterations": count,
                    "run_dir": child,
                    "network_dir": replay_root / "network" / "conic" / period,
                })
    return found


def load_all(runs: list) -> list:
    """Join each run's Cube side and TAPlite side, and parse its logs."""
    for run in runs:
        print(f"  loading {run['config']}/{run['period']}/{run['label']} ...")
        run["settings"] = loaders.load_settings(run["run_dir"])
        run["occupancy"] = loaders.occupancy_map(run["run_dir"])
        run["log"] = loaders.parse_summary_log(run["run_dir"])
        run["record"] = loaders.load_run_record(run["run_dir"])
        run["joined"] = loaders.join_run(
            run["network_dir"], run["run_dir"], run["period"]
        )
        # The period length the kernel actually used, from its own settings.csv.
        run["period_hours"] = run["settings"]["_period_hours"]
    return runs


def tag(frame: pd.DataFrame, run: dict) -> pd.DataFrame:
    """Prefix a per-run table with the run identity so tables can be concatenated."""
    frame = frame.copy()
    # Some builders already carry period/run; overwrite in place rather than insert
    # a duplicate, so every table ends up with the same three leading key columns.
    for column, value in (("run", run["label"]), ("period", run["period"]),
                          ("config", run["config"])):
        if column in frame.columns:
            frame[column] = value
            frame.insert(0, column, frame.pop(column))
        else:
            frame.insert(0, column, value)
    return frame


def write(frame: pd.DataFrame, path: Path, manifest: dict) -> None:
    frame.to_csv(path, index=False)
    manifest["outputs"][path.name] = {"rows": int(len(frame)),
                                      "columns": int(frame.shape[1]),
                                      "bytes": path.stat().st_size}
    print(f"    {path.name:<32} {len(frame):>8,} rows  {frame.shape[1]:>3} cols")


def run_item4(runs: list, out_dir: Path, manifest: dict, tables: dict) -> dict:
    print("item 4 - conical replay")
    three_way, summary, regression, register = [], [], [], []
    for run in runs:
        table = item4_vdf.build_three_way(
            run["joined"], run["period"], run["period_hours"]
        )
        run["three_way"] = table
        three_way.append(tag(table, run))
        summary.append(tag(item4_vdf.summarise_three_way(table), run))
        regression.append(tag(item4_vdf.build_regression_ft_at(table), run))
        register.append(tag(item4_vdf.build_missing_parameters(
            run["joined"], table, run["period"], run["period_hours"]), run))

    three_way_table = pd.concat(three_way, ignore_index=True)
    tables["three_way"] = three_way_table
    write(three_way_table, out_dir / "item4_three_way.csv", manifest)
    summary_table = pd.concat(summary, ignore_index=True)
    write(summary_table, out_dir / "item4_three_way_summary.csv", manifest)
    write(pd.concat(regression, ignore_index=True),
          out_dir / "item4_regression_ft_at.csv", manifest)
    structure = pd.concat(
        [tag(item4_vdf.build_residual_structure(run["three_way"]), run) for run in runs],
        ignore_index=True,
    )
    tables["structure"] = structure
    write(structure, out_dir / "item4_residual_structure.csv", manifest)
    register_table = pd.concat(register, ignore_index=True)
    write(register_table, out_dir / "item4_missing_parameters.csv", manifest)

    unexpected = register_table[
        (register_table["severity"] == "error") & (register_table["as_expected"] == False)  # noqa: E712
    ]
    verdict = structure["msa_verdict"].dropna().unique().tolist()
    return {
        "register_error_rows": int(len(unexpected)),
        "register_unexpected": unexpected[["run", "case", "n_links", "expected"]]
            .to_dict("records"),
        "msa_verdict": verdict,
    }


def run_item5(runs: list, out_dir: Path, manifest: dict, tables: dict) -> dict:
    print("item 5 - VMT / VHT / PMT / PHT")
    link_measures, rollup, speed = [], [], []
    for run in runs:
        measures = item5_vmt_vht.build_link_measures(run["joined"], run["occupancy"])
        run["measures"] = measures
        link_measures.append(tag(measures, run))
        corridor = item6_diagnostics.assign_corridors(measures["name"])
        rollup.append(tag(item5_vmt_vht.build_rollup(
            measures, corridor, run["period"]), run))
        speed.append(tag(item5_vmt_vht.build_network_speed(
            measures, run["period"], run["label"]), run))

    write(pd.concat(link_measures, ignore_index=True),
          out_dir / "item5_link_measures.csv", manifest)
    rollup_table = pd.concat(rollup, ignore_index=True)
    tables["rollup"] = rollup_table
    write(rollup_table, out_dir / "item5_rollup.csv", manifest)
    speed_table = pd.concat(speed, ignore_index=True)
    tables["network_speed"] = speed_table
    write(speed_table, out_dir / "item5_network_speed.csv", manifest)

    residual_columns = [c for c in rollup_table.columns if c.startswith("residual_")]
    worst = float(rollup_table[residual_columns].abs().max().max())
    headline = speed_table[
        (speed_table["scope"] == "all_links")
    ][["run", "source", "total_VMT", "total_VHT",
       "network_speed_mph_CORRECT_vmt_over_vht"]].to_dict("records")
    return {"worst_rollup_residual": worst, "network_speed": headline}


def run_item6(runs: list, out_dir: Path, manifest: dict, tables: dict) -> dict:
    print("item 6 - assignment diagnostics")
    convergence = item6_diagnostics.build_convergence(runs)
    tables["convergence"] = convergence
    write(convergence, out_dir / "item6_convergence.csv", manifest)
    runtime = item6_diagnostics.build_runtime(runs)
    write(runtime, out_dir / "item6_runtime.csv", manifest)

    measures_by_run = {
        (run["config"], run["period"], run["label"]): run["measures"]
        for run in runs if "measures" in run
    }
    if measures_by_run:
        corridors = item6_diagnostics.build_corridors(measures_by_run)
        tables["corridors"] = corridors
        write(corridors, out_dir / "item6_corridors.csv", manifest)
        joined_by_run = {
            (run["config"], run["period"], run["label"]): run["joined"] for run in runs
        }
        write(item6_diagnostics.build_corridor_vc(joined_by_run),
              out_dir / "item6_corridor_vc.csv", manifest)
    else:
        print("    corridors skipped: item 5 must run first (needs link measures)")
    return {"runs": runtime[["run", "iterations_requested", "iterations_logged",
                             "final_gap_pct", "cpu_sec"]].to_dict("records")}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--region", type=Path,
                        help="region.yaml (default: the one at the kit root)")
    parser.add_argument("--replay-root", type=Path,
                        help="output folder written by main_convert.py (default: from region)")
    parser.add_argument("--config", nargs="+", default=["LEGACY_CONICAL_REPLAY"])
    parser.add_argument("--periods", nargs="+",
                        help="default: every period in region.yaml that has runs")
    parser.add_argument("--iterations", nargs="*", type=int, default=None,
                        help="restrict to these iteration counts; default is all found")
    parser.add_argument("--items", nargs="+", type=int, default=[4, 5, 6],
                        choices=[4, 5, 6])
    parser.add_argument("--out-dir", type=Path,
                        help="default: <replay-root>/analysis")
    parser.add_argument("--figures", action=argparse.BooleanOptionalAction,
                        default=True, help="write PNG charts into analysis/figures/")
    parser.add_argument("--figure-run",
                        help="which run the per-link charts describe (default: most iterations)")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    replay_root = (args.replay_root or REGION.output_root).resolve()
    if not replay_root.is_dir():
        raise SystemExit(f"ERROR: replay root does not exist: {replay_root}")
    out_dir = (args.out_dir or replay_root / "analysis").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    periods = [p.lower() for p in (args.periods or REGION.periods)]
    items = sorted(set(args.items))
    # Item 6's corridor tables are built from item 5's link measures, so item 5 has
    # to run whenever 6 does. Stated here rather than silently reordered.
    if 6 in items and 5 not in items:
        print("note: item 6 corridors need item 5 link measures; adding item 5")
        items = sorted(set(items) | {5})

    print("=" * 72)
    print(f"region      : {REGION.name}  ({os.environ[REGION_ENV]})")
    print(f"replay root : {replay_root}")
    print(f"output      : {out_dir}")
    print(f"items       : {items}")
    print("=" * 72)

    runs = discover_runs(replay_root, args.config, periods, args.iterations)
    if not runs:
        raise SystemExit("ERROR: no run folders found with a link_performance.csv")
    print(f"{len(runs)} run(s) found")
    started = time.time()
    runs = load_all(runs)
    figure_run = args.figure_run or max(runs, key=lambda r: r["iterations"])["label"]

    manifest = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "replay_root": str(replay_root),
        "items": items,
        "region": REGION.name,
        "region_file": os.environ[REGION_ENV],
        "period_factor_E": PERIOD_FACTOR,
        "runs": [{
            "config": run["config"],
            "period": run["period"],
            "label": run["label"],
            "run_dir": str(run["run_dir"]),
            "network_dir": str(run["network_dir"]),
            "iterations_requested": run["settings"]["_iterations"],
            "period_hours": run["period_hours"],
            "occupancy": run["occupancy"],
            "links": int(len(run["joined"])),
            "kernel_native_sha256": run["record"].get("kernel", {}).get("native_sha256"),
        } for run in runs],
        "outputs": {},
        "headline": {},
    }

    tables: dict = {}
    if 4 in items:
        manifest["headline"]["item4"] = run_item4(runs, out_dir, manifest, tables)
    if 5 in items:
        manifest["headline"]["item5"] = run_item5(runs, out_dir, manifest, tables)
    if 6 in items:
        manifest["headline"]["item6"] = run_item6(runs, out_dir, manifest, tables)

    if args.figures and "three_way" in tables:
        print("figures")
        written = figures.make_all(tables, out_dir / "figures", figure_run)
        manifest["figures"] = [f.name for f in written]
    elif args.figures:
        print("figures skipped: item 4 must run (the charts need its tables)")

    manifest["elapsed_sec"] = round(time.time() - started, 1)
    (out_dir / "ANALYSIS_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print("=" * 72)
    print(f"done in {manifest['elapsed_sec']}s -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
