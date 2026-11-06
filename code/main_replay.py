"""Step 3 - run the TAPlite assignment on the folders staged by main_convert.py.

Nothing is converted here. The kernel is verified before every run (version, wheel and
native-binary SHA-256 against code/setup/taplite_pypi_lock.json) and refuses to run on
a mismatch.

Run this in the TAPlite environment. The script launches the kernel with the same
Python interpreter that runs it, so that interpreter must have the kernel installed.
It needs only the standard library otherwise -- no PyYAML, no pandas.

    python code/main_replay.py                        # periods and iterations from region
    python code/main_replay.py --periods am --iterations 1 20

Each (config, period, iteration count) gets its own folder:

    <output>/runs/<CONFIG>/<period>/            staged inputs, from main_convert.py
    <output>/runs/<CONFIG>/<period>/iter<NN>/   one assignment: inputs, outputs, record
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
KIT_ROOT = CODE_ROOT.parent
SOURCE_ROOT = CODE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

STAGED_INPUTS = ("node.csv", "link.csv", "settings.csv", "mode_type.csv")
DEFAULT_CONFIG = "LEGACY_CONICAL_REPLAY"


def link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def set_iterations(settings_path: Path, iterations: int, processors: int | None) -> dict:
    with settings_path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    header, values = rows[0], rows[1]
    index = {name: i for i, name in enumerate(header)}
    values[index["number_of_iterations"]] = str(iterations)
    if processors is not None:
        values[index["number_of_processors"]] = str(processors)
    with settings_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerow(values)
    return dict(zip(header, values))


def prepare_iteration_folder(staged: Path, target: Path, iterations: int,
                             processors: int | None) -> dict:
    """Hard-link the staged inputs into an isolated folder for one run."""
    target.mkdir(parents=True, exist_ok=True)
    demand_files = sorted(
        p.name for p in staged.iterdir()
        if p.is_file() and p.suffix == ".csv" and p.name not in STAGED_INPUTS
    )
    for name in (*STAGED_INPUTS, *demand_files):
        source = staged / name
        if not source.is_file():
            raise FileNotFoundError(f"staged input missing: {source}")
        if name == "settings.csv":
            shutil.copy2(source, target / name)   # rewritten per iteration count
        else:
            link_or_copy(source, target / name)
    settings = set_iterations(target / "settings.csv", iterations, processors)
    return {"demand_files": demand_files, "settings": settings}


def run_one(staged: Path, target: Path, iterations: int, processors: int | None) -> dict:
    from dtalite4cube.reproducible_run import (
        parse_convergence, preflight, run_dtalite, verify_outputs,
    )
    from dtalite4cube.taplite_runtime import verify_taplite_runtime

    info = prepare_iteration_folder(staged, target, iterations, processors)
    identity = verify_taplite_runtime()
    pre = preflight(target)
    print(f"  kernel {identity['distribution']}=={identity['installed_version']} "
          f"native {identity['native_sha256'][:16]}...")
    print(f"  running {iterations} iteration(s) in {target}")

    started = time.time()
    elapsed, log = run_dtalite(target, kernel_source="pypi")
    outputs = verify_outputs(target, route_output=0)
    record = {
        "folder": str(target),
        "iterations": iterations,
        "processors": info["settings"].get("number_of_processors"),
        "settings": info["settings"],
        "demand_files": info["demand_files"],
        "kernel": identity,
        "preflight": pre,
        "outputs": outputs,
        "convergence": parse_convergence(log, target),
        "elapsed_sec": elapsed,
        "wall_sec": time.time() - started,
    }
    (target / "RUN_RECORD.json").write_text(json.dumps(record, indent=2, default=str),
                                            encoding="utf-8")
    print(f"  done in {elapsed:.1f}s -> {target / 'link_performance.csv'}")
    return record


def read_resolved(output_root: Path) -> dict:
    path = output_root / "region.resolved.json"
    if not path.is_file():
        raise SystemExit(
            f"ERROR: {path} not found. Run code/main_convert.py first, or pass --output-root "
            "pointing at the folder it wrote."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--output-root", type=Path, default=KIT_ROOT / "data" / "output",
                        help="the output folder main_convert.py wrote")
    parser.add_argument("--config", nargs="+",
                        help=f"default: the run config main_convert.py recorded, else {DEFAULT_CONFIG}")
    parser.add_argument("--periods", nargs="+", help="default: every period in the region")
    parser.add_argument("--iterations", nargs="+", type=int,
                        help="one assignment per value (default: assignment > iterations)")
    parser.add_argument("--processors", type=int,
                        help="default: assignment > processors in the region")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    output_root = args.output_root.resolve()
    resolved = read_resolved(output_root)
    assignment = resolved.get("assignment", {}) or {}
    # Period folders are named as in the region file: am, md ... (NVTA), AM, MD ... (SCAG).
    named = {str(p).lower(): str(p) for p in resolved.get("periods", {})}
    periods = [named.get(p.lower(), p) for p in (args.periods or list(named.values()))]
    configs = args.config or [str((resolved.get("_resolved") or {}).get("run_config", DEFAULT_CONFIG))]
    iterations = args.iterations or [int(v) for v in assignment.get("iterations", [20])]
    processors = args.processors or assignment.get("processors")
    runs_root = output_root / "runs"
    if not runs_root.is_dir():
        raise SystemExit(f"ERROR: no staged runs under {runs_root}. Run main_convert.py first.")

    print("=" * 72)
    print(f"region      : {resolved.get('region', {}).get('name', '?')}")
    print(f"runs        : {runs_root}")
    print(f"periods     : {periods}   iterations: {iterations}   processors: {processors}")
    print("=" * 72)

    records = []
    for config in configs:
        for period in periods:
            staged = runs_root / config / period
            if not staged.is_dir():
                print(f"skip {config}/{period}: not staged (no demand for this period?)")
                continue
            for count in iterations:
                target = staged / f"iter{count:02d}"
                print("-" * 72)
                print(f"{config} / {period} / {count} iteration(s)")
                records.append(run_one(staged, target, count, processors))

    if not records:
        print("nothing ran")
        return 1
    summary = runs_root / "REPLAY_SUMMARY.json"
    summary.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    print("=" * 72)
    print(f"{len(records)} run(s) complete. Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
