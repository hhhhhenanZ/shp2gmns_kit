"""settings.csv and mode_type.csv for a staged TAPlite run folder.

The column lists come from the kit's own settings generator
(``dtalite4cube/settings/dtalite_settings_config.py``), so SCAG and NVTA run folders share
one schema. Only the values differ: SCAG periods and modes from ``region.yaml``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from dtalite4cube.settings.dtalite_settings_config import (
    DEFAULT_SETTINGS,
    MODE_TYPE_FILENAME,
    MODE_TYPE_HEADER,
    SETTINGS_FILENAME,
    SETTINGS_HEADER,
)

from .demand import demand_file_name


def mode_type_rows(region, period: str) -> list[dict]:
    return [
        {"mode_type_id": number, "mode_type": mode.mode_type, "name": mode.core,
         "vot": region.vot(mode, period), "pce": mode.pce, "occ": mode.occ,
         "demand_file": demand_file_name(mode.mode_type, period)}
        for number, mode in enumerate(region.modes, start=1)
    ]


def settings_row(region, period: str, iterations: int, processors: int) -> dict:
    start, end = region.kernel_window(period)
    row = dict(DEFAULT_SETTINGS)
    row.update(number_of_iterations=int(iterations), number_of_processors=int(processors),
               demand_period_starting_hours=start, demand_period_ending_hours=end)
    return row


def _write(path: Path, header: list[str], rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # "\n" only: TAPlite does not strip a trailing CR from the last field of a row.
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_run_files(folder: Path, region, period: str, iterations: int, processors: int) -> dict:
    return {
        SETTINGS_FILENAME: str(_write(folder / SETTINGS_FILENAME, SETTINGS_HEADER,
                                      [settings_row(region, period, iterations, processors)])),
        MODE_TYPE_FILENAME: str(_write(folder / MODE_TYPE_FILENAME, MODE_TYPE_HEADER,
                                       mode_type_rows(region, period))),
    }
