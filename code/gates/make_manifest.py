"""manifest.csv: path, bytes, sha256, source, script, date for every file in the run folder.

00_raw files: source = the agency file name; script empty. Files listed in 00_raw/EXTERNAL.csv
(too large to copy) appear with their original path. Every other file takes its script from
99_log/produced.csv; a file with no script there is flagged ``script = MISSING``.
_work/ is intermediate and left out.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

import pandas as pd

from .common import KIT_ROOT, PRODUCED, sha256, write_csv

SKIP = {"manifest.csv"}


def commit() -> str:
    try:
        c = subprocess.run(["git", "-C", str(KIT_ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(KIT_ROOT), "status", "--porcelain", "code"],
                               capture_output=True, text=True).stdout.strip()
        return c + ("+uncommitted" if dirty else "")
    except Exception:
        return "unknown"


def run(run_dir: Path) -> Path:
    log = run_dir / "99_log" / PRODUCED
    produced = pd.read_csv(log).set_index("path") if log.exists() else pd.DataFrame()
    rev = commit()
    rows = []
    for p in sorted(run_dir.rglob("*")):
        rel = p.relative_to(run_dir).as_posix()
        if p.is_dir() or rel.startswith("_work/") or p.name in SKIP or p.name.startswith("."):
            continue
        date = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        if rel.startswith("00_raw/"):
            src, script = "agency file, original name", ""
        elif rel in produced.index:
            src, script = produced.loc[rel, "inputs"], f"{produced.loc[rel, 'script']} @ {rev}"
        elif rel.startswith("99_log/") or rel == "README.md":
            src, script = "log / text", ""
        else:
            src, script = "", "MISSING"
        rows.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p),
                     "source": src, "script": script, "date": date})
    ext = run_dir / "00_raw" / "EXTERNAL.csv"
    if ext.exists():
        for r in pd.read_csv(ext).itertuples():
            rows.append({"path": f"(external) {r.original_path}", "bytes": r.bytes, "sha256": r.sha256,
                         "source": "agency file, too large to copy", "script": "", "date": ""})
    path = run_dir / "manifest.csv"
    write_csv(pd.DataFrame(rows), path)
    return path
