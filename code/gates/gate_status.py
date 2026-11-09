"""One-line L files for gates that cannot be produced (region file > gates > not_produced).

Each file has one row: gate, status, reason, requested_from, requested_on. When the data
arrives, the gate's own script replaces the file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import load_region, record, worklog, write_csv

SCRIPT = "code/gates/gate_status.py"


def run(region_file: Path, run_dir: Path) -> list[Path]:
    paths = []
    for gate, e in load_region(region_file)["gates"].get("not_produced", {}).items():
        path = run_dir / e["folder"] / e["file"]
        write_csv(pd.DataFrame([{"gate": gate, "status": e["status"], "reason": e["reason"],
                                 "requested_from": e.get("requested_from", ""),
                                 "requested_on": e.get("requested_on", "")}]), path)
        paths.append(path)
    record(run_dir, paths, SCRIPT, "region file gates > not_produced")
    worklog(run_dir, "status files for " + ", ".join(p.stem.split("_")[0] for p in paths))
    return paths
