"""Step 1 for SCAG - check region.yaml against the TransCAD shapefile and trip tables.

Runs from ``code/check_inputs.py`` when ``region.yaml`` has ``model: transcad_scag``.
Exit code 0 when everything passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DIRECTIONS, INPUT_KEYS, REGION_ENV, ScagRegion, ScagRegionError, fill
from .dictionary import NetworkDictionary, load_demand_dictionary, read_dcc

KIT_ROOT = Path(__file__).resolve().parents[3]


def field_names(region: ScagRegion) -> list[str]:
    """Every DBD field name the converter reads."""
    names = []
    for template in region.raw["link_fields"].values():
        template = str(template)
        directions = DIRECTIONS if "{D}" in template else (None,)
        periods = list(region.periods) if "{P}" in template else [None]
        classes = [m.flow_class for m in region.modes] if "{C}" in template else [None]
        names += [fill(template, D=d, P=p, C=c) for d in directions for p in periods for c in classes]
    return sorted(set(names))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", type=Path)
    parser.add_argument("--kernel", action="store_true",
                        help="verify the TAPlite kernel (run inside the TAPlite environment)")
    args = parser.parse_args(argv)
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        results.append((name, bool(ok), detail))
        return bool(ok)

    path = args.region or Path(os.environ.get(REGION_ENV) or KIT_ROOT / "region.yaml")
    try:
        region = ScagRegion.load(path)
        check("region.yaml is complete (SCAG TransCAD)", True,
              f"{region.name}: periods {list(region.periods)}, {len(region.modes)} modes")
    except (ScagRegionError, KeyError, TypeError) as error:
        check("region.yaml is complete (SCAG TransCAD)", False, str(error))
        region = None

    if region is not None:
        files_ok = _check_files(region, check)
        if files_ok:
            _check_network(region, check)
            _check_demand(region, check)
            _check_zones(region, check)
    if args.kernel:
        try:
            from dtalite4cube.taplite_runtime import verify_taplite_runtime
            identity = verify_taplite_runtime()
            check("TAPlite kernel matches code/setup/taplite_pypi_lock.json", True,
                  f"{identity['distribution']}=={identity['installed_version']}")
        except Exception as error:  # noqa: BLE001 - report, do not crash
            check("TAPlite kernel matches code/setup/taplite_pypi_lock.json", False, str(error))

    width = max(len(name) for name, _, _ in results)
    print()
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print()
    print(f"  {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


def _check_files(region: ScagRegion, check) -> bool:
    ok = True
    for key in INPUT_KEYS:
        if key == "demand_file":
            continue
        target = region.path(key)
        ok &= check(f"input > {key}", target.exists(), str(target))
    shp = region.path("network_shapefile")
    siblings = [shp.with_suffix(ext) for ext in (".dbf", ".shx", ".prj")]
    ok &= check("shapefile .dbf .shx .prj beside it", all(p.is_file() for p in siblings),
                ", ".join(p.name for p in siblings if not p.is_file()) or "present")
    return ok


def _check_network(region: ScagRegion, check) -> None:
    import pyogrio

    try:
        dictionary = NetworkDictionary.load(region.path("network_dictionary"))
        check("network data dictionary readable", True, f"{len(dictionary.entries)} fields")
    except Exception as error:  # noqa: BLE001
        check("network data dictionary readable", False, str(error))
        return
    shp = region.path("network_shapefile")
    present = set(pyogrio.read_info(str(shp))["fields"])
    unmapped, absent = [], []
    wanted = field_names(region)
    for name in wanted:
        try:
            column = dictionary.shapefile_name(name)
        except KeyError:
            unmapped.append(name)
            continue
        if column not in present:
            absent.append(f"{name} -> {column}")
    check("link_fields are DBD names in the dictionary", not unmapped,
          f"not found: {unmapped[:8]}" if unmapped else f"{len(wanted)} names")
    check("link_fields exist in the shapefile", not absent,
          f"missing: {absent[:8]}" if absent else "all present")
    undocumented = sorted(present - set(dictionary.entries["shp"]))
    check("every shapefile field is in the dictionary", not undocumented,
          f"not in dictionary: {undocumented}" if undocumented else f"{len(present)} fields")

    cap = region.capacity
    wanted_cap = [cap["id_field"], fill(cap["hourly_capacity_field"], D="AB"),
                  fill(cap["hourly_capacity_field"], D="BA")]
    header = pd.read_csv(region.path("link_capacity_csv"), nrows=0).columns
    missing = [c for c in wanted_cap if c not in header]
    if check("capacity CSV columns", not missing, f"missing: {missing}" if missing else ", ".join(wanted_cap)):
        id_column = dictionary.shapefile_name(region.link_field("id"))
        ids = pyogrio.read_dataframe(str(shp), columns=[id_column], read_geometry=False)[id_column]
        table = pd.read_csv(region.path("link_capacity_csv"), usecols=[cap["id_field"]])
        lacking = np.setdiff1d(ids.to_numpy(), table[cap["id_field"]].to_numpy())
        check("capacity CSV covers every link ID", len(lacking) == 0,
              f"{len(lacking)} IDs missing, e.g. {lacking[:5].tolist()}" if len(lacking)
              else f"{len(ids):,} records")


def _check_demand(region: ScagRegion, check) -> None:
    try:
        listed = set(load_demand_dictionary(region.path("demand_dictionary"))["core"])
        missing = [m.core for m in region.modes if m.core not in listed]
        check("modes are cores in the demand dictionary", not missing,
              f"not listed: {missing}" if missing else ", ".join(m.core for m in region.modes))
    except Exception as error:  # noqa: BLE001
        check("demand data dictionary readable", False, str(error))
    for period in region.periods:
        csv, dcc = region.demand_csv(period), region.demand_dcc(period)
        if not check(f"{period} trip table and .DCC", csv.is_file() and dcc.is_file(),
                     f"{csv.name}, {dcc.name}"):
            continue
        cores = read_dcc(dcc)[2:]
        missing = [m.core for m in region.modes if m.core not in cores]
        check(f"{period} matrix cores", not missing,
              f"missing: {missing}; found {cores}" if missing else f"{len(cores)} cores")


def _check_zones(region: ScagRegion, check) -> None:
    import pyogrio

    from .zones import load_crosswalk, read_special_zones

    try:
        crosswalk = load_crosswalk(region)
        check("Tier-1 TAZ correspondence is one-to-one", True,
              f"{len(crosswalk):,} zones: {crosswalk['zone_type'].value_counts().to_dict()}")
    except Exception as error:  # noqa: BLE001
        check("Tier-1 TAZ correspondence is one-to-one", False, str(error))
    try:
        specials = read_special_zones(region.path("external_zones"),
                                      region.zones["external_zones_sheet"])
        check("External Zone IDs.xlsx readable", True, f"{len(specials)} cordon, airport and port zones")
    except Exception as error:  # noqa: BLE001
        check("External Zone IDs.xlsx readable", False, str(error))
    polygon_fields = pyogrio.read_info(str(region.path("tier1_taz_shapefile")))["fields"]
    field = region.zones["tier1_zone_field"]
    check("Tier-1 TAZ polygons have the zone field", field in polygon_fields, field)
