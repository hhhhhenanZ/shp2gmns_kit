"""MODES letters -> allowed_use [A Table 18 p.47].

allowed_use lists mode codes separated by ';' (NVTA convention). The codes are the OD vehicle
classes; the letter-to-code table is ``region.cmap.yaml > access``.
"""

from __future__ import annotations

import pandas as pd


def assign(links: pd.DataFrame, region) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = region.raw["access"]
    order, letters = cfg["mode_order"], cfg["letters"]

    def rule(modes: str) -> str:
        allowed = {code for ch in str(modes) for code in letters.get(ch, [])}
        return ";".join(c for c in order if c in allowed) or "closed"

    table = {m: rule(m) for m in links["_modes"].unique()}
    links["allowed_use"] = links["_modes"].map(table)
    check = (links.groupby("_modes").size().rename("links").reset_index()
             .rename(columns={"_modes": "MODES"})
             .assign(allowed_use=lambda d: d.MODES.map(table))
             .sort_values("links", ascending=False))
    return links, check
