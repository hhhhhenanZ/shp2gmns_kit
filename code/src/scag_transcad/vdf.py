"""SCAG volume-delay functions for TAPlite, and the period capacity factor.

Source: SCAG Model Validation Report (RTP24), p.159-160.

``vdf_type = 7``  SCAG piecewise BPR, TAPLite.cpp. ``t = t0 (1 + alpha x^e)`` with ``e = 4``
                  at ``x <= 1`` (kernel constant ``SCAG_UNCONGESTED_BETA``) and
                  ``e = vdf_beta`` above capacity. alpha and beta are Table 16-2, by
                  facility group, posted speed and area type.
``vdf_type = 8``  SCAG freeway on-ramp meter, TAPLite.cpp, for facility types 82 and 84:
                  ``t = t0 + (PLPH/120) * 5 * (1 + x)^8`` minutes. The row keeps the
                  Table 16-2 "All Others" alpha and beta, so switching ``on_ramp >
                  vdf_type`` to 7 needs no other change.
Centroid connectors keep ``vdf > connectors > vdf_type`` (7) with alpha 0, i.e.
``t = t0`` at every volume, which is what SCAG's loaded times show on them.

Capacity basis. TAPlite computes ``x = V / (lanes * H * vdf_plf * capacity)`` with ``H``
the hours in settings.csv and ``capacity`` per lane per hour. SCAG assigns a period
against the hourly capacity times a period factor E, so ``vdf_plf = E / H``. E is SCAG's
own number, ``"<D> CAPA <P>" / <D>_HRCAPACITY<P>`` in their 50PL working network, and is
pinned in ``vdf > period_capacity_factor``.
"""

from __future__ import annotations

PLF_DECIMALS = 3  # decimals kept on vdf_plf in link.csv

import numpy as np
import pandas as pd


def assign_vdf(region, facility_type, posted_speed, area_type, highway) -> dict:
    cfg = region.vdf
    n = len(facility_type)
    vdf_type = np.full(n, -1, dtype=np.int64)
    alpha = np.full(n, np.nan)
    beta = np.full(n, np.nan)
    group = np.full(n, "", dtype=object)

    connector_types = cfg["connectors"]["facility_types"]
    connectors = highway & np.isin(facility_type, connector_types)
    pending = highway & ~connectors
    for rule in cfg["table_16_2"]:
        mask = pending.copy()
        if "facility_types" in rule:
            mask &= np.isin(facility_type, rule["facility_types"])
        if "posted_speed_max" in rule:
            mask &= posted_speed <= float(rule["posted_speed_max"])
        if "posted_speed_min" in rule:
            mask &= posted_speed >= float(rule["posted_speed_min"])
        if "area_types" in rule:
            mask &= np.isin(area_type, rule["area_types"])
        vdf_type[mask] = int(cfg["road_vdf_type"])
        alpha[mask] = float(rule["alpha"])
        beta[mask] = float(rule["beta"])
        group[mask] = str(rule["group"])
        pending &= ~mask
    if pending.any():
        left = pd.DataFrame({"facility_type": facility_type[pending], "area_type": area_type[pending],
                             "posted_speed": posted_speed[pending]})
        raise ValueError(
            f"{int(pending.sum())} highway links match no Table 16-2 row; refusing to default.\n"
            f"{left.value_counts(dropna=False).head(20)}")

    ramp_cfg = cfg["on_ramp"]
    ramps = highway & ~connectors & np.isin(facility_type, ramp_cfg["facility_types"])
    vdf_type[ramps] = int(ramp_cfg["vdf_type"])
    group[ramps] = np.array([f"{g}; on-ramp meter" for g in group[ramps]], dtype=object)

    vdf_type[connectors] = int(cfg["connectors"]["vdf_type"])
    alpha[connectors] = float(cfg["connectors"]["alpha"])
    beta[connectors] = float(cfg["connectors"]["beta"])
    group[connectors] = "Centroid connector"
    return {"vdf_type": vdf_type, "vdf_alpha": alpha, "vdf_beta": beta, "vdf_group": group,
            "ramp": ramps, "connector": connectors}


def parameter_table(region) -> pd.DataFrame:
    cfg = region.vdf
    rows = []
    for rule in cfg["table_16_2"]:
        rows.append({
            "group": rule["group"],
            "facility_types": " ".join(str(v) for v in rule.get("facility_types", [])) or "all others",
            "posted_speed": (f"<= {rule['posted_speed_max']}" if "posted_speed_max" in rule
                             else f">= {rule['posted_speed_min']}" if "posted_speed_min" in rule
                             else "all"),
            "area_types": " ".join(str(v) for v in rule.get("area_types", [])) or "all",
            "vdf_type": cfg["road_vdf_type"], "alpha": rule["alpha"], "beta_above_capacity": rule["beta"],
            "beta_at_or_below_capacity": cfg["uncongested_beta"], "source": cfg["source"],
        })
    ramp = cfg["on_ramp"]
    rows.append({"group": "On-ramp meter", "facility_types": " ".join(map(str, ramp["facility_types"])),
                 "posted_speed": "all", "area_types": "all", "vdf_type": ramp["vdf_type"],
                 "alpha": "Table 16-2 All Others", "beta_above_capacity": "Table 16-2 All Others",
                 "beta_at_or_below_capacity": "", "source": ramp["source"]})
    conn = cfg["connectors"]
    rows.append({"group": "Centroid connector", "facility_types": " ".join(map(str, conn["facility_types"])),
                 "posted_speed": "all", "area_types": "all", "vdf_type": conn["vdf_type"],
                 "alpha": conn["alpha"], "beta_above_capacity": conn["beta"],
                 "beta_at_or_below_capacity": conn["beta"], "source": conn["source"]})
    return pd.DataFrame(rows)


