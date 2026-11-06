"""Derive the conical parameters from Cube's own assignment output.

Two tables, written to ``<output>/parameters/``:

``alpha_by_ft_at.csv``   vdf_alpha per facility type x area type
``period_factor.csv``    Cube's period capacity factor E per period

Alpha. Cube stores both V/C (``I4{P}VC``) and the travel-time ratio (``I4{P}VDF``)
for every link. Spiess' constraint beta = (2a-1)/(2a-2) forces the curve through 1 at
zero volume, so alpha is the only unknown and is fitted by least squares. All periods
are pooled: alpha belongs to the link, not the period.

Identifiability. The conical curve is nearly flat well below capacity, so a cell whose
links never approach V/C = 1 cannot determine alpha. Each cell is tested: scale alpha
by +/-30% and measure how far the predicted ratio moves over the cell's own data. If it
moves less than the 0.01 agreement tolerance, or the cell has too few observations, the
cell inherits the pooled facility-type value, and the table says so.

E. Cube computes V/C = volume / (hourly link capacity x E). Rearranged,
E = volume / (capacity x V/C) on any loaded road link; the median is taken and rounded
to five decimals.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ALPHA_GRID = np.arange(1.05, 60.0001, 0.005)
E_DECIMALS = 5
ALPHA_DECIMALS = 2


def conical(alpha, x):
    beta = (2.0 * alpha - 1.0) / (2.0 * alpha - 2.0)
    gap = 1.0 - x
    return 2.0 + np.sqrt(alpha * alpha * gap * gap + beta * beta) - alpha * gap - beta


def _fit(x, y):
    residual = np.array([np.sum((conical(a, x) - y) ** 2) for a in ALPHA_GRID])
    index = int(np.argmin(residual))
    return float(ALPHA_GRID[index]), float(np.sqrt(residual[index] / x.size))


def _read_link_csv(link_csv: Path, columns: list[str]) -> pd.DataFrame:
    header = pd.read_csv(link_csv, nrows=0).columns
    missing = [c for c in columns if c not in header]
    if missing:
        raise KeyError(
            f"{link_csv} is missing {missing}. Check cube_fields in region.yaml "
            "against the field names in your shapefile."
        )
    frame = pd.read_csv(link_csv, usecols=columns, dtype=str, keep_default_na=False)
    return frame.apply(pd.to_numeric, errors="coerce")


def derive_period_factor(region, link_csv: Path) -> pd.DataFrame:
    pinned = region.pinned_period_factor()
    periods = list(region.periods)
    ft_col = "FTYPE"
    from .conic_vdf import converter_field_names
    ft_col = converter_field_names().get("facility_type_field", ft_col)
    columns = [ft_col]
    for p in periods:
        columns += [region.cube_field("volume", p), region.cube_field("vc_ratio", p),
                    region.cube_field("link_capacity", p)]
    frame = _read_link_csv(link_csv, sorted(set(columns)))
    connector = int(region.conic.get("connector_ftype", 0))

    rows = []
    for p in periods:
        vol, vc, cap = (region.cube_field(k, p) for k in ("volume", "vc_ratio", "link_capacity"))
        loaded = frame[(frame[ft_col] != connector) & (frame[vc] > 0.01) & (frame[cap] > 0)]
        ratio = loaded[vol] / (loaded[cap] * loaded[vc])
        derived = round(float(ratio.median()), E_DECIMALS) if len(ratio) else float("nan")
        use = pinned.get(p, derived)
        rows.append({
            "period": p,
            "E": use,
            "source": "pinned in region.yaml" if p in pinned else "derived",
            "derived_E": derived,
            "std": float(ratio.std()) if len(ratio) else float("nan"),
            "n_links": int(len(ratio)),
            "hours_assigned": region.period_hours(p),
            "vdf_plf": use / region.period_hours(p),
        })
    return pd.DataFrame(rows)


def derive_alpha(region, link_csv: Path) -> pd.DataFrame:
    rules = region.conic.get("identifiability", {}) or {}
    min_obs = int(rules.get("min_observations", 30))
    min_vc = float(rules.get("min_vc", 0.20))
    tolerance = float(rules.get("tolerance", 0.01))
    scale = float(rules.get("scale", 0.30))
    divisor = int(region.classification.get("link_type_divisor", 100))
    connector = int(region.conic.get("connector_ftype", 0))

    from .conic_vdf import converter_field_names
    ft_col = converter_field_names().get("facility_type_field", "FTYPE")
    # All four Cube periods are pooled when the network carries them, whether or not
    # they are being converted: alpha is a property of the link.
    header = set(pd.read_csv(link_csv, nrows=0).columns)
    periods = [p for p in ("am", "md", "pm", "nt")
               if region.cube_field("vc_ratio", p) in header
               and region.cube_field("travel_time_ratio", p) in header]
    if not periods:
        raise KeyError("no period has both vc_ratio and travel_time_ratio fields in link.csv")
    columns = [ft_col, "link_type"]
    for p in periods:
        columns += [region.cube_field("vc_ratio", p), region.cube_field("travel_time_ratio", p)]
    frame = _read_link_csv(link_csv, columns)
    frame["ATYPE"] = frame["link_type"] // divisor

    parts = []
    for p in periods:
        part = frame[[ft_col, "ATYPE"]].rename(columns={ft_col: "FTYPE"}).copy()
        part["vc"] = frame[region.cube_field("vc_ratio", p)]
        part["vdf"] = frame[region.cube_field("travel_time_ratio", p)]
        parts.append(part)
    obs = pd.concat(parts, ignore_index=True)
    obs = obs[(obs["FTYPE"] != connector) & obs["vc"].notna() & obs["vdf"].notna()]

    pooled = {}
    for ftype, group in obs.groupby("FTYPE"):
        usable = group[group["vc"] >= min_vc]
        pooled[int(ftype)] = _fit(usable["vc"].to_numpy(), usable["vdf"].to_numpy())[0]

    rows = []
    for (ftype, atype), group in obs.groupby(["FTYPE", "ATYPE"]):
        ftype, atype = int(ftype), int(atype)
        usable = group[group["vc"] >= min_vc]
        x, y = usable["vc"].to_numpy(), usable["vdf"].to_numpy()
        base = pooled[ftype]
        row = {
            "FTYPE": ftype, "ATYPE": atype, "link_type": divisor * atype + ftype,
            "n_observations": int(len(group)), "n_used": int(len(usable)),
            "vc_median": float(group["vc"].median()), "vc_p95": float(group["vc"].quantile(0.95)),
            "pooled_ftype_alpha": base,
        }
        if len(usable) < min_obs:
            row.update(cell_alpha_fit=None, cell_rmse=None, sensitivity=None, identified=False,
                       reason=f"only {len(usable)} observations above V/C {min_vc} "
                              f"(need {min_obs})",
                       alpha=base, source="pooled facility type")
        else:
            moved = float(np.mean(np.abs(conical(base * (1 + scale), x)
                                         - conical(base * (1 - scale), x))))
            fitted, rmse = _fit(x, y)
            ok = moved >= tolerance
            row.update(cell_alpha_fit=fitted, cell_rmse=rmse, sensitivity=moved, identified=ok,
                       reason="" if ok else
                       f"scaling alpha +/-{scale:.0%} moves the ratio by only {moved:.5f}, "
                       f"below {tolerance}; the cell cannot determine alpha",
                       alpha=fitted if ok else base,
                       source="cell fit" if ok else "pooled facility type")
        rows.append(row)

    table = pd.DataFrame(rows).sort_values(["FTYPE", "ATYPE"]).reset_index(drop=True)
    table["alpha"] = table["alpha"].round(ALPHA_DECIMALS)
    table["beta"] = (2 * table["alpha"] - 1) / (2 * table["alpha"] - 2)
    table.attrs["periods_pooled"] = periods
    table.attrs["observations"] = int(len(obs))
    return table


def write_parameters(region, link_csv: Path) -> dict:
    """Derive whatever region.yaml asks to derive, and write both tables."""
    region.parameters_dir.mkdir(parents=True, exist_ok=True)
    factors = derive_period_factor(region, link_csv)
    factors.to_csv(region.period_factor_path, index=False)
    summary = {"period_factor": dict(zip(factors["period"], factors["E"]))}

    if region.derive_alpha:
        table = derive_alpha(region, link_csv)
        table.to_csv(region.alpha_table_path, index=False)
        summary.update(
            alpha_table=str(region.alpha_table_path),
            alpha_cells=int(len(table)),
            alpha_cells_identified=int(table["identified"].sum()),
            alpha_periods_pooled=table.attrs["periods_pooled"],
            alpha_observations=table.attrs["observations"],
        )
    else:
        summary["alpha_table"] = f"{region.alpha_table_path} (supplied, not derived)"
    return summary
