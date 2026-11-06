"""CMAP region file: every path, field name and rule the Emme converter uses."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from scag_transcad.config import read_region_file, region_file_from_argv

MODEL_KEY = "emme_cmap"
RESOLVED_NAME = "region.resolved.json"
REQUIRED = ("region", "references", "input", "output", "periods", "crs", "zones",
            "link_fields", "node_fields", "extra_attribute_fields", "vdf", "toll",
            "access", "checks")


class CmapRegionError(ValueError):
    """A problem in region.cmap.yaml, reported with the key that caused it."""


def is_cmap_region(raw: dict) -> bool:
    return str((raw.get("region") or {}).get("model", "")).strip().lower() == MODEL_KEY


def region_is_cmap(argv: list[str], default: str | Path) -> bool:
    """True when a driver should hand over to this package. Read problems return False."""
    try:
        return is_cmap_region(read_region_file(region_file_from_argv(argv, default)))
    except Exception:  # noqa: BLE001
        return False


@dataclass
class CmapRegion:
    raw: dict
    source: Path
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.source.resolve().parent
        missing = [key for key in REQUIRED if key not in self.raw]
        if missing:
            raise CmapRegionError(f"{self.source.name}: missing sections {missing}")
        nocap = self.raw["vdf"].get("no_capacity_links") or {}
        for key in ("vdf_codes", "capacity_placeholder", "alpha", "beta", "vdf_type"):
            if key not in nocap:
                raise CmapRegionError(f"vdf > no_capacity_links > {key} is missing")

    @classmethod
    def load(cls, path: str | Path) -> "CmapRegion":
        raw = read_region_file(path)
        if not is_cmap_region(raw):
            raise CmapRegionError(f"{path}: region > model is not '{MODEL_KEY}'")
        return cls(raw, Path(path))

    # ---- paths -------------------------------------------------------------
    def path(self, value: str | Path) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (self.root / p)

    def input_path(self, key: str, period: str) -> Path:
        table = self.raw["input"].get(key) or {}
        if period not in table:
            raise CmapRegionError(f"input > {key} has no entry for period {period}")
        return self.path(table[period])

    @property
    def output_root(self) -> Path:
        return self.path(self.raw["output"]["root"])

    # ---- sections ----------------------------------------------------------
    @property
    def name(self) -> str:
        return str(self.raw["region"]["name"])

    @property
    def periods(self) -> dict:
        return self.raw["periods"]

    @property
    def links(self) -> dict:
        return self.raw["link_fields"]

    @property
    def nodes(self) -> dict:
        return self.raw["node_fields"]

    @property
    def extra(self) -> dict:
        return self.raw["extra_attribute_fields"]

    @property
    def vdf(self) -> dict:
        return self.raw["vdf"]

    @property
    def nocap(self) -> dict:
        return self.raw["vdf"]["no_capacity_links"]

    @property
    def checks(self) -> dict:
        return self.raw["checks"]

    def reference(self, key: str) -> str:
        ref = self.raw["references"][key]
        return f"[{key}] {ref['title']} - {ref['url']}"


def default_region_file(kit_root: Path) -> Path:
    return kit_root / "region.cmap.yaml"


def python_info() -> str:
    return sys.version.split()[0]