def _pce_flow(region, fields, period: str) -> np.ndarray:
    flow = None
    for mode in region.modes:
        part = mode.pce * np.nan_to_num(
            fields.per_direction(region.link_field("flow"), P=period, C=mode.flow_class))
        flow = part if flow is None else flow + part
    return flow


def ramp_function_check(region, fields, keep, vdf: dict, free_time, lane_capacity,
                        factor: pd.DataFrame) -> pd.DataFrame:
    """SCAG's loaded on-ramp delay beside what vdf_type 8 and vdf_type 7 would give.

    Both predictions use SCAG's loaded volume and the converter's capacity basis:
    ``PLPH = V_pce / lanes / E`` (TAPlite's per-lane hourly demand) and ``x = PLPH / c``.
    ``vdf_type 8``: ``(PLPH/120) * 5 * (1+x)^8`` minutes, as coded in TAPLite.cpp.
    ``vdf_type 7``: ``t0 * alpha * x^e`` minutes with the row's Table 16-2 alpha and beta.
    """
    cfg = region.vdf
    ramps = keep & vdf["ramp"]
    uncongested = float(cfg["uncongested_beta"])
    used = dict(zip(factor["period"], factor["E"]))
    rows = []
    for period in region.periods:
        time = fields.per_direction(region.link_field("time_min"), P=period)
        lanes = fields.per_direction(region.link_field("lanes"), P=period)
        flow = _pce_flow(region, fields, period)
        use = ramps & np.isfinite(time) & np.isfinite(lanes) & (lanes > 0)
        if not use.any():
            continue
        plph = flow[use] / lanes[use] / float(used[period])
        x = plph / lane_capacity[use]
        loaded = time[use] - free_time[use]
        meter = (plph / 120.0) * 5.0 * (1.0 + x) ** 8
        exponent = np.where(x <= 1.0, uncongested, vdf["vdf_beta"][use])
        bpr = free_time[use] * vdf["vdf_alpha"][use] * x ** exponent
        for label, predicted in (("vdf_type 8: on-ramp meter", meter),
                                 ("vdf_type 7: Table 16-2 All Others", bpr)):
            rows.append({
                "period": period, "function": label, "links": int(use.sum()),
                "loaded_delay_min_median": float(np.median(loaded)),
                "loaded_delay_min_p90": float(np.quantile(loaded, 0.9)),
                "loaded_delay_min_p99": float(np.quantile(loaded, 0.99)),
                "predicted_delay_min_median": float(np.median(predicted)),
                "predicted_delay_min_p90": float(np.quantile(predicted, 0.9)),
                "predicted_delay_min_p99": float(np.quantile(predicted, 0.99)),
                "mean_abs_error_min": float(np.mean(np.abs(predicted - loaded))),
            })
    return pd.DataFrame(rows)


def period_factor_table(region) -> pd.DataFrame:
    """E and vdf_plf per period.

    SCAG assigns each period against ``hourly capacity x E``; TAPlite divides by
    ``lanes x lane capacity x H x vdf_plf``. Equating the two gives ``vdf_plf = E / H``.

    E comes from SCAG's own files (``"<D> CAPA <P>" / <D>_HRCAPACITY<P>`` in the 50PL
    working network): 3, 6, 4, 2, 8 hours for AM, MD, PM, EVE, NT, exact on every link that
    carries capacity. H is the period's own length, so ``H x vdf_plf = E`` puts SCAG's
    period capacity back in the denominator. The night period is nine hours while SCAG
    gives it eight hours of capacity, which is the only period where vdf_plf is not 1.
    """
    setting = region.vdf.get("period_capacity_factor", "clock_hours")
    rows = []
    for period in region.periods:
        hours = region.kernel_hours(period)
        if isinstance(setting, dict):
            if period not in setting:
                raise ValueError(f"vdf > period_capacity_factor has no entry for {period}")
            factor, source = float(setting[period]), 'SCAG "<D> CAPA <P>" / <D>_HRCAPACITY<P>'
        elif str(setting).lower() == "clock_hours":
            factor, source = region.clock_hours(period), "clock hours of the period"
        else:
            raise ValueError(
                "vdf > period_capacity_factor must be a mapping of period to E, or "
                f"'clock_hours'; got {setting!r}")
        start, end = region.kernel_window(period)
        rows.append({
            "period": period,
            "start_hour": region.periods[period]["start_hour"],
            "end_hour": region.periods[period]["end_hour"],
            "period_hours": region.clock_hours(period),
            "settings_start_hour": start, "settings_end_hour": end, "settings_hours": hours,
            "E": factor, "E_source": source,
            # 3 decimals: NT is 8/9 = 0.889, so hours x vdf_plf is 8.001 rather than 8,
            # 0.01% more night capacity than SCAG codes. Every other period is exactly 1.
            "vdf_plf": round(factor / hours, PLF_DECIMALS),
            "hours_x_plf": round(hours * round(factor / hours, PLF_DECIMALS), 4),
        })
    return pd.DataFrame(rows)
