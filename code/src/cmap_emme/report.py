"""FIELD_PROVENANCE.csv and CONVERSION_REPORT.md for the CMAP conversion."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

A_URL = "A"
G_URL = "G"


def provenance(region) -> pd.DataFrame:
    a, g, c_ = region.reference("A"), region.reference("G"), region.reference("C")
    nocap = region.nocap
    P = []

    def row(col, rule, source, status, src_unit, out_unit, ref):
        P.append({"file": "link.csv", "column": col, "rule": rule, "source": source,
                  "status": status, "source_unit": src_unit, "output_unit": out_unit,
                  "reference": ref})

    row("link_id", "1..N in shapefile order", "-", "derived", "-", "-", "workplan 4.2")
    row("from_node_id", "INODE", "emme_links.dbf", "source field", "-", "-", g)
    row("to_node_id", "JNODE", "emme_links.dbf", "source field", "-", "-", g)
    row("dir_flag", "1: Emme links are directed", "-", "documented rule", "-", "-", g)
    row("length", "LENGTH x 1609.344", "emme_links.dbf LENGTH", "derived", "mile", "meter",
        f"{a} Table 18 p.47; {g} link field 4")
    row("vdf_length_mi", "LENGTH", "emme_links.dbf", "source field", "mile", "mile", a)
    row("lanes", "LANES", "emme_links.dbf", "source field", "lanes", "lanes", f"{a} Table 18 p.47")
    row("capacity", f"@emcap on VDF 1-5, 8; PLACEHOLDER {nocap['capacity_placeholder']} on VDF "
        f"{nocap['vdf_codes']} (CMAP @emcap = 0, no capacity constraint; region.cmap.yaml > vdf > "
        "no_capacity_links)", "attribs_p7.txt @emcap", "source field / placeholder",
        "vehicle/hour/lane", "vehicle/hour/lane", f"{g}; {a} pp.48-49, p.126")
    row("capacity_source", "cmap_emcap or placeholder_no_constraint", "-", "documented rule",
        "-", "-", "workplan 4.6")
    row("hourly_link_capacity", "capacity x lanes", "-", "derived", "-", "vehicle/hour/link", "-")
    row("free_speed", "vdf_free_speed_mph x 1.609344", "-", "derived", "mph", "kph",
        "code/src/dtalite4cube/unit_contract.py")
    row("vdf_free_speed_mph", "LENGTH / @ftime x 60", "-", "derived", "mile, minute", "mph", a)
    row("vdf_fftt", "@ftime (CMAP: length / binned @speed x 60, see region.cmap.yaml)", "attribs_p7.txt", "source field", "minute", "minute",
        f"{c_} Ftime_capacity.py; {a} Table 18 p.47")
    row("vdf_code", "VDF", "emme_links.dbf", "source field", "-", "-", f"{a} Table 18 p.47")
    row("link_type", "= vdf_code", "-", "documented rule", "-", "-", "workplan 4.3")
    row("facility_type", "name of the VDF code", "region.cmap.yaml vdf > functions",
        "documented rule", "-", "-", f"{a} p.47")
    row("vdf_type", f"{nocap['vdf_type']} on VDF {nocap['vdf_codes']}; blank on VDF 1-5, 8 "
        "(TAPLite form chosen in the replay step)", "region.cmap.yaml", "documented rule / open",
        "-", "-", f"{a} pp.122-126")
    row("vdf_alpha", f"{nocap['alpha']} on VDF {nocap['vdf_codes']}; blank otherwise",
        "region.cmap.yaml", "documented rule / open", "-", "-", f"{a} p.126")
    row("vdf_beta", f"{nocap['beta']} on VDF {nocap['vdf_codes']}; blank otherwise",
        "region.cmap.yaml", "documented rule / open", "-", "-", f"{a} p.126")
    row("vdf_plf", "1.0: period capacity = @emcap x lanes x 2 for the 2-h PM period", "-",
        "documented rule", "-", "-", f"{g} emmenet_highway; {a} p.49")
    row("toll", "@toll as given: dollars per link (CMAP assignment uses it unchanged as link cost)",
        "attribs_p7.txt @toll", "source field", "US dollar per link", "US dollar per link",
        f"{c_} SOLA_assignment.py; {g}; NVTA: dtalite4cube/cube2gmns/funclib.py (toll in dollars)")
    row("allowed_use", "MODES letters -> mode codes sov;hov2;hov3;apv;btrk;ltrk;mtrk;htrk "
        "(region.cmap.yaml > access); codes = OD vehicle classes", "emme_links.dbf MODES",
        "documented rule", "-", "-", f"{a} Table 18 p.47, p.111; NVTA netconfig.py allowed_uses_dict")
    row("org_link_id", "ID ('i-j')", "emme_links.dbf", "source field", "-", "-", g)
    row("tipid", "@tipid", "attribs_p7.txt", "source field", "-", "-", g)
    row("width", "@width", "attribs_p7.txt", "source field", "foot", "foot", g)
    row("parkl", "@parkl", "attribs_p7.txt", "source field", "count", "count", g)
    row("sigic", "@sigic", "attribs_p7.txt", "source field", "0/1", "0/1", g)
    row("ref_volume", "DATA1 (= @vadt): CMAP assigned PM volume", "emme_links.dbf DATA1",
        "source field", "vehicle per 2-h period (4-6 pm)", "vehicle per 2-h period",
        f"{g} PM Peak Highway Network Shapefiles")
    row("ref_time", "TIMAU (= timau): CMAP congested auto time at the final assigned PM volume",
        "emme_links.dbf TIMAU", "source field", "minute", "minute",
        f"{g} Emme Highway Networks (timau); {c_} vdf_tod.in")
    row("timau", "TIMAU, same as ref_time, kept under its CMAP name", "emme_links.dbf TIMAU",
        "source field", "minute", "minute", g)
    frame = pd.DataFrame(P)
    nodes = pd.DataFrame([
        {"file": "node.csv", "column": "node_id", "rule": "Emme node number", "source": "emme_nodes.dbf ID",
         "status": "source field", "source_unit": "-", "output_unit": "-", "reference": g},
        {"file": "node.csv", "column": "zone_id", "rule": "= node_id where ISZONE = 1 (1-3649)",
         "source": "emme_nodes.dbf ISZONE", "status": "source field", "source_unit": "-",
         "output_unit": "-", "reference": g},
        {"file": "node.csv", "column": "x_coord", "rule": "X reprojected EPSG:26771 -> EPSG:4326",
         "source": "emme_nodes.dbf X", "status": "derived", "source_unit": "US survey foot",
         "output_unit": "degree", "reference": f"{a} Table 19 p.48"},
        {"file": "node.csv", "column": "y_coord", "rule": "Y reprojected EPSG:26771 -> EPSG:4326",
         "source": "emme_nodes.dbf Y", "status": "derived", "source_unit": "US survey foot",
         "output_unit": "degree", "reference": f"{a} Table 19 p.48"},
        {"file": "node.csv", "column": "node_type", "rule": "centroid if ISZONE = 1, else road",
         "source": "ISZONE", "status": "derived", "source_unit": "-", "output_unit": "-", "reference": g},
        {"file": "node.csv", "column": "cmap_label", "rule": "LABEL", "source": "emme_nodes.dbf",
         "status": "source field", "source_unit": "-", "output_unit": "-", "reference": g},
    ])
    return pd.concat([nodes, frame], ignore_index=True)


def _md_table(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in frame.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def conversion_report(region, period, nodes, links, gates, summary, reproduction, access_check,
                      manifest, dem=None) -> str:
    a = region.raw["references"]["A"]
    g = region.raw["references"]["G"]
    nocap = region.nocap
    n_ph = int((links.capacity_source == nocap["capacity_source_label"]).sum())
    gate_counts = gates.status.value_counts().to_dict()
    lines = [
        f"# CMAP highway network -> GMNS: conversion report ({period})",
        "",
        f"Generated {manifest['finished_utc']} by `code/src/cmap_emme` "
        f"(`region.cmap.yaml`).",
        "",
        "## Sources",
        "",
        f"- **[G]** {g['title']}: `{g['file']}`. Download (CMAP Data Hub, c25q4 package): {g['url']}",
        f"- **[A]** {a['title']}: `{a['file']}`. Download: {a['url']} (printed page numbers)",
        f"- **[C]** {region.raw['references']['C']['title']}: `{region.raw['references']['C']['file']}`. Source: {region.raw['references']['C']['url']}",
        f"- Model: CMAP trip-based model, conformity cycle {region.raw['region']['conformity_cycle']}, "
        f"scenario {region.raw['region']['scenario']} = {region.raw['region']['base_year']} base year.",
        f"- Period: {period} = Emme period {region.periods[period]['emme_period']}, "
        f"{region.periods[period]['start_hour']}:00-{region.periods[period]['end_hour']}:00 "
        f"({region.periods[period]['hours']} h).",
        "",
        "## Result",
        "",
        f"- `network/{period}/node.csv`: {len(nodes):,} nodes, of which "
        f"{int((nodes.node_type == 'centroid').sum()):,} zone centroids (ids 1-3649).",
        f"- `network/{period}/link.csv`: {len(links):,} links; none excluded.",
        f"- Gates: {gate_counts.get('PASS', 0)} PASS, {gate_counts.get('FAIL', 0)} FAIL, "
        f"{gate_counts.get('INFO', 0)} INFO (`checks/gate_report.csv`).",
        f"- Shapefile read with: {manifest['reader']}. Reprojection: {manifest['reprojection']}.",
        "",
        "## Assignment test (TAPLite, BPR)",
        "",
        "This network and demand were assigned in TAPLite as a first end-to-end test (PM, BPR alpha 0.15, "
        "beta 4, no tolls, 10 iterations, gap 0.18 %). Against CMAP's own PM assignment, all links: VMT 0.925, "
        "VHT 0.710, delay 0.109, link volume R^2 0.93 (road links). Volumes match; BPR adds too little delay. "
        "Inputs, run scripts and evaluation: https://github.com/hhhhhenanZ/city-tensor/tree/main/cmap_ta_bpr_allmodes. "
        "Summary: `report/CMAP_progress_report.pdf`, sections 4-5.",
        "",
        "## By VDF class",
        "",
        _md_table(summary),
        "",
        "## Units",
        "",
        "| Quantity | Source (CMAP) | Output (GMNS, kit convention) | Reference |",
        "|---|---|---|---|",
        "| length | miles (`LENGTH`) | metres (`length`); miles kept in `vdf_length_mi` | [A] Table 18 p.47; [G] link field 4 |",
        "| speed | mph (`@speed`, posted; `@ftime` uses it rounded up to a bin) | km/h (`free_speed`); mph in `vdf_free_speed_mph`, both from `@ftime` | [G]; [C] Ftime_capacity.py |",
        "| free-flow time | minutes (`@ftime`) | minutes (`vdf_fftt`) | [A] Table 18 p.47, p.49 |",
        "| capacity | vehicles/hour/**lane**, LOS E (`@emcap`) | vehicles/hour/lane (`capacity`); per link in `hourly_link_capacity` | [G]; [A] pp.48-49 |",
        "| volume | vehicles per **2-hour** period (`DATA1` = `@vadt`) | same (`ref_volume`) | [G] PM Peak Highway Network Shapefiles |",
        "| congested time | minutes (`TIMAU`) | minutes (`ref_time`, `timau`) | [G] |",
        "| toll | US dollars per link (`@toll`; CMAP adds it unchanged as link cost) | US dollars per link (`toll`) | [C] SOLA_assignment.py; [G] |",
        "| coordinates | US survey feet, NAD27 / Illinois East (EPSG:26771) | degrees, EPSG:4326 | [A] Table 19 p.48 |",
        "",
        "Units are also given per column in `FIELD_PROVENANCE.csv`.",
        "",
        "`@ftime` is computed by CMAP's `Ftime_capacity.py` ([C]): `@speed` is rounded up to a bin "
        "and `@ftime = length / binned speed x 60`. Bins: VDF 2, 4 = 40-65 (> 60 -> 65); VDF 1 = 15-55; "
        "VDF 3, 5, 8 = 15-50; VDF 8 adds 0.083 min (5-s meter delay); VDF 6 = length x 3 (20 mph); "
        "VDF 7 uses the incoming link's speed. `vdf_fftt` uses `@ftime` as given; where it differs "
        "from `LENGTH / @speed` is listed in `checks/ftime_vs_posted_speed.csv`.",
        "",
        "## Decisions",
        "",
        f"1. **Connector and toll-link capacity = {nocap['capacity_placeholder']:,} placeholder (CMAP only).** "
        f"CMAP's `@emcap` is 0 on every VDF 6 (centroid connector) and VDF 7 (toll collection) link and "
        f"CMAP does not constrain them ([G]; [A] p.126). There is no reference value, so "
        f"{nocap['capacity_placeholder']:,} is written only to avoid dividing by zero, with vdf_type "
        f"{nocap['vdf_type']}, alpha {nocap['alpha']}, beta {nocap['beta']}: time stays at `@ftime` at every "
        f"volume, so the value does not change the assignment. {n_ph:,} links carry it, marked "
        f"`capacity_source = {nocap['capacity_source_label']}`. Set in `region.cmap.yaml > vdf > "
        f"no_capacity_links`. NVTA (3,150) and SCAG (their own file) are not affected.",
        "2. **Connectors are VDF 6, not every link touching a zone.** The road links leaving zones "
        "3633-3649 keep `@emcap` and their own VDF (`checks/zone_road_links.csv`).",
        "3. **Toll links are kept.** They are in series on the tollways; deleting them disconnects part "
        "of the network and removes the toll from route choice.",
        "4. **Capacity is CMAP's own `@emcap` only.** The 0.75 (VDF 1, 3) and +300 (VDF 2) are part of "
        "CMAP's functions and are kept in `parameters/vdf_parameters.csv`, not in `capacity`.",
        "5. **TAPLite form for VDF 1-5 and 8 is left open** (blank vdf_type/alpha/beta). CMAP's min-term "
        "and signal delay are not kernel functions; the form is chosen in the replay step.",
        "",
        "## Volume-delay functions vs CMAP's own PM times",
        "",
        "v = `DATA1` (vehicles). CMAP's functions use vehicle equivalents including buses, which the PM "
        "files do not carry, so the error tail on VDF 2 and 4 is expected.",
        "",
        "- Functions are evaluated as CMAP runs them ([C] `vdf_tod.in`, `TOD_network_prep.py`): "
        "ul2 = 0.75 x `@emcap` x lanes x 2 on VDF 1-5 (the appendix names the 0.75 only for arterials), "
        "`@emcap` x lanes x 2 on VDF 8; fd2 divides ul1 by 1.15.",
        "- Remaining error: v here is `DATA1` in vehicles; CMAP uses vehicle equivalents plus bus "
        "equivalents (el2), which the PM files do not carry.",
        "- **VDF 1, 3.** Signal delay needs `@cycle`, `@gc` (ul3), not exported.",
        "",
        _md_table(reproduction),
        "",
        "## Reference fields: ref_volume, ref_time, timau",
        "",
        "CMAP runs a static equilibrium assignment per period. For PM (4-6 pm) every link ends with "
        "one volume and one time:",
        "",
        "- `ref_volume` = `DATA1` (= `@vadt`): vehicles over the whole **2-hour** period, not per hour.",
        "- `ref_time` = `timau` = `TIMAU`: the VDF time ([C] `vdf_tod.in`) at that final volume, in "
        "minutes. One time for 4-6 pm at the period-average flow rate; no change within the period, "
        "no queue spillback. A model output, not observed ([G]: \"raw model results\").",
        f"- Every link has both values; {int((links.ref_volume == 0).sum()):,} links have zero volume "
        "and keep their free-flow time. Connectors are distance-based in every period ([G]).",
        "- Use: the answer key for a TAPLite replay with the same OD. Time-of-day congestion comes "
        "from TMC / QVDF, not from these fields.",
        "",
        "## allowed_use",
        "",
        _md_table(access_check.head(15)),
        "",
        *(_demand_section(dem, period) if dem is not None else []),
        "## Not converted / not found",
        "",
        "- `emme_turns.dbf` (turn penalties and bans): listed, not converted.",
        "- `@gc`, `@cycle` (signal green/cycle) are not exported, so the arterial intersection delay "
        "(VDF 1, 3) cannot be reproduced.",
        "- Class volumes for the PM period are not in the PM files.",
        "- `VOLAU` in the shapefile is not a volume and is not used.",
        "",
        "## Gates",
        "",
        _md_table(gates),
        "",
    ]
    return "\n".join(lines)


def _demand_section(dem, period) -> list[str]:
    s = dem["summary"][["mode_type", "rule", "total_vehicles", "cells_written",
                        "vehicles_written", "share_kept", "vehicles_dropped"]]
    total = dem["summary"].total_vehicles.sum()
    kept = dem["summary"].vehicles_written.sum()
    return [
        f"## Demand ({period})",
        "",
        "Built as CMAP's `Database/macros/ttables.mac` builds the period-7 tables ([C]); factors "
        "from `tod_factors.p7` = [G] TOD conversion table, TOD7. Matrices from "
        "`emmemat_c25q4_100.zip` (mf417-mf457 PM auto vehicles from the demand model; mf4-mf10 "
        "daily, factored). Files `demand/" + period + "/<mode_type>_" + period + ".csv`: "
        "`o_zone_id,d_zone_id,volume`, vehicles per 2-hour period.",
        "",
        f"- Total {total:,.0f} vehicles; written {kept:,.0f} ({kept / total:.2%}). Cells at or below "
        f"{dem['floor']} are not written and **not rescaled** (first version).",
        "- Medium and heavy trucks are in vehicles; CMAP's x2 / x3 vehicle equivalents are `pce` in "
        "`parameters/mode_type_by_period.csv`.",
        "- Airport trips (mf10) are `apv`; CMAP folds them into SOV.",
        "- Not included: park-and-ride first legs (mf59, built inside CMAP's run, not exported); "
        "bus vehicle equivalents (a link preload, replay step).",
        "",
        _md_table(s),
        "",
        "mode_type values:",
        "",
        _md_table(dem["mode_types"]),
        "",
    ]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
