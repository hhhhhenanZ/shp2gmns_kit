"""allowed_use for every directed link, and a check of the rules against SCAG's flows.

Rules come from ``region.yaml > access`` and are applied in order; the first rule that
matches a link decides it. A link no rule matches is open to every mode. Facility types
listed in ``closed_facility_types`` are written with ``allowed_use = closed``.

The check sums, for each rule and period, SCAG's loaded flow of every class the rule
does not allow. A rule that reproduces SCAG's access coding leaves that sum at zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CLOSED


def assign_allowed_use(region, facility_type, toll_flag, truck_prohibit, highway) -> tuple:
    cfg = region.access
    modes = [m.mode_type for m in region.modes]
    n = len(facility_type)
    allowed = np.full(n, ";".join(modes), dtype=object)
    rule_name = np.full(n, "all modes", dtype=object)
    decided = ~highway.copy()

    closed = highway & np.isin(facility_type, cfg.get("closed_facility_types", []))
    allowed[closed] = CLOSED
    rule_name[closed] = cfg.get("closed_reason", "closed facility type")
    decided |= closed

    for rule in cfg.get("rules", []):
        mask = ~decided
        if "facility_types" in rule:
            mask &= np.isin(facility_type, rule["facility_types"])
        if "toll_flags" in rule:
            mask &= np.isin(toll_flag, rule["toll_flags"])
        if "truck_prohibit" in rule:
            mask &= np.isin(truck_prohibit, rule["truck_prohibit"])
        allowed[mask] = ";".join(rule["allowed"])
        rule_name[mask] = rule["name"]
        decided |= mask
    return allowed, rule_name


def check_against_loaded_flows(region, fields, keep, allowed, rule_name) -> pd.DataFrame:
    rows = []
    template = region.link_field("flow")
    rules = pd.Series(rule_name[keep])
    for period in region.periods:
        for mode in region.modes:
            flow = np.nan_to_num(fields.per_direction(template, P=period, C=mode.flow_class))[keep]
            barred = np.array([mode.mode_type not in text.split(";") for text in allowed[keep]])
            frame = pd.DataFrame({"rule": rules, "flow": flow, "barred": barred})
            for name, part in frame.groupby("rule"):
                if not part["barred"].any():
                    continue
                on_barred = part.loc[part["barred"], "flow"]
                rows.append({"rule": name, "period": period, "mode_type": mode.mode_type,
                             "links": int(len(part)),
                             "loaded_flow_on_barred_links": float(on_barred.sum()),
                             "barred_links_with_flow": int((on_barred > 0).sum())})
    return pd.DataFrame(rows)
