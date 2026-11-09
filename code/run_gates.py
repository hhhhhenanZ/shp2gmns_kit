"""Build a gate run folder from the agency files: one L file per gate.

    python code/run_gates.py --region region.cmap.yaml --run ../cmap_2019_pm
    python code/run_gates.py --region region.cmap.yaml --run ../cmap_2019_pm --steps L0 L1 manifest

Steps, in order: raw, convert, publish, demand, L0, L1, L2, L3build, L3run, L3, status, manifest, export (default: all).
The demand step stops after a time budget and resumes where it stopped; exit code 2 = run again.
Gates L2-L5 are added as they are built. Layout and rules: code/gates/README.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gates import export, gate_L0, gate_L1, gate_L2, gate_L3, gate_status, make_manifest, prepare, scag_gates  # noqa: E402
from gates.common import load_region  # noqa: E402

STEPS = ["raw", "convert", "publish", "demand", "L0", "L1", "L2", "L3build", "L3run", "L3", "status", "manifest", "export"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True, help="run folder, e.g. ../cmap_2019_pm")
    ap.add_argument("--steps", nargs="+", default=STEPS, choices=STEPS)
    ap.add_argument("--data-root", type=Path, default=None,
                    help="SCAG: kit folder holding data/input and data/output (default: the region file's folder)")
    ap.add_argument("--conversion", default=None,
                    help="SCAG: conversion folder relative to --data-root (default: region.yaml > gates > conversion)")
    a = ap.parse_args()
    region, run = a.region.resolve(), a.run.resolve()
    run.mkdir(parents=True, exist_ok=True)
    cfg = load_region(region)
    period = cfg["gates"]["period"]
    if cfg["region"]["model"] == "transcad_scag":
        return run_scag(a, region, run, period)
    for s in STEPS:
        if s not in a.steps:
            continue
        print(f"== {s}")
        if s == "raw":
            prepare.step_raw(region, run)
        elif s == "convert":
            prepare.step_convert(region, run, period)
        elif s == "publish":
            prepare.step_publish(region, run, period)
        elif s == "demand":
            if not prepare.step_demand(region, run, period):
                return 2          # not finished: run again with --steps demand ...
        elif s == "L0":
            print("  ", gate_L0.run(region, run, period))
        elif s == "L1":
            print("  ", gate_L1.run(region, run, period))
        elif s == "L2":
            print("  ", gate_L2.run(region, run, period))
        elif s == "L3build":
            print("  ", gate_L3.build(region, run, period))
        elif s == "L3run":
            gate_L3.run(region, run)
        elif s == "L3":
            print("  ", gate_L3.summarize(region, run))
        elif s == "status":
            print("  ", gate_status.run(region, run))
        elif s == "manifest":
            print("  ", make_manifest.run(run))
        elif s == "export":
            export.run(run)
    return 0


SCAG_STEPS = ["raw", "publish", "L0", "L1", "L2", "L3", "status", "manifest", "export"]


def run_scag(a, region: Path, run: Path, period: str) -> int:
    """SCAG: steps raw, publish, L0, L1, L2, L3, status, manifest. Exit code 2 = run again."""
    root = (a.data_root or region.parent).resolve()
    if a.conversion:
        scag_gates.CONVERSION_OVERRIDE = a.conversion
    for s in SCAG_STEPS:
        if s not in a.steps:
            continue
        print(f"== {s}")
        if s == "raw" and not scag_gates.step_raw(region, root, run):
            return 2
        if s == "publish":
            scag_gates.step_publish(region, root, run, period)
        if s == "L0" and not scag_gates.step_L0(region, root, run, period):
            return 2
        if s == "L1" and not scag_gates.step_L1(region, root, run, period):
            return 2
        if s == "L2":
            print("  ", scag_gates.step_L2(region, root, run, period))
        if s == "L3":
            print("  ", scag_gates.step_L3(region, root, run, period))
        if s == "status":
            print("  ", gate_status.run(region, run))
        if s == "manifest":
            print("  ", make_manifest.run(run))
        if s == "export":
            export.run(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
