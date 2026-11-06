"""TransCAD CSV trip tables -> one TAPlite demand file per mode and period.

Each ``<P>_OD.mtx.csv`` is a TransCAD export without a header row. Its ``.DCC`` file names
the columns: origin TAZ, destination TAZ, then one column per matrix core (DA, SR2 HOV,
SR3 HOV, LHDT, MHDT, HHDT, SR2 NONHOV, SR3 NONHOV). Values are vehicle trips
(``Data_Dictionary_OD_Vehicle_trip_matrix.xlsx``).

Output ``<mode_type>_<P>.csv``: ``o_zone_id,d_zone_id,volume``. Zone ids are the Tier-1
internal sequence (``TAZ_seq_t1``). Volumes are copied exactly as written in the source.
Intrazonal cells are kept. Cells whose origin or destination zone has no centroid are
counted as dropped.

``demand > min_volume`` in region.yaml is a floor on what is written: a cell at or below it
is left out and counted under ``below_min_volume_*``, so the retained share of trips is on
the record for every mode and period. Trip ends used to locate zone centroids are taken
from the unfiltered matrix.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from .dictionary import read_dcc

HEADER = "o_zone_id,d_zone_id,volume\n"
ZONE_COLUMNS = ["o_taz", "d_taz"]


def demand_file_name(mode_type: str, period: str) -> str:
    return f"{mode_type}_{period}.csv"


def matrix_columns(region, period: str) -> list[str]:
    dcc = region.demand_dcc(period)
    cores = read_dcc(dcc)[2:]
    missing = [mode.core for mode in region.modes if mode.core not in cores]
    if missing:
        raise ValueError(f"{dcc.name} has no core(s) {missing}; it lists {cores}")
    return [*ZONE_COLUMNS, *cores]


def trip_ends(region, period: str, crosswalk: pd.DataFrame, chunksize: int):
    """Trips produced and attracted by each zone, per mode, intrazonal cells excluded."""
    columns = matrix_columns(region, period)
    cores = [mode.core for mode in region.modes]
    dtypes = {"o_taz": np.int64, "d_taz": np.int64, **{c: np.float64 for c in columns[2:]}}
    origins = destinations = None
    rows, intrazonal = 0, 0.0
    for chunk in pd.read_csv(region.demand_csv(period), header=None, names=columns,
                             dtype=dtypes, chunksize=chunksize):
        rows += len(chunk)
        same = (chunk["o_taz"] == chunk["d_taz"]).to_numpy()
        intrazonal += float(chunk.loc[same, cores].to_numpy().sum())
        part = chunk.loc[~same]
        o = part.groupby("o_taz")[cores].sum()
        d = part.groupby("d_taz")[cores].sum()
        origins = o if origins is None else origins.add(o, fill_value=0.0)
        destinations = d if destinations is None else destinations.add(d, fill_value=0.0)
    zone_of = dict(zip(crosswalk["taz_id"].astype(np.int64), crosswalk["zone_id"].astype(np.int64)))
    unknown = sorted((set(origins.index) | set(destinations.index)) - set(zone_of))
    if unknown:
        raise ValueError(f"{region.demand_csv(period).name}: TAZ ids not in the correspondence "
                         f"file: {unknown[:10]}")
    rename = {mode.core: mode.mode_type for mode in region.modes}
    origins = origins.rename(index=zone_of, columns=rename)
    destinations = destinations.rename(index=zone_of, columns=rename)
    return origins, destinations, {"matrix_rows": rows, "intrazonal_trips": intrazonal}


def convert_period(region, period: str, crosswalk: pd.DataFrame, zone_of_taz: dict,
                   out_dir: Path, chunksize: int) -> dict:
    columns = matrix_columns(region, period)
    source = region.demand_csv(period)
    known = set(crosswalk["taz_id"].astype(np.int64))
    minimum = float(region.demand_options["min_volume"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {mode.mode_type: {"file": demand_file_name(mode.mode_type, period), "core": mode.core,
                              "rows": 0, "trips": 0.0, "intrazonal_trips": 0.0,
                              "dropped_rows": 0, "dropped_trips": 0.0, "negative_cells": 0,
                              "min_volume": minimum,
                              "below_min_volume_rows": 0, "below_min_volume_trips": 0.0,
                              "positive_rows": 0, "positive_trips": 0.0}
             for mode in region.modes}
    started = time.perf_counter()
    matrix_rows = 0
    handles = {}
    try:
        for mode in region.modes:
            handle = open(out_dir / stats[mode.mode_type]["file"], "w", newline="", encoding="utf-8")
            handle.write(HEADER)
            handles[mode.mode_type] = handle
        dtypes = {"o_taz": np.int64, "d_taz": np.int64, **{c: str for c in columns[2:]}}
        for chunk in pd.read_csv(source, header=None, names=columns, dtype=dtypes,
                                 chunksize=chunksize, keep_default_na=False):
            matrix_rows += len(chunk)
            strange = ~chunk["o_taz"].isin(known) | ~chunk["d_taz"].isin(known)
            if strange.any():
                raise ValueError(f"{source.name}: TAZ ids not in the correspondence file, e.g. "
                                 f"{chunk.loc[strange, ZONE_COLUMNS].head(3).to_numpy().tolist()}")
            o_zone = chunk["o_taz"].map(zone_of_taz)
            d_zone = chunk["d_taz"].map(zone_of_taz)
            located = (o_zone.notna() & d_zone.notna()).to_numpy()
            same = (chunk["o_taz"] == chunk["d_taz"]).to_numpy()
            for mode in region.modes:
                text = chunk[mode.core].str.strip()
                value = pd.to_numeric(text, errors="raise").to_numpy(dtype=float)
                record = stats[mode.mode_type]
                record["negative_cells"] += int((value < 0).sum())
                positive = value > 0
                # min_volume is a floor on what is written; the cells it removes are
                # counted so the retained share of SCAG's trips stays on the record.
                large = value > minimum
                small = positive & ~large
                record["positive_rows"] += int(positive.sum())
                record["positive_trips"] += float(value[positive].sum())
                record["below_min_volume_rows"] += int(small.sum())
                record["below_min_volume_trips"] += float(value[small].sum())
                keep = large & located
                dropped = large & ~located
                record["rows"] += int(keep.sum())
                record["trips"] += float(value[keep].sum())
                record["intrazonal_trips"] += float(value[keep & same].sum())
                record["dropped_rows"] += int(dropped.sum())
                record["dropped_trips"] += float(value[dropped].sum())
                if keep.any():
                    pd.DataFrame({
                        "o": o_zone.to_numpy()[keep].astype(np.int64),
                        "d": d_zone.to_numpy()[keep].astype(np.int64),
                        "v": text.to_numpy()[keep],
                    }).to_csv(handles[mode.mode_type], header=False, index=False, lineterminator="\n")
    finally:
        for handle in handles.values():
            handle.close()
    return {"period": period, "source": str(source), "matrix_rows": matrix_rows,
            "elapsed_sec": time.perf_counter() - started, "modes": stats}
