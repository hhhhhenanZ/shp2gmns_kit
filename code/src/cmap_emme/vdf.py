"""CMAP volume-delay functions and the capacity rule.

Source: [C] CMAP model code (Database/data/vdf_tod.in, macros/TOD_network_prep.py) and
[A] appendix pp. 122-126; values in ``region.cmap.yaml > vdf``.
ul2 = capacity_factor x @emcap x lanes x period hours (0.75 on VDF 1-5); ul1 = @ftime.

Capacity
--------
* VDF 1-5, 8: ``capacity = @emcap`` (vehicles per hour per lane), unchanged. The 0.75
  (VDF 1, 3) and +300 (VDF 2) belong to the function and are kept in vdf_parameters.csv.
* VDF 6 (centroid connector) and 7 (toll collection): CMAP gives @emcap = 0 and puts no
  capacity constraint on them. ``region.cmap.yaml > vdf > no_capacity_links`` sets the
  PLACEHOLDER (99,999), alpha 0 and beta 1. The number is read from there; it is not in
  this code. Connectors are found by VDF code, not by touching a zone node.

TAPLite form
------------
Only the no-capacity links get vdf_type / alpha / beta here. For VDF 1-5 and 8 they are
left blank: CMAP's min-term and intersection delay are not kernel functions, and the
TAPLite form is chosen in the replay step.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def parameter_table(region) -> pd.DataFrame:
    rows = []
    nocap = region.nocap
    for code, f in sorted(region.vdf["functions"].items(), key=lambda kv: int(kv[0])):
        code = int(code)
        placeholder = code in nocap["vdf_codes"]
        rows.append({
            "vdf_code": code, "name": f["name"], "form": f["form"],
            "alpha": f["alpha"], "exponent": f["exponent"],
            "capacity_factor": f["capacity_factor"], "capacity_add_veh": f["capacity_add"],
            "min_term": f["min_term"], "ftime_divisor_documented": f["ftime_divisor"],
            "intersection_delay": f["intersection_delay"],
            "capacity_written": (f"placeholder {nocap['capacity_placeholder']}" if placeholder
                                 else "@emcap (veh/h/lane)"),
            "taplite_vdf_type": nocap["vdf_type"] if placeholder else "",
            "taplite_alpha": nocap["alpha"] if placeholder else "",
            "taplite_beta": nocap["beta"] if placeholder else "",
            "taplite_status": ("set: fixed time t = @ftime" if placeholder
                               else "open: chosen in the replay step"),
            "source": f["page"],
        })
    return pd.DataFrame(rows)


def assign(links: pd.DataFrame, region) -> pd.DataFrame:
    nocap = region.nocap
    is_nocap = links["vdf_code"].isin(nocap["vdf_codes"]).to_numpy()
    emcap = links["_emcap"].to_numpy(float)
    links["capacity"] = np.where(is_nocap, float(nocap["capacity_placeholder"]), emcap)
    links["capacity_source"] = np.where(is_nocap, nocap["capacity_source_label"], "cmap_emcap")
    links["vdf_type"] = np.where(is_nocap, str(nocap["vdf_type"]), "")
    links["vdf_alpha"] = np.where(is_nocap, str(nocap["alpha"]), "")
    links["vdf_beta"] = np.where(is_nocap, str(nocap["beta"]), "")
    return links


def _formula(code: int, f: dict, t0, v, cap_period, use_divisor: bool):
    c = cap_period * f["capacity_factor"]
    x = v / (c + f["capacity_add"])   # [A p.124]: VDF 2 capacity "increased by 300 vehicles"
    t = t0 / (f["ftime_divisor"] if use_divisor else 1.0)
    t = t * (1 + f["alpha"] * x ** f["exponent"])
    if f["min_term"]:
        t = t * (1 + 0.15 * np.minimum(v / c, 1.0))   # fd2, fd4: min(v/ul2, 1) [C vdf_tod.in]
    return t


def reproduction(links: pd.DataFrame, region, hours: float) -> pd.DataFrame:
    """Each CMAP function evaluated with v = DATA1 against CMAP's own timau."""
    rows = []
    t_obs = links["ref_time"].to_numpy(float)
    for code, f in sorted(region.vdf["functions"].items(), key=lambda kv: int(kv[0])):
        code = int(code)
        sel = (links["vdf_code"] == code).to_numpy()
        if not sel.any():
            continue
        t0 = links.loc[sel, "vdf_fftt"].to_numpy(float)
        v = links.loc[sel, "ref_volume"].to_numpy(float)
        cap = links.loc[sel, "_emcap"].to_numpy(float) * links.loc[sel, "lanes"].to_numpy(float) * hours
        obs = t_obs[sel]
        variants = [("as documented", True)]
        if f["ftime_divisor"] != 1.0:
            variants.append(("without the /1.15 on T0", False))
        for label, use_div in variants:
            if code in region.nocap["vdf_codes"]:
                pred, note = t0, "fixed time"
            else:
                with np.errstate(divide="ignore", invalid="ignore"):
                    pred = _formula(code, f, t0, v, cap, use_div)
                note = ("BPR part only: intersection delay needs @gc, @cycle (not exported)"
                        if f["intersection_delay"] else "")
            ok = np.isfinite(pred) & (obs > 0)
            rel = (pred[ok] - obs[ok]) / obs[ok]
            low = ok & (np.divide(v, cap, out=np.full_like(v, np.inf), where=cap > 0) < 0.1)
            rows.append({
                "vdf_code": code, "name": f["name"], "variant": label, "links": int(sel.sum()),
                "links_evaluated": int(ok.sum()),
                "median_rel_error": round(float(np.median(rel)), 4) if ok.any() else "",
                "p90_abs_rel_error": round(float(np.quantile(np.abs(rel), 0.9)), 4) if ok.any() else "",
                "timau_over_ftime_at_vc_below_0.1": (round(float(np.median(obs[low] / t0[low])), 3)
                                                     if low.any() else ""),
                "note": note,
            })
    return pd.DataFrame(rows)
