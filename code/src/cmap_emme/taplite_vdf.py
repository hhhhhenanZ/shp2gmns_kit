"""Replay step: the volume-delay function TAPLite uses on each CMAP link.

CMAP's functions fd1-fd8 (vdf.py) are not TAPLite kernel functions: fd2 and fd4 have a
min(v/ul2, 1) term and fd1 and fd3 add signal delay from @cycle and @gc, which were not
exported. Until they are added to TAPLite, ``region.cmap.yaml > taplite_vdf`` sets one BPR
on every link that has a capacity. Nothing of CMAP is lost:

* CMAP's own values stay on each link in the ``cmap_*`` columns (function, alpha, exponent,
  capacity factor and add, min-term, signal delay), so changing back needs no reconversion;
* ``replay`` evaluates both at CMAP's own volume (DATA1) against CMAP's time (timau), so the
  cost of the BPR stand-in is shown by facility type before any assignment is run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .vdf import _formula


def apply(link: pd.DataFrame, cfg: dict, functions: dict) -> pd.DataFrame:
    """Write CMAP's parameters to cmap_* columns and TAPLite's to vdf_*."""
    link = link.copy()
    f = {int(k): v for k, v in functions.items()}
    code = link.vdf_code.astype(int)
    link["cmap_vdf_function"] = "fd" + code.astype(str)
    link["cmap_alpha"] = code.map(lambda c: f[c]["alpha"])
    link["cmap_beta"] = code.map(lambda c: f[c]["exponent"])
    link["cmap_capacity_factor"] = code.map(lambda c: f[c]["capacity_factor"])
    link["cmap_capacity_add"] = code.map(lambda c: f[c]["capacity_add"])
    link["cmap_min_term"] = code.map(lambda c: int(f[c]["min_term"]))
    link["cmap_signal_delay"] = code.map(lambda c: int(f[c]["intersection_delay"]))
    fixed = code.isin(cfg["fixed_time_codes"])
    link["vdf_type"] = int(cfg["vdf_type"])
    link["vdf_alpha"] = np.where(fixed, 0.0, float(cfg["alpha"]))
    link["vdf_beta"] = np.where(fixed, 1.0, float(cfg["beta"]))
    link["vdf_plf"] = float(cfg["plf"])
    return link


def bpr_time(t0, v, cap_period, alpha, beta):
    with np.errstate(divide="ignore", invalid="ignore"):
        return t0 * (1 + alpha * np.power(v / cap_period, beta))


def replay(link: pd.DataFrame, functions: dict, hours: float) -> pd.DataFrame:
    """Time at CMAP's volume: CMAP fd1-fd8 and the TAPLite VDF, against timau, by VDF code."""
    t0 = link.vdf_fftt.to_numpy(float)
    v = link.ref_volume.to_numpy(float)
    obs = link.ref_time.to_numpy(float)
    cap = link.capacity.to_numpy(float) * link.lanes.to_numpy(float) * hours
    t_bpr = bpr_time(t0, v, cap, link.vdf_alpha.to_numpy(float), link.vdf_beta.to_numpy(float))
    t_cmap = t0.copy()
    for c, f in functions.items():
        sel = (link.vdf_code == int(c)).to_numpy()
        if f["alpha"] > 0:
            with np.errstate(divide="ignore", invalid="ignore"):
                t_cmap[sel] = _formula(int(c), f, t0[sel], v[sel], cap[sel], True)
    rows = []
    groups = [(int(c), link.vdf_code == int(c)) for c in sorted(functions, key=int)]
    groups.append(("road", link.vdf_code != 6))
    for c, sel in groups:
        sel = sel.to_numpy() & (obs > 0) & np.isfinite(t_cmap) & np.isfinite(t_bpr)
        if not sel.any():
            continue
        vht = lambda t: float((v[sel] * t[sel]).sum() / 60)
        rows.append({
            "vdf_code": c,
            "facility_type": (link.facility_type[sel].iloc[0] if c != "road" else "road links (no connectors)"),
            "links": int(sel.sum()),
            "vht_timau": round(vht(obs)), "vht_cmap_fd": round(vht(t_cmap)), "vht_taplite_vdf": round(vht(t_bpr)),
            "vht_ratio_cmap_fd": round(vht(t_cmap) / vht(obs), 3),
            "vht_ratio_taplite_vdf": round(vht(t_bpr) / vht(obs), 3),
            "median_time_ratio_cmap_fd": round(float(np.median(t_cmap[sel] / obs[sel])), 3),
            "median_time_ratio_taplite_vdf": round(float(np.median(t_bpr[sel] / obs[sel])), 3),
        })
    return pd.DataFrame(rows)
