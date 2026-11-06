"""Per-record and per-direction shapefile values, addressed by DBD field name."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import fill


class LinkFields:
    """Read shapefile columns for the directed links built by ``topology.directed_links``.

    A template containing ``{D}`` reads ``AB_*`` for AB rows and ``BA_*`` for BA rows.
    Every column read is remembered in ``used`` for the provenance table.
    """

    def __init__(self, attributes: pd.DataFrame, dictionary, directed: pd.DataFrame):
        self.attributes = attributes
        self.dictionary = dictionary
        self.record = directed["record"].to_numpy()
        self.is_ab = (directed["side"] == "AB").to_numpy()
        self.fallbacks: dict[str, int] = {}
        self.used: dict[str, str] = {}

    def column(self, dbd_name: str) -> str:
        name = self.dictionary.shapefile_name(dbd_name)
        if name not in self.attributes.columns:
            raise KeyError(f"'{dbd_name}' maps to shapefile field '{name}', "
                           "which the shapefile does not have")
        self.used[name] = dbd_name
        return name

    def _values(self, name: str, numeric: bool) -> np.ndarray:
        series = self.attributes[name]
        if numeric:
            return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        return series.to_numpy(dtype=object)

    def per_record(self, dbd_name: str, numeric: bool = True) -> np.ndarray:
        return self._values(self.column(dbd_name), numeric)

    def per_direction(self, template: str, *, P: str | None = None, C: str | None = None,
                      numeric: bool = True, fallback_to_ab: bool = False) -> np.ndarray:
        if "{D}" not in template:
            return self._values(self.column(fill(template, P=P, C=C)), numeric)[self.record]
        ab = self._values(self.column(fill(template, D="AB", P=P, C=C)), numeric)[self.record]
        ba = self._values(self.column(fill(template, D="BA", P=P, C=C)), numeric)[self.record]
        values = np.where(self.is_ab, ab, ba)
        if fallback_to_ab and numeric:
            use_ab = ~self.is_ab & np.isnan(ba) & ~np.isnan(ab)
            values = np.where(use_ab, ab, values)
            self.fallbacks[fill(template, D="BA", P=P, C=C)] = int(use_ab.sum())
        return values
