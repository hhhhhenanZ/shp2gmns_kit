"""Copy the small evidence files of a run folder into the repository: gate_runs/<run folder name>/.

Copied: README.md, manifest.csv, 00_raw/EXTERNAL.csv, every L<n> file, the small tables that
the L files point to (capacity_lookup.csv, zone_split.csv, settings.yaml, settings.csv,
mode_type.csv), 99_log/*.md and, if a rerun folder exists next to the run folder, its
rerun_compare.csv. Large data files (network, demand, link_performance) stay in the run
folder; manifest.csv holds their sha256, so a rerun can be checked against them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .common import KIT_ROOT

SMALL = {"capacity_lookup.csv", "zone_split.csv", "settings.yaml", "settings.csv", "mode_type.csv", "EXTERNAL.csv"}
MAX_BYTES = 2_000_000


def run(run_dir: Path, repo: Path | None = None) -> Path:
    repo = repo or KIT_ROOT
    dst_root = repo / "gate_runs" / run_dir.name
    copied = []
    for p in sorted(run_dir.rglob("*")):
        rel = p.relative_to(run_dir)
        if p.is_dir() or rel.parts[0] == "_work" or p.name.startswith("."):
            continue
        keep = (rel.as_posix() in ("README.md", "manifest.csv")
                or (p.name.startswith("L") and p.name[1:2].isdigit())
                or p.name in SMALL
                or (rel.parts[0] == "99_log" and p.suffix == ".md"))
        if keep and p.stat().st_size <= MAX_BYTES:
            d = dst_root / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, d)
            copied.append(rel.as_posix())
    rc = run_dir.parent / f"{run_dir.name}_rerun" / "rerun_compare.csv"
    if rc.exists():
        (dst_root / "99_log").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rc, dst_root / "99_log" / "rerun_compare.csv")
        copied.append("99_log/rerun_compare.csv")
    print(f"  {len(copied)} files -> {dst_root}")
    return dst_root
