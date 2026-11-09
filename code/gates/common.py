"""Shared helpers for the gate scripts: run folder layout, hashing, the produced-file log."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
from pathlib import Path

import pandas as pd
import yaml

KIT_ROOT = Path(__file__).resolve().parents[2]

LAYOUT = {
    "raw": "00_raw",
    "topology": "01_topology",
    "demand": "02_demand",
    "supply": "03_supply",
    "assignment": "04_assignment",
    "counts": "05_counts",
    "congestion": "06_congestion",
    "transit": "07_transit",
    "log": "99_log",
    "work": "_work",          # intermediate files, rebuilt by run_gates.py, not evidence
}

PRODUCED = "produced.csv"     # 99_log/produced.csv: path, script, inputs, time


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def sha256(path: Path, block: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def load_region(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def kit_path(region_file: Path, value: str) -> Path:
    """A path written in the region file, relative to that file."""
    p = Path(value)
    return p if p.is_absolute() else (region_file.parent / p).resolve()


def folder(run: Path, key: str) -> Path:
    d = run / LAYOUT[key]
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def record(run: Path, paths: list[Path], script: str, inputs: str) -> None:
    """Log which script wrote which file; make_manifest.py reads this log."""
    log = folder(run, "log") / PRODUCED
    rows = []
    if log.exists():
        rows = [r for r in csv.DictReader(open(log, encoding="utf-8"))]
    names = {p.relative_to(run).as_posix() for p in paths}
    rows = [r for r in rows if r["path"] not in names]
    rows += [{"path": n, "script": script, "inputs": inputs, "time": today()} for n in sorted(names)]
    with open(log, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "script", "inputs", "time"])
        w.writeheader()
        w.writerows(rows)


def worklog(run: Path, text: str) -> None:
    with open(folder(run, "log") / "worklog.md", "a", encoding="utf-8") as f:
        f.write(f"- {today()}: {text}\n")
