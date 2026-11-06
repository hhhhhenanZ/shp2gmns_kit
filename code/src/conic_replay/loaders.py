"""Read the Cube-side network and the TAPlite-side outputs and join them.

Read-only. Nothing here writes into a run folder.

Field names come from the region. Right after reading, region-specific names are
renamed to the canonical columns the analysis modules use (``FTYPE``, ``TOLLGRP``,
``JUR``, ``STREETNAME``, ``cube_*``), so the modules themselves never see a
network-specific name.

The join is on ``link_id``. ``ref_volume`` in ``link_performance.csv`` is Cube's own
assigned volume, put there by the conic overlay; the join brings across the Cube
fields the kernel does not echo (V/C, travel-time ratio, speed, capacity, mode volumes).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd

from .config import (
    CANONICAL_COLUMNS,
    CUBE_FIELDS,
    CUBE_MODE_FIELDS,
    LINK_PERFORMANCE,
    LINK_TYPE_ATYPE_DIVISOR,
    MODE_TYPE,
    MODES,
    RUN_RECORD,
    SETTINGS,
    SUMMARY_LOG,
    TAPLITE_MODE_COLUMNS,
)

# GMNS columns every conic link.csv carries.
GMNS_KEEP = [
    "link_id", "from_node_id", "to_node_id", "name", "lanes", "capacity",
    "free_speed", "length", "length_in_mile", "vdf_free_speed_mph",
    "vdf_length_mi", "vdf_fftt", "vdf_type", "vdf_alpha", "vdf_beta", "vdf_plf",
    "ref_volume", "link_type", "allowed_use",
]
GMNS_NUMERIC = [
    "link_id", "from_node_id", "to_node_id", "lanes", "capacity", "free_speed",
    "length", "length_in_mile", "vdf_free_speed_mph", "vdf_length_mi", "vdf_fftt",
    "vdf_type", "vdf_alpha", "vdf_beta", "vdf_plf", "ref_volume", "link_type",
]
CANONICAL_NUMERIC = ["FTYPE", "TOLLGRP"]

PERFORMANCE_KEEP = [
    "link_id", "iteration_no", "volume", "ref_volume", "link_capacity",
    "lane_capacity", "doc", "vdf_fftt", "travel_time", "vdf_alpha", "vdf_beta",
    "vdf_plf", "speed_mph", "VMT", "VHT", "PMT", "PHT",
] + list(TAPLITE_MODE_COLUMNS.values())


def load_network(network_dir: Path, period: str) -> pd.DataFrame:
    """Read the conic ``link.csv``, canonicalise names, decode area type."""
    path = Path(network_dir) / "link.csv"
    if not path.is_file():
        raise FileNotFoundError(f"conic network link.csv not found: {path}")
    fields = CUBE_FIELDS[period]
    modes = CUBE_MODE_FIELDS[period]
    wanted = GMNS_KEEP + list(CANONICAL_COLUMNS) + list(fields.values()) + list(modes.values())
    wanted = list(dict.fromkeys(wanted))

    header = pd.read_csv(path, nrows=0).columns.tolist()
    missing = [column for column in wanted if column not in header]
    if missing:
        raise KeyError(
            f"{path} is missing columns: {missing}. Check cube_fields and "
            "mode_volume_fields in region.yaml."
        )

    frame = pd.read_csv(path, usecols=wanted, dtype=str, keep_default_na=False)
    frame = frame.rename(columns=CANONICAL_COLUMNS)
    for column in GMNS_NUMERIC + CANONICAL_NUMERIC + list(fields.values()) + list(modes.values()):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # link_type = divisor * area type + FTYPE; the decode is asserted, not assumed.
    atype = frame["link_type"] // LINK_TYPE_ATYPE_DIVISOR
    mismatch = int(((frame["link_type"] % LINK_TYPE_ATYPE_DIVISOR) != frame["FTYPE"]).sum())
    if mismatch:
        raise ValueError(
            f"link_type does not decode to facility type on {mismatch} links; the "
            f"{LINK_TYPE_ATYPE_DIVISOR}*ATYPE+FTYPE convention does not hold"
        )
    frame["ATYPE_CODE"] = atype.astype("Int64")
    frame["period_limit"] = pd.to_numeric(frame[fields["limit"]], errors="coerce").astype("Int64")

    renames = {value: f"cube_{key}" for key, value in fields.items()}
    renames.update({value: f"cube_vol_{key}" for key, value in modes.items()})
    return frame.rename(columns=renames)


def load_link_performance(run_dir: Path) -> pd.DataFrame:
    """Read ``link_performance.csv``, keeping only the final iteration's rows."""
    path = Path(run_dir) / LINK_PERFORMANCE
    if not path.is_file():
        raise FileNotFoundError(f"link_performance.csv not found: {path}")
    header = pd.read_csv(path, nrows=0).columns.tolist()
    wanted = [column for column in PERFORMANCE_KEEP if column in header]
    missing = [column for column in PERFORMANCE_KEEP if column not in header]
    frame = pd.read_csv(path, usecols=wanted)
    if "iteration_no" in frame.columns and frame["iteration_no"].nunique() > 1:
        frame = frame[frame["iteration_no"] == frame["iteration_no"].max()]
    frame = frame.rename(columns={
        column: f"tap_{column}" for column in frame.columns if column != "link_id"
    })
    frame.attrs["missing_columns"] = missing
    return frame


