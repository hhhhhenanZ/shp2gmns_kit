"""SCAG data dictionaries, TransCAD matrix headers, and how SCAG names its fields.

This module is the one place that knows SCAG's field naming, so the notation is documented
here rather than in a generated file.

How a field name is built
-------------------------
``<direction>_<measure>_<period>``, e.g. ``AB_Flow_SR2 HOV_AM``:

``AB_`` / ``BA_``   direction of travel along the line: AB runs from the first vertex to
                    the last, BA is the reverse. A one-way line (``Dir`` 1) carries AB
                    values only.
period suffix       ``AM`` 6-9, ``MD`` 9-15, ``PM`` 15-19, ``EVE`` 19-21, ``NT`` 21-6, and
                    ``Day`` for the daily totals. Lane fields put the period before the
                    word instead: ``AB_AMLANES``, ``AB_EVELANES``.
``LM`` / ``HDT``    vehicle groups in the VMT/VHT/delay fields: light-medium duty vehicles
                    (the five car classes) and heavy duty trucks (the three truck classes).

The eight assigned classes, as SCAG names them
----------------------------------------------
``DA``, ``SR2 HOV``, ``SR3 HOV``, ``SR2 NONHOV``, ``SR3 NONHOV``, ``LIGHT TRUCKS``,
``MEDIUM TRUCKS``, ``HEAVY TRUCKS``. HOV and NONHOV are not different vehicles: SCAG's HOV
diversion model splits each carpool matrix into the share that may use HOV/HOT lanes and
the share confined to general-purpose lanes, so ``SR2 = SR2 HOV + SR2 NONHOV``.

Why names must be looked up
---------------------------
The shapefile export truncates every name to ten characters and disambiguates collisions
with a counter, so the names carry no pattern at all::

    AB_Flow_SR2 HOV_AM     -> AB_FLOW_SR        AB_Flow_SR2 HOV_PM  -> AB_FLOW_S4
    AB_Flow_SR3 HOV_AM     -> AB_FLOW_S1        AB_Flow_SR2 NONHOV_MD -> AB_FLOW_10

``Data_Dictionary_loaded_network.xlsx`` lists both spellings for all 189 fields, in the
same order as the .dbf. ``region.yaml`` is therefore written with the full (DBD) names and
every shapefile column is resolved through :class:`NetworkDictionary`, so no truncated name
is ever typed by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SHP_HEADER = "Field Name in shapefile version"
DBD_HEADER = "Field Name in DBD version"
CORE_HEADER = "Core Name"
_DCC_FIELD = re.compile(r'^"(?P<name>[^"]*)",')

#: SCAG's period codes, in the order the model runs them.
PERIODS = ("AM", "MD", "PM", "EVE", "NT")
DAILY = "Day"
#: The eight assigned classes, as the DBD field names and the matrix cores spell them.
CLASSES = ("DA", "SR2 HOV", "SR3 HOV", "SR2 NONHOV", "SR3 NONHOV",
           "LIGHT TRUCKS", "MEDIUM TRUCKS", "HEAVY TRUCKS")
#: Vehicle groups used by the VMT / VHT / delay fields.
VEHICLE_GROUPS = {"LM": "light-medium duty vehicles (the five car classes)",
                  "HDT": "heavy duty trucks (the three truck classes)"}

_PERIOD_SUFFIX = re.compile(r"_(AM|MD|PM|EVE|NT)$", re.IGNORECASE)
_PERIOD_LANES = re.compile(r"_(AM|MD|PM|EVE|NT)LANES$", re.IGNORECASE)
_DAILY_SUFFIX = re.compile(r"_(Day)$", re.IGNORECASE)


def period_of(dbd_name: str) -> str:
    """The period a DBD field belongs to: ``AM``…``NT``, ``Day``, or ``""`` if it has none.

    Used to keep only the period's own fields in that period's ``link.csv``.
    """
    for pattern in (_PERIOD_SUFFIX, _PERIOD_LANES, _DAILY_SUFFIX):
        match = pattern.search(str(dbd_name))
        if match:
            tag = match.group(1).upper()
            return DAILY if tag == DAILY.upper() else tag
    return ""


def _find_header(frame: pd.DataFrame, label: str) -> tuple[int, int]:
    for row in range(len(frame)):
        for column in range(frame.shape[1]):
            if str(frame.iat[row, column]).strip() == label:
                return row, column
    raise ValueError(f"no '{label}' header found")


class NetworkDictionary:
    """Shapefile name <-> DBD name <-> note, from the loaded-network data dictionary."""

    def __init__(self, entries: pd.DataFrame, source: Path | None = None):
        self.entries = entries.reset_index(drop=True)
        self.source = source
        self._shp_by_dbd = dict(zip(self.entries["dbd"], self.entries["shp"]))
        self._row_by_shp = {shp: row for row, shp in enumerate(self.entries["shp"])}
        self._row_by_dbd = {dbd: row for row, dbd in enumerate(self.entries["dbd"])}

    @classmethod
    def load(cls, path: str | Path) -> "NetworkDictionary":
        frame = pd.read_excel(path, sheet_name=0, header=None, dtype=str)
        row, shp_col = _find_header(frame, SHP_HEADER)
        if str(frame.iat[row, shp_col + 1]).strip() != DBD_HEADER:
            raise ValueError(f"{path}: expected '{DBD_HEADER}' beside '{SHP_HEADER}'")
        body = frame.iloc[row + 1:]
        entries = pd.DataFrame({
            "number": body.iloc[:, shp_col - 1] if shp_col > 0 else "",
            "shp": body.iloc[:, shp_col].str.strip(),
            "dbd": body.iloc[:, shp_col + 1].str.strip(),
            "note": body.iloc[:, shp_col + 2].fillna("").str.strip(),
        }).dropna(subset=["shp", "dbd"])
        return cls(entries, Path(path))

    def shapefile_name(self, dbd_name: str) -> str:
        try:
            return self._shp_by_dbd[dbd_name]
        except KeyError:
            where = self.source.name if self.source else "the network dictionary"
            raise KeyError(f"'{dbd_name}' is not a DBD field name in {where}") from None

    def describe(self, shp_name: str) -> tuple[str, str]:
        """(DBD name, note) for a shapefile field. BA fields borrow the AB field's note."""
        row = self._row_by_shp.get(shp_name)
        if row is None:
            return "", ""
        dbd, note = str(self.entries.at[row, "dbd"]), str(self.entries.at[row, "note"])
        if not note and dbd.startswith("BA_"):
            twin = self._row_by_dbd.get("AB_" + dbd[3:])
            if twin is not None:
                note = str(self.entries.at[twin, "note"])
        return dbd, note


def load_demand_dictionary(path: str | Path) -> pd.DataFrame:
    """Matrix core names and notes from ``Data_Dictionary_OD_Vehicle_trip_matrix.xlsx``."""
    frame = pd.read_excel(path, sheet_name=0, header=None, dtype=str)
    row, core_col = _find_header(frame, CORE_HEADER)
    body = frame.iloc[row + 1:]
    table = pd.DataFrame({
        "core": body.iloc[:, core_col].str.strip(),
        "note": body.iloc[:, core_col + 1].fillna("").str.strip(),
    }).dropna(subset=["core"]).reset_index(drop=True)
    try:
        file_row, file_col = _find_header(frame, "File Name")
        table.attrs["file_name"] = str(frame.iat[file_row, file_col + 1]).strip()
    except ValueError:
        table.attrs["file_name"] = ""
    return table


def read_dcc(path: str | Path) -> list[str]:
    """Column names of a TransCAD CSV export, in order, from its ``.DCC`` header file."""
    names = [match.group("name")
             for line in Path(path).read_text(encoding="latin-1").splitlines()
             if (match := _DCC_FIELD.match(line.strip()))]
    if len(names) < 3:
        raise ValueError(f"{path}: expected two zone columns and at least one core")
    return names
