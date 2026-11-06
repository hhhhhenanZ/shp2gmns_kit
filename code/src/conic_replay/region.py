"""Read ``region.yaml`` and answer every region-specific question the kit asks.

One object, :class:`Region`, holds the configuration. Everything downstream asks it
for paths and field names instead of hard-coding them, so a new network is a new
``region.yaml`` rather than a code change.

Two file forms are accepted:

``region.yaml``            what a person edits (needs PyYAML)
``region.resolved.json``   written by ``main_convert.py`` into the output folder, with
                           every path made absolute. Readable with the standard
                           library, so the assignment environment needs no PyYAML.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REGION_ENV = "CONIC_REPLAY_REGION"
KIT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGION_FILE = KIT_ROOT / "region.yaml"

VALID_PERIODS = ("am", "md", "pm", "nt")
MODES = ("sov", "hov2", "hov3", "com", "trk", "apv")
CUBE_FIELD_KEYS = (
    "volume", "vc_ratio", "travel_time_ratio", "speed", "free_speed", "vmt",
    "link_capacity", "lane_capacity", "limit",
)
STATIC_FIELD_KEYS = ("street_name", "toll_group", "jurisdiction")

RESOLVED_NAME = "region.resolved.json"
PARAMETERS_DIR = "parameters"
ALPHA_TABLE_NAME = "alpha_by_ft_at.csv"
PERIOD_FACTOR_NAME = "period_factor.csv"


class RegionError(ValueError):
    """A problem in region.yaml, reported with the key that caused it."""


def _read(path: Path) -> dict:
    if not path.is_file():
        raise RegionError(f"region file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as error:
        raise RegionError(
            f"{path.name} is YAML but PyYAML is not installed in this environment. "
            f"Install it, or point to {RESOLVED_NAME} in the output folder instead."
        ) from error
    return yaml.safe_load(text) or {}


class Region:
    def __init__(self, raw: dict, source: Path):
        self.raw = raw
        self.source = Path(source).resolve()
        # Relative paths in region.yaml are relative to the file itself.
        self.base = self.source.parent
        self._validate()

    # ---- construction -------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Region":
        path = Path(path or os.environ.get(REGION_ENV) or DEFAULT_REGION_FILE)
        return cls(_read(path), path)

    def _need(self, *keys):
        node = self.raw
        for depth, key in enumerate(keys):
            if not isinstance(node, dict) or key not in node:
                raise RegionError("region.yaml is missing: " + " > ".join(keys[: depth + 1]))
            node = node[key]
        return node

    def _validate(self) -> None:
        self._need("input", "network_shapefile")
        self._need("input", "demand_folder")
        self._need("output", "root")
        periods = self._need("periods")
        unknown = sorted(set(periods) - set(VALID_PERIODS))
        if unknown:
            raise RegionError(
                f"periods {unknown} are not supported; use am, md, pm or nt. Other period "
                "names need converter changes (see README, 'Networks with different field names')."
            )
        for period, spec in periods.items():
            for key in ("start_hour", "end_hour"):
                if key not in (spec or {}):
                    raise RegionError(f"region.yaml is missing: periods > {period} > {key}")
        fields = self._need("cube_fields")
        for key in CUBE_FIELD_KEYS + STATIC_FIELD_KEYS:
            if key not in fields:
                raise RegionError(f"region.yaml is missing: cube_fields > {key}")
        missing_modes = sorted(set(MODES) - set(self._need("mode_volume_fields")))
        if missing_modes:
            raise RegionError(f"mode_volume_fields is missing modes: {missing_modes}")
        mode_types = self._need("mode_types")
        for period in periods:
            if period not in mode_types:
                raise RegionError(f"region.yaml is missing: mode_types > {period}")
            listed = {row.get("mode") for row in mode_types[period]}
            if listed != set(MODES):
                raise RegionError(
                    f"mode_types > {period} must list exactly {list(MODES)}; got {sorted(listed)}"
                )

    # ---- paths --------------------------------------------------------------
    def _path(self, value) -> Path:
        path = Path(str(value))
        return path if path.is_absolute() else (self.base / path).resolve()

    @property
    def name(self) -> str:
        return str(self.raw.get("region", {}).get("name", "region"))

    @property
    def network_shapefile(self) -> Path:
        return self._path(self._need("input", "network_shapefile"))

    @property
    def demand_folder(self) -> Path:
        return self._path(self._need("input", "demand_folder"))

    @property
    def output_root(self) -> Path:
        return self._path(self._need("output", "root"))

    @property
    def parameters_dir(self) -> Path:
        return self.output_root / PARAMETERS_DIR

    @property
    def alpha_table_path(self) -> Path:
        configured = self.conic.get("alpha_table", "derive")
        if configured and str(configured).lower() != "derive":
            return self._path(configured)
        return self.parameters_dir / ALPHA_TABLE_NAME

    @property
    def derive_alpha(self) -> bool:
        return str(self.conic.get("alpha_table", "derive")).lower() == "derive"

    @property
    def period_factor_path(self) -> Path:
        return self.parameters_dir / PERIOD_FACTOR_NAME

    @property
    def resolved_path(self) -> Path:
        return self.output_root / RESOLVED_NAME

    # ---- periods and fields -------------------------------------------------
    @property
    def periods(self) -> dict:
        return {str(k).lower(): v for k, v in self._need("periods").items()}

    def period_hours(self, period: str) -> float:
        """Hours TAPlite actually assigns. A cross-midnight period is cut at 24:00."""
        spec = self.periods[period]
        start, end = float(spec["start_hour"]), float(spec["end_hour"])
        return (24.0 - start) if end < start else (end - start)

    def cube_field(self, key: str, period: str) -> str:
        fields = self._need("cube_fields")
        override = (fields.get("overrides") or {}).get(period, {}) or {}
        template = override.get(key, fields[key])
        return str(template).replace("{P}", period.upper())

    def static_field(self, key: str) -> str:
        return str(self._need("cube_fields", key))

    def mode_field(self, mode: str, period: str) -> str:
        return str(self._need("mode_volume_fields", mode)).replace("{P}", period.upper())

    @property
    def street_name_placeholder(self) -> str:
        return str(self.raw.get("street_name_placeholder", ""))

    @property
    def conic(self) -> dict:
        return self.raw.get("conic", {}) or {}

    @property
    def classification(self) -> dict:
        return self.raw.get("classification", {}) or {}

    @property
    def analysis(self) -> dict:
        return self.raw.get("analysis", {}) or {}

    @property
    def assignment(self) -> dict:
        return self.raw.get("assignment", {}) or {}

    def pinned_period_factor(self) -> dict:
        pinned = self.conic.get("period_factor_E") or {}
        return {str(k).lower(): float(v) for k, v in pinned.items() if v not in (None, "")}

    # ---- snapshot -----------------------------------------------------------
    def write_resolved(self, extra: dict | None = None) -> Path:
        """Freeze the configuration beside the outputs it produced."""
        snapshot = json.loads(json.dumps(self.raw, default=str))
        snapshot["input"] = {
            "network_shapefile": str(self.network_shapefile),
            "demand_folder": str(self.demand_folder),
        }
        snapshot["output"] = {"root": str(self.output_root)}
        conic = dict(snapshot.get("conic") or {})
        conic["alpha_table"] = str(self.alpha_table_path)
        snapshot["conic"] = conic
        snapshot["_source_region_file"] = str(self.source)
        if extra:
            snapshot["_resolved"] = extra
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.resolved_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return self.resolved_path


def activate(path: str | Path | None) -> Region:
    """Load a region and publish its path so ``conic_replay.config`` finds it."""
    region = Region.load(path)
    os.environ[REGION_ENV] = str(region.source)
    return region