def load_mode_type(run_dir: Path) -> pd.DataFrame:
    """Read ``mode_type.csv`` -- the authority for vot, pce and occupancy."""
    path = Path(run_dir) / MODE_TYPE
    if not path.is_file():
        raise FileNotFoundError(f"mode_type.csv not found: {path}")
    frame = pd.read_csv(path)
    for column in ("vot", "pce", "occ"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    unknown = sorted(set(frame["mode_type"]) - set(MODES))
    if unknown:
        raise ValueError(f"mode_type.csv carries unexpected modes: {unknown}")
    return frame


def occupancy_map(run_dir: Path) -> dict:
    frame = load_mode_type(run_dir)
    return dict(zip(frame["mode_type"], frame["occ"]))


def load_settings(run_dir: Path) -> dict:
    """Read the one-row ``settings.csv`` and derive the assignment period length."""
    path = Path(run_dir) / SETTINGS
    if not path.is_file():
        raise FileNotFoundError(f"settings.csv not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    settings = dict(zip(rows[0], rows[1]))
    start = float(settings["demand_period_starting_hours"])
    end = float(settings["demand_period_ending_hours"])
    hours = end - start
    if hours <= 0:
        hours += 24.0
    settings["_period_hours"] = hours
    settings["_iterations"] = int(settings["number_of_iterations"])
    settings["_processors"] = int(settings["number_of_processors"])
    return settings


def load_run_record(run_dir: Path) -> dict:
    path = Path(run_dir) / RUN_RECORD
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


ITERATION_PATTERN = re.compile(
    r"iter No\s*=\s*(\d+),\s*Lambda\s*=\s*([-\d.eE+]+),"
    r"\s*g_System_VMT\s*=\s*([-\d.eE+]+),"
    r"\s*sys\. TT\s*=\s*([-\d.eE+]+),"
    r"\s*least TT\s*=\s*([-\d.eE+]+),"
    r"\s*gap\s*=\s*([-\d.eE+]+)\s*%,"
    r"\s*elapsed\s*=\s*([-\d.eE+]+)\s*s"
)
SETUP_PATTERN = re.compile(r"SETUP[^=]*=\s*([\d.]+)\s*s")
CPU_PATTERN = re.compile(
    r"CPU running time:\s*(\d+)\s*hours?\s*(\d+)\s*minutes?\s*(\d+)\s*seconds?\s*(\d+)\s*ms"
)
MODE_VOLUME_PATTERN = re.compile(r"mode type\s*=\s*(\w+),\s*total_volume\s*=\s*([\d.]+)")
NETWORK_PATTERN = re.compile(
    r"no_nodes=\s*(\d+),\s*no_zones\s*=\s*(\d+).*?number_of_links\s*=\s*(\d+)"
)


def parse_summary_log(run_dir: Path) -> dict:
    """Parse ``summary_log_file.txt`` for convergence, timing and loaded demand.

    A one-iteration run emits no ``iter No =`` line -- a relative gap needs a previous
    solution -- so ``iterations`` is empty. That is a property of the run, not a parse
    failure.
    """
    path = Path(run_dir) / SUMMARY_LOG
    if not path.is_file():
        raise FileNotFoundError(f"summary_log_file.txt not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")

    iterations = []
    previous_elapsed = 0.0
    for match in ITERATION_PATTERN.finditer(text):
        elapsed = float(match.group(7))
        iterations.append({
            "iteration": int(match.group(1)),
            "lambda": float(match.group(2)),
            "system_vmt": float(match.group(3)),
            "system_travel_time": float(match.group(4)),
            "least_travel_time": float(match.group(5)),
            "relative_gap_pct": float(match.group(6)),
            "cumulative_elapsed_sec": elapsed,
            "iteration_elapsed_sec": elapsed - previous_elapsed,
        })
        previous_elapsed = elapsed

    setup = SETUP_PATTERN.search(text)
    cpu = CPU_PATTERN.search(text)
    cpu_seconds = None
    if cpu:
        hours, minutes, seconds, milliseconds = (int(g) for g in cpu.groups())
        cpu_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    network = NETWORK_PATTERN.search(text)

    return {
        "iterations": iterations,
        "setup_sec": float(setup.group(1)) if setup else None,
        "cpu_sec": cpu_seconds,
        "loaded_mode_volume": {
            mode: float(volume) for mode, volume in MODE_VOLUME_PATTERN.findall(text)
        },
        "nodes": int(network.group(1)) if network else None,
        "zones": int(network.group(2)) if network else None,
        "links": int(network.group(3)) if network else None,
    }


def join_run(network_dir: Path, run_dir: Path, period: str) -> pd.DataFrame:
    """Cube side + TAPlite side, one row per link, joined on ``link_id``."""
    network = load_network(network_dir, period)
    performance = load_link_performance(run_dir)
    merged = network.merge(performance, on="link_id", how="left", validate="one_to_one")

    unmatched = int(merged["tap_volume"].isna().sum()) if "tap_volume" in merged else len(merged)
    if unmatched:
        raise ValueError(f"{unmatched} of {len(merged)} links have no row in link_performance.csv")
    merged.attrs["missing_performance_columns"] = performance.attrs.get("missing_columns", [])

    # ref_volume reaches this frame twice: the overlay's column and the kernel's echo.
    # Agreement proves the kernel read the column the overlay wrote.
    merged["ref_volume_echo_delta"] = (merged["ref_volume"] - merged["tap_ref_volume"]).abs()
    return merged
