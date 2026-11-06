"""SCAG region file: every path, period, mode and rule the TransCAD converter uses.

``region.yaml`` selects this converter with ``region: {model: transcad_scag}``. The other
modules in this package hold no SCAG numbers: they ask :class:`ScagRegion` for names and
values, and ``region.yaml`` records the source of each value beside it.

**This converter builds a Tier-1 network.** SCAG's trip tables are keyed by Tier-1 TAZ id,
so Tier-1 centroids (facility type 100) carry the zone ids, and the Tier-2 centroid
connectors (facility type 200) and the nodes that only they touch are left out entirely -
they are closed to every mode and carry no loaded flow. A Tier-2 conversion would need a
different zone crosswalk, different demand and its own centroid rules.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MODEL_KEY = "transcad_scag"
REGION_ENV = "CONIC_REPLAY_REGION"
DIRECTIONS = ("AB", "BA")
RESOLVED_NAME = "region.resolved.json"
CLOSED = "closed"
INPUT_KEYS = (
    "network_shapefile", "network_dictionary", "link_capacity_csv", "demand_folder",
    "demand_file", "demand_dictionary", "taz_correspondence", "tier1_taz_shapefile",
    "external_zones",
)
SECTIONS = ("link_fields", "capacity", "modes", "cost_multiplier", "vdf", "access", "zones")
#: What ``output`` controls, and what the converter does when the key is absent.
OUTPUT_DEFAULTS = {
    "keep_closed_links": False,   # write links whose allowed_use is "closed"
    "period_fields_only": True,   # keep only this period's SCAG fields in its link.csv
    "include_daily_fields": True, # keep the seven <measure>_Day fields in every period
    "include_geometry": True,     # write the WKT geometry at all
    # True:  geometry goes to network/link_geometry.csv, one row per link, written once for
    #        every period. link.csv then has no cell over a few hundred characters, so it
    #        opens in Excel and in any CSV reader. 110 links have a WKT longer than Excel's
    #        32,767-character cell limit, which is why this is the default.
    # False: geometry is a column in link.csv, as TAPlite's own schema has it.
    "geometry_separate_file": True,
    "csv_bom": True,              # write CSVs as UTF-8 with BOM, so Excel reads them
}
DEFAULT_AREA_TYPE_MULTIPLIER = 1000


class ScagRegionError(ValueError):
    """A problem in region.yaml, reported with the key that caused it."""


def read_region_file(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ScagRegionError(f"region file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as error:
        raise ScagRegionError(
            f"{path.name} is YAML but PyYAML is not installed in this environment"
        ) from error
    return yaml.safe_load(text) or {}


def is_scag_region(raw: dict) -> bool:
    return str((raw.get("region") or {}).get("model", "")).strip().lower() == MODEL_KEY


def region_file_from_argv(argv: list[str], default: str | Path) -> Path:
    """The region file a driver will use: --region, else $CONIC_REPLAY_REGION, else default."""
    for index, token in enumerate(argv):
        if token == "--region" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if token.startswith("--region="):
            return Path(token.split("=", 1)[1])
    return Path(os.environ.get(REGION_ENV) or default)


def region_is_scag(argv: list[str], default: str | Path) -> bool:
    """True when the drivers should hand over to this package. Any read problem returns
    False, so the Cube path reports it in its own words."""
    try:
        return is_scag_region(read_region_file(region_file_from_argv(argv, default)))
    except Exception:  # noqa: BLE001
        return False


def fill(template: str, *, D: str | None = None, P: str | None = None,
         C: str | None = None) -> str:
    """Replace ``{D}`` (AB/BA), ``{P}`` (period code) and ``{C}`` (flow class) in a name."""
    text = str(template)
    for key, value in (("{D}", D), ("{P}", P), ("{C}", C)):
        if key in text:
            if value is None:
                raise ScagRegionError(f"field template {template!r} needs {key}")
            text = text.replace(key, value)
    return text


@dataclass(frozen=True)
class Mode:
    mode_type: str      # TAPlite mode_type
    core: str           # matrix core name in the .DCC header and the demand dictionary
    flow_class: str     # class name inside the loaded-network flow field names
    group: str          # cost multiplier group, "auto" or "truck"
    pce: float
    occ: float
    cost_factor: float  # distance cost conversion factor, $/h


class ScagRegion:
    def __init__(self, raw: dict, source: str | Path):
        self.raw = raw
        self.source = Path(source).resolve()
        self.base = self.source.parent
        self._output_root: Path | None = None
        self._validate()

    @classmethod
    def load(cls, path: str | Path) -> "ScagRegion":
        return cls(read_region_file(path), path)

    # ---- validation ---------------------------------------------------------
    def _need(self, *keys):
        node = self.raw
        for depth, key in enumerate(keys):
            if not isinstance(node, dict) or key not in node:
                raise ScagRegionError(
                    "region.yaml is missing: " + " > ".join(str(k) for k in keys[: depth + 1]))
            node = node[key]
        return node

    def _validate(self) -> None:
        if not is_scag_region(self.raw):
            raise ScagRegionError(f"region > model must be '{MODEL_KEY}'")
        for key in INPUT_KEYS:
            self._need("input", key)
        self._need("output", "root")
        periods = self._need("periods")
        if not periods:
            raise ScagRegionError("region.yaml has no periods")
        for period, spec in periods.items():
            for key in ("start_hour", "end_hour"):
                if key not in (spec or {}):
                    raise ScagRegionError(f"region.yaml is missing: periods > {period} > {key}")
        for section in SECTIONS:
            self._need(section)
        if self.area_type_multiplier < 1:
            raise ScagRegionError("link_type > area_type_multiplier must be 1 or more")
        unknown = sorted(set(self.raw.get("output", {}) or {}) - set(OUTPUT_DEFAULTS) - {"root"})
        if unknown:
            raise ScagRegionError(
                f"output has unknown key(s) {unknown}; expected {sorted(OUTPUT_DEFAULTS)}")

        names = [str(m.get("mode_type", "")) for m in self.raw["modes"]]
        if len(set(names)) != len(names) or not all(names):
            raise ScagRegionError(f"modes need unique, non-empty mode_type names; got {names}")
        # TAPlite decides allowed_use with a substring search (TAPLite.cpp, allowed_uses.find).
        for a in names:
            for b in names + [CLOSED]:
                if a != b and a in b:
                    raise ScagRegionError(
                        f"mode_type {a!r} is contained in {b!r}; TAPlite matches allowed_use "
                        "by substring, so the two could not be told apart")
        multipliers = self.raw["cost_multiplier"]
        for mode in self.modes:
            if mode.group not in multipliers:
                raise ScagRegionError(
                    f"cost_multiplier has no group {mode.group!r} (mode {mode.mode_type})")
            missing = [p for p in self.periods if p not in multipliers[mode.group]]
            if missing:
                raise ScagRegionError(f"cost_multiplier > {mode.group} is missing {missing}")
        known = set(names)
        for rule in self.access.get("rules", []):
            unknown = sorted(set(rule.get("allowed", [])) - known)
            if unknown:
                raise ScagRegionError(
                    f"access rule {rule.get('name')!r} names unknown modes {unknown}")

    # ---- paths --------------------------------------------------------------
    def path(self, key: str) -> Path:
        value = Path(str(self._need("input", key)))
        return value if value.is_absolute() else (self.base / value).resolve()

    @property
    def name(self) -> str:
        return str(self.raw.get("region", {}).get("name", "SCAG"))

    @property
    def output_root(self) -> Path:
        if self._output_root is not None:
            return self._output_root
        value = Path(str(self._need("output", "root")))
        return value if value.is_absolute() else (self.base / value).resolve()

    @output_root.setter
    def output_root(self, value: str | Path) -> None:
        self._output_root = Path(value).resolve()

    def demand_csv(self, period: str) -> Path:
        return self.path("demand_folder") / fill(self._need("input", "demand_file"), P=period)

    def demand_dcc(self, period: str) -> Path:
        csv = self.demand_csv(period)
        stem = csv.name[:-4] if csv.name.lower().endswith(".csv") else csv.name
        return csv.with_name(stem + ".DCC")

    # ---- periods ------------------------------------------------------------
    @property
    def periods(self) -> dict:
        return {str(k): v for k, v in self._need("periods").items()}

    @property
    def demand_options(self) -> dict:
        """``demand`` in region.yaml. ``min_volume``: cells at or below it are not written."""
        block = self.raw.get("demand") or {}
        unknown = set(block) - {"min_volume"}
        if unknown:
            raise ValueError(f"demand in {self.source.name} has unknown key(s) {sorted(unknown)}")
        minimum = float(block.get("min_volume", 0.0))
        if minimum < 0:
            raise ValueError(f"demand > min_volume must be >= 0; got {minimum}")
        return {"min_volume": minimum}

    def clock_hours(self, period: str) -> float:
        spec = self.periods[period]
        hours = (float(spec["end_hour"]) - float(spec["start_hour"])) % 24
        return hours or 24.0

    def kernel_window(self, period: str) -> tuple[int, int]:
        """Hours written to settings.csv.

        TAPlite takes the period length as a plain subtraction
        (``demand_period_ending_hours - demand_period_starting_hours``), so an overnight
        period is written as hours past midnight: NT 21-6 becomes 21 -> 30. The window then
        has the period's own length, and ``vdf_plf = E / hours`` keeps SCAG's capacity.
        """
        spec = self.periods[period]
        start, end = int(spec["start_hour"]), int(spec["end_hour"])
        return (start, end + 24) if end <= start else (start, end)

    def kernel_hours(self, period: str) -> float:
        start, end = self.kernel_window(period)
        return float(end - start)

    # ---- modes and sections -------------------------------------------------
    @property
    def modes(self) -> list[Mode]:
        return [
            Mode(mode_type=str(m["mode_type"]), core=str(m["core"]),
                 flow_class=str(m["flow_class"]), group=str(m["group"]),
                 pce=float(m["pce"]), occ=float(m["occ"]), cost_factor=float(m["cost_factor"]))
            for m in self.raw["modes"]
        ]

    def vot(self, mode: Mode, period: str) -> float:
        return round(mode.cost_factor * float(self.raw["cost_multiplier"][mode.group][period]), 6)

    def link_field(self, key: str) -> str:
        return str(self._need("link_fields", key))

    @property
    def capacity(self) -> dict:
        return self.raw["capacity"]

    @property
    def vdf(self) -> dict:
        return self.raw["vdf"]

    @property
    def access(self) -> dict:
        return self.raw.get("access", {}) or {}

    @property
    def zones(self) -> dict:
        return self.raw["zones"]

    @property
    def assignment(self) -> dict:
        return self.raw.get("assignment", {}) or {}

    @property
    def output_options(self) -> dict:
        """``output`` in region.yaml, with :data:`OUTPUT_DEFAULTS` filling the gaps."""
        options = dict(OUTPUT_DEFAULTS)
        for key, value in (self.raw.get("output", {}) or {}).items():
            if key in options:
                options[key] = bool(value)
        return options

    @property
    def area_type_multiplier(self) -> int:
        """``link_type = multiplier * area_type + facility_type``.

        1000 for SCAG, whose facility types reach 200; NVTA's Cube converter uses 100 for
        facility types 0-6. Decode with ``divmod(link_type, multiplier)``.
        """
        return int((self.raw.get("link_type", {}) or {}).get(
            "area_type_multiplier", DEFAULT_AREA_TYPE_MULTIPLIER))

    @property
    def run_config(self) -> str:
        return str(self.assignment.get("config_name", "SCAG_VDF_REPLAY"))

    @property
    def resolved_path(self) -> Path:
        return self.output_root / RESOLVED_NAME

    def write_resolved(self, extra: dict | None = None) -> Path:
        """Freeze the configuration beside the outputs it produced."""
        snapshot = json.loads(json.dumps(self.raw, default=str))
        snapshot["input"] = {key: str(self.path(key)) if key != "demand_file"
                             else str(self._need("input", key)) for key in INPUT_KEYS}
        snapshot["output"] = {"root": str(self.output_root)}
        snapshot["_source_region_file"] = str(self.source)
        snapshot["_resolved"] = {"run_config": self.run_config, **(extra or {})}
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.resolved_path.write_text(json.dumps(snapshot, indent=2, default=str),
                                      encoding="utf-8")
        return self.resolved_path
