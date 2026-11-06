"""Where every output column comes from: FIELD_PROVENANCE.csv and CONVERSION_REPORT.md.

Status of a column
------------------
source field     copied or converted from SCAG field(s) named in the data dictionary
documented rule  set by a rule SCAG documents (validation report, User's Guide, answers)
derived          computed by this converter from SCAG data; the method is stated
external input   from a file that is not part of the loaded-network delivery
not found        SCAG's value was not found in the files provided; what was used instead
                 is stated
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import fill
from .dictionary import DAILY, period_of

SOURCES = {
    "VR": "SCAG Model Validation Report_Final RTP24.pdf (printed page numbers)",
    "UG": "SCAG User's Guide: data/05_ModelInputs_Networks.xlsx, 06_ModelParameters.xlsx",
    "ND": "data/input/network/Data_Dictionary_loaded_network.xlsx",
    "DD": "data/input/demand/Data_Dictionary_OD_Vehicle_trip_matrix.xlsx",
    "SA": "SCAG's answers: SCAG/VDF_intro.png, capacity_time_period.png, on_ramp_parameters.png",
    "CW": "data/input/taz: TAZ_correspondence(in).csv, External Zone IDs.xlsx, T1TAZ_24RTP.shp",
    "CAP": "data/input/network/scag_link_hrcapac.csv",
    "TC": "TAPLite.cpp, TAPLite4MPO kernel source",
    "M": "measured from SCAG's loaded network by this converter",
}


def _shown(template: str) -> str:
    return (str(template).replace("{D}", "AB|BA").replace("{P}", "<P>")
            .replace("{C}", "<class>"))


def field_rows(region, context: dict) -> pd.DataFrame:
    lf = region.link_field
    cap = region.capacity
    modes = ", ".join(m.mode_type for m in region.modes)
    rows = []

    options = region.output_options
    dictionary = context["dictionary"]

    def add(file, column, status, rule, source, period="", kept="every period"):
        rows.append({"file": file, "column": column, "status": status, "rule": rule,
                     "source": source, "period": period, "kept_in_period_folder": kept})

    # node.csv
    add("node.csv", "node_id", "derived",
        "Distinct end points of the line geometries (the export has no node layer or A/B "
        "fields). Centroid nodes take their zone_id, as SCAG numbers centroid nodes by Tier-1 "
        "zone ('Node' column of External Zone IDs.xlsx). Other nodes are numbered from "
        f"{(region.raw.get('topology') or {}).get('first_road_node_id', 100001)} in "
        "first-appearance order. SCAG's own TransCAD node IDs: not found.", "shapefile geometry; CW")
    add("node.csv", "zone_id", "derived",
        "TAZ_seq_t1 of the zone whose centroid the node is; see parameters/zone_centroids.csv "
        "for the method, score and confidence of every zone.", "CW; M")
    add("node.csv", "x_coord / y_coord", "source field",
        "Line end point, reprojected from the shapefile .prj to EPSG:4326.", "shapefile geometry")
    add("node.csv", "zone_type", "documented rule",
        "internal / external / airport / seaport by zone_id range.", "VR Table 15-8 p.150; UG")
    add("node.csv", "taz_id", "source field", "TAZ_ID_t1, the id used in the trip tables.", "CW")
    add("node.csv", "centroid_method / centroid_confidence", "derived",
        "How the centroid was located.", "M")

    # link.csv: TAPlite columns
    add("link.csv", "link_id", "derived",
        "1..n after sorting by from_node_id, to_node_id (TAPlite reads links in from-node "
        "order). Same id in every period.", "")
    add("link.csv", "from_node_id / to_node_id", "documented rule",
        f"{lf('dir')}: 0 gives an AB and a BA link, 1 AB only, -1 BA only. AB runs from the "
        "first vertex to the last.", "ND (Dir)")
    add("link.csv", "dir_flag", "documented rule", "1: every row is one direction.", "")
    add("link.csv", "length", "source field", f"{lf('length_mi')} x 1609.344 (metres).",
        "ND (Length, miles)")
    add("link.csv", "vdf_length_mi", "source field", f"{lf('length_mi')} (miles).", "ND")
    add("link.csv", "lanes", "source field", f"{_shown(lf('lanes'))} for the period.",
        "ND; UG (one-directional lanes by period)")
    add("link.csv", "capacity", "external input",
        f"{_shown(cap['hourly_capacity_field'])} / {_shown(lf('lanes')).replace('<P>', cap['lanes_basis_period'])}"
        " = vehicles per lane per hour. HRCAPAC is not in the loaded shapefile or its "
        "dictionary. Basis confirmed by SCAG (hourly, per direction) and by the period "
        "factor measured from the loaded times.", "CAP; SA VDF_intro.png; M")
    add("link.csv", "hourly_link_capacity", "derived", "capacity x lanes of the period.", "CAP")
    add("link.csv", "free_speed", "source field",
        f"60 x {lf('length_mi')} / {_shown(lf('free_time_min'))}, x 1.609344 (km/h).", "ND")
    add("link.csv", "vdf_free_speed_mph", "source field",
        f"60 x {lf('length_mi')} / {_shown(lf('free_time_min'))} (mph).", "ND")
    add("link.csv", "vdf_fftt", "source field", f"{_shown(lf('free_time_min'))} (minutes).",
        "ND (calculated free-flow travel time in minute)")
    add("link.csv", "toll", "not found",
        "0. Toll amounts (User's Guide AB/BA TOLLV <P> <DA/SR2/SR3/TRK>, toll schedule) are "
        "not in the loaded shapefile.", "UG link_fields")
    add("link.csv", "toll_<mode>", "not found", f"0 for {modes}; see toll.", "UG")
    add("link.csv", "link_type", "derived",
        f"{region.area_type_multiplier} x {_shown(lf('area_type'))} + "
        f"{_shown(lf('facility_type'))}, both of which are also kept as their own columns. "
        f"Decode with divmod(link_type, {region.area_type_multiplier}); the multiplier is "
        "1000 because SCAG's facility codes reach 200 (NVTA's Cube converter uses 100).",
        "UG facility_type; region.yaml > link_type")
    add("link.csv", "allowed_use", "documented rule",
        "region.yaml > access, first matching rule; see allowed_use_rule and "
        "parameters/access_rule_check.csv.", "UG; VR p.181; M")
    add("link.csv", "vdf_type / vdf_alpha / vdf_beta", "documented rule",
        "Table 16-2 by facility group, posted speed and area type -> vdf_type 7; on-ramps "
        f"{region.vdf['on_ramp']['facility_types']} -> vdf_type {region.vdf['on_ramp']['vdf_type']}; "
        f"connectors -> vdf_type {region.vdf['connectors']['vdf_type']}, alpha 0, beta 1. "
        "See parameters/vdf_parameters.csv.",
        "VR p.160; TC; M")
    add("link.csv", "vdf_plf", "derived",
        "E / the period's own hours, E = region.yaml > vdf > period_capacity_factor, which "
        "is SCAG's \"<D> CAPA <P>\" / <D>_HRCAPACITY<P>; see parameters/period_factor.csv.",
        "SA (SCAG 50PL working network, since removed from the kit); VR p.36; M")
    add("link.csv", "ref_volume", "not found",
        "Left blank. SCAG's export has no link total, only the eight class flows "
        f"{_shown(lf('flow'))}, which are kept as their own columns in this file. Summing "
        "them is a choice - vehicles, or PCE-weighted to match the kernel's own "
        "PCE-weighted volume column - so the converter does not make it for you.", "ND")
    add("link.csv", "ref_cost", "derived", "0.", "")
    if region.output_options["geometry_separate_file"]:
        add("link.csv", "crs", "source field",
            "EPSG:4326, the CRS of network/link_geometry.csv.", "shapefile .prj")
        add("link_geometry.csv", "geometry", "source field",
            "Line geometry reprojected to EPSG:4326, WKT, 7 decimals; BA rows reversed so "
            "the line runs from -> to. Its own file because 110 links have a WKT longer than "
            "Excel's 32,767-character cell limit; join to link.csv on link_id.",
            "shapefile geometry")
    else:
        add("link.csv", "crs / geometry", "source field",
            "Line geometry reprojected to EPSG:4326; BA rows reversed.", "shapefile geometry")
    add("link.csv", "name", "source field", f"{lf('road_name')}.", "ND")
    add("link.csv", "org_link_id", "source field", f"{lf('id')}.", "ND (Link ID)")
    add("link.csv", "dir_side", "derived", "AB or BA: which set of AB_/BA_ fields the row uses.", "ND")
    add("link.csv", "facility_type / area_type / posted_speed_mph", "source field",
        f"{_shown(lf('facility_type'))}, {_shown(lf('area_type'))}, {_shown(lf('posted_speed'))}. "
        "A blank BA value takes the AB value (counts in CONVERT_MANIFEST.json).", "ND")
    add("link.csv", "vdf_group", "documented rule", "Table 16-2 row that set the VDF.", "VR p.160")
    add("link.csv", "allowed_use_rule", "documented rule", "access rule that set allowed_use.",
        "region.yaml > access")

    # link.csv: the shapefile's own fields
    for column in context["attributes"].columns:
        dbd, note = dictionary.describe(column)
        tag = period_of(dbd or column)
        if tag == "":
            kept = "every period"
        elif tag == DAILY:
            kept = "every period" if options["include_daily_fields"] else "left out"
        else:
            kept = f"{tag} folder only" if options["period_fields_only"] else "every period"
        add("link.csv", column, "source field" if dbd else "not found",
            "Shapefile field, unchanged." + (f" DBD name: {dbd}." if dbd else
                                            " Not listed in the data dictionary.")
            + (f" {note}" if note else ""), "ND" if dbd else "", period=tag, kept=kept)

    # demand, mode_type, settings
    add("<mode>_<P>.csv", "o_zone_id / d_zone_id", "source field",
        "Trip table TAZ_ID_t1 -> TAZ_seq_t1.", "DD; CW")
    add("<mode>_<P>.csv", "volume", "source field",
        "Matrix core value as written in <P>_OD.mtx.csv (vehicle trips); zero cells left out, "
        "intrazonal cells kept.", "DD")
    add("mode_type.csv", "mode_type", "source field",
        "Matrix core name with '_' for spaces (allowed_use is ';'-separated and names demand "
        "files).", "DD")
    add("mode_type.csv", "name", "source field", "Matrix core name, unchanged.", "DD")
    add("mode_type.csv", "vot", "documented rule",
        "Distance cost conversion factor x cost multiplier of the period. The toll/HOT VOT "
        "multipliers are not applied (no tolls are available).", "VR Table 16-1 p.159; UG Assignment")
    add("mode_type.csv", "pce", "documented rule",
        "User's Guide defaults: LHDT 1.2, MHDT 1.5, HHDT 2.0, cars 1. SCAG's link-specific PCE "
        "(grade, climb length, truck share) needs fields not in the export: not found.",
        "UG Assignment; VR Table 15-13")
    add("mode_type.csv", "occ", "not found",
        "DA 1 and SR2 2 by definition; SR3 is '3+' with no average found, 3 used; trucks 1.", "DD")
    add("settings.csv", "demand_period_starting_hours / ending_hours", "documented rule",
        "Period hours. TAPlite takes the period length as ending - starting, so a period "
        "that crosses midnight is written as hours past midnight: NT 21-6 becomes 21 -> 30.", "VR p.36; SA")
    add("settings.csv", "number_of_iterations / number_of_processors", "derived",
        "region.yaml > assignment. SCAG: bi-conjugate Frank-Wolfe, relative gap 0.001 or 200 "
        "iterations.", "VR p.158")
    return pd.DataFrame(rows)


def _cell(value) -> str:
    if isinstance(value, (float, np.floating)):
        return "" if np.isnan(value) else f"{value:,.4g}"
    return str(value).replace("|", "/")


def _table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


def code_counts(region, context: dict) -> list[str]:
    """Codes present in the shapefile that the SCAG documentation does not list."""
    documented = region.raw.get("documented_codes", {}) or {}
    fields = context["fields"]
    checks = [("facility_type", region.link_field("facility_type")),
              ("toll_flag", region.link_field("toll_flag")),
              ("truck_prohibit", region.link_field("truck_prohibit")),
              ("mode", region.link_field("mode"))]
    if "hov_flag" in region.raw["link_fields"]:
        checks.append(("hov_flag", region.link_field("hov_flag")))
    lines = []
    for key, template in checks:
        if key not in documented:
            continue
        names = ([fill(template, D=d) for d in ("AB", "BA")] if "{D}" in template else [template])
        for name in names:
            values = pd.Series(fields.per_record(name)).dropna()
            odd = values[~values.isin(documented[key])].value_counts().sort_index()
            if len(odd):
                listed = ", ".join(f"{v:g} ({n} records)" for v, n in odd.items())
                lines.append(f"`{name}`: {listed}")
    return lines


def write(region, root: Path, *, context: dict, factor: pd.DataFrame, ramp_check: pd.DataFrame,
          access_check: pd.DataFrame, centroids: pd.DataFrame, zone_notes: dict,
          manifest: dict, periods: list[str]) -> dict:
    table = field_rows(region, context)
    table.to_csv(root / "FIELD_PROVENANCE.csv", index=False)
    status = table["status"].value_counts().to_dict()

    lines = [f"# {region.name} conversion report", "",
             f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by "
             "`code/main_convert.py` (`code/src/scag_transcad`). Configuration: "
             "`region.resolved.json`. Every output column and its source: `FIELD_PROVENANCE.csv`.",
             "", "## Sources", ""]
    lines += [f"- **{key}** {text}" for key, text in SOURCES.items()]

    network = manifest["stages"]["network"]
    lines += ["", "## Network", "",
              f"- {network['records']:,} shapefile records, {network['fields']} fields, "
              f"CRS {network['source_crs']}.",
              f"- {network['nodes']:,} nodes rebuilt from line end points.",
              f"- {network['directed_links']:,} directed links; {network['kept_directed_links']:,} "
              f"written to link.csv; {network['excluded_not_highway']:,} left out because "
              f"MODE is not {region.access['highway_mode']} (highway); "
              f"{network['excluded_self_loops']:,} self-loops left out "
              "(`network/link_excluded.csv`).",
              ""]
    rules = manifest["stages"].get("rules", {})
    if rules:
        options_text = ", ".join(f"{k}={v}" for k, v in rules.get("output_options", {}).items())
        lines += [f"- **Tier-1 network.** {rules.get('links_written', 0):,} links and "
                  f"{rules.get('nodes_written', 0):,} nodes written. Left out: "
                  f"{rules.get('closed_links_left_out', 0):,} links closed to every mode "
                  f"(facility {region.access.get('closed_facility_types')}, the Tier-2 centroid "
                  f"connectors; SCAG's loaded flow on them is zero) and "
                  f"{rules.get('nodes_left_out', 0):,} nodes no remaining link touches - the "
                  "Tier-2 centroids. `network/link_excluded.csv` lists every dropped link.",
                  f"- `link_type` = {rules.get('link_type_rule', '')}; `facility_type` and "
                  "`area_type` are also kept as their own columns.",
                  f"- Output options: {options_text}.", ""]
    written = manifest["stages"].get("write", {})
    if written:
        lines += [_table(pd.DataFrame([{"period": p, **v} for p, v in written.items()])), ""]

    demand = manifest["stages"].get("demand", {})
    if demand:
        rows = []
        for period, stats in demand.items():
            for mode, s in stats["modes"].items():
                rows.append({"period": period, "mode_type": mode, "rows": s["rows"],
                             "trips": s["trips"], "intrazonal_trips": s["intrazonal_trips"],
                             "dropped_trips": s["dropped_trips"],
                             "positive_trips": s.get("positive_trips", s["trips"]),
                             "below_min_volume_rows": s.get("below_min_volume_rows", 0),
                             "below_min_volume_trips": s.get("below_min_volume_trips", 0.0)})
        frame = pd.DataFrame(rows)
        floor = float(region.demand_options["min_volume"])
        totals = ["rows", "trips", "intrazonal_trips", "dropped_trips", "positive_trips",
                  "below_min_volume_rows", "below_min_volume_trips"]
        by_period = frame.groupby("period", sort=False)[totals].sum().reset_index()
        by_period["kept_share_of_trips"] = (
            by_period["trips"] / by_period["positive_trips"].where(by_period["positive_trips"] > 0)
        ).round(4)
        by_mode = frame.groupby("mode_type", sort=False)[totals].sum().reset_index()
        by_mode["kept_share_of_trips"] = (
            by_mode["trips"] / by_mode["positive_trips"].where(by_mode["positive_trips"] > 0)
        ).round(4)
        lines += ["## Demand", "",
                  "Trips in cells whose origin or destination zone has no centroid are dropped.", ""]
        if floor > 0:
            lines += [f"`demand > min_volume` = {floor:g}: a cell is written only if it carries "
                      f"more than {floor:g} vehicle trips. `positive_trips` is everything SCAG's "
                      "matrix holds above zero, `below_min_volume_trips` is what the floor "
                      "removed, and `kept_share_of_trips` is the share of SCAG's trips that "
                      "reaches the run folder. The cut cells are the long tail of the matrix: "
                      "they are many rows carrying few trips. **The assignment therefore loads "
                      "less than SCAG's full demand**; raise or remove `min_volume` to load all "
                      "of it.", ""]
        lines += ["By period:", "", _table(by_period), "",
                  "By mode:", "", _table(by_mode), ""]

    lines += ["## Field sources", "", _table(pd.DataFrame(
        [{"status": k, "columns": v} for k, v in status.items()])), ""]

    lines += ["## Not found in the SCAG files, or not reproduced by TAPlite", "",
              "1. **Node layer.** No node IDs, A/B node fields or centroid flag in the export "
              "(the User's Guide node fields ZONEID, CentroidCode, Internal_Sequence_ID_T1 belong "
              "to the DBD node layer). Nodes rebuilt; centroids located as in "
              "`parameters/zone_centroids.csv`.",
              "1a. **`ccportzone`.** The field that says which connector node belongs to which "
              "port or airport zone is past the shapefile's 255-field limit. Zones with too "
              "little demand to locate by flow are placed by county and proximity instead, and "
              "carry `confidence = assumed` in `parameters/zone_centroids.csv`.",
              "2. **Hourly capacity (AB/BA_HRCAPAC).** Not in the loaded shapefile or its "
              "dictionary (the loaded export has only CAPACITY_M, the multiplier). Read from "
              "`data/input/network/scag_link_hrcapac.csv`, checked against "
              "`<D>_HRCAPACITYAM` in SCAG's 50PL working network (read once, then removed from "
              "the kit): every one of the 124,076 "
              "link IDs matches, road links agree to 0.05 veh/h (the CSV keeps one decimal) "
              "and only the dropped Tier-2 connectors differ, both values being placeholders "
              "(99,999 and 899,991).",
              "3. **Tolls.** No toll amounts in the export: `toll` = 0 on toll roads (Toll_flag "
              "11/12) and Express/HOT lanes (21/22).",
              "4. **Generalized cost terms TAPlite does not carry:** auto operating cost "
              "(20.364 c/mile, report p.158; 16.7037 in the User's Guide), HOT penalty "
              "(Table 16-1), HOV access penalty 0.5 min and mainline factor 1.1 (p.160).",
              "5. **Link-specific truck PCE** (Table 15-13: grade, climb length, truck share). "
              "User's Guide defaults 1.2 / 1.5 / 2.0 used.",
              "6. **Transit preload** (`<D>_BUSFLOW_<P>`, report p.157): kept as a field, not "
              "loaded.",
              "7. **Occupancy** of SR3 (\"3+\") and of trucks: 3 and 1 used.",
              "8. **Table 16-2 groups.** The report names the groups but not their facility "
              "codes. Freeways and HOV = 10, 20-25; Expressways = 30-32; ramps 80-89 and truck "
              "lanes 90 fall in All Others.",
              "9. **Period capacity factor.** Not stated in the report, and the V/C fields "
              "(`<D>_<P>_VOC`) are past the shapefile's 255-field limit, so they were never "
              "delivered. Taken from SCAG's own capacity pair instead; see below.",
              "10. **Truck travel time.** SCAG stores a separate truck time (`<D>_TruckTime_<P>`, "
              "about 3% above the car time on freeways); TAPlite has one time per link.", ""]
    odd = code_counts(region, context)
    if odd:
        lines += ["**Codes in the shapefile that the documentation does not list:**", ""]
        lines += [f"- {text}" for text in odd] + [""]

    lines += ["## Checks against SCAG's loaded network", "",
              "### Period capacity factor", "",
              "SCAG assigns a period against `hourly capacity x E`; TAPlite divides by "
              "`lanes x lane capacity x H x vdf_plf`, so `vdf_plf = E / H`. E is read "
              "straight from SCAG's 50PL working network - read once, then removed from the kit - "
              "as `\"<D> CAPA <P>\" / "
              "<D>_HRCAPACITY<P>`, which is a single exact integer per period on all 123,045 "
              "links that carry capacity. H is the period's own length, so `settings_hours x "
              "vdf_plf` puts SCAG's period capacity back: the `hours_x_plf` column below must "
              "equal E. The night period is nine hours while SCAG gives it eight hours of "
              "capacity, which is why NT is the only period with `vdf_plf` other than 1, and "
              "why its settings window is written as 21 -> 30 (TAPlite takes H as a plain "
              "subtraction and cannot cross midnight).", "",
              _table(factor[["period", "start_hour", "end_hour", "period_hours",
                             "settings_start_hour", "settings_end_hour", "settings_hours",
                             "E", "vdf_plf", "hours_x_plf", "E_source"]]), ""]
    if len(ramp_check):
        lines += ["### On-ramp function (facility 82, 84)", "",
                  "SCAG's loaded ramp delay beside the delay each TAPlite VDF gives for the same "
                  "loaded volume.", "",
                  _table(ramp_check[["period", "function", "links", "loaded_delay_min_median",
                                     "loaded_delay_min_p99", "predicted_delay_min_median",
                                     "predicted_delay_min_p99", "mean_abs_error_min"]]), ""]
    if len(access_check):
        summary = (access_check.groupby(["rule", "mode_type"], as_index=False)
                   [["loaded_flow_on_barred_links", "barred_links_with_flow"]].sum())
        summary = summary[summary["loaded_flow_on_barred_links"] > 0]
        lines += ["### Access rules", "",
                  "SCAG loaded flow, all periods, of classes a rule does not allow. Empty means "
                  "the rules reproduce SCAG's access coding exactly.", "",
                  _table(summary) if len(summary) else "_No barred class carries loaded flow._", ""]

    period = zone_notes["period"]
    lines += ["### Zone centroids", "",
              f"{zone_notes['resolved']:,} of {len(centroids):,} Tier-1 zones located; "
              f"{zone_notes['unresolved']} not. Flow balance uses {period} loaded flows.", "",
              _table(centroids.groupby(["zone_type", "method", "confidence"]).size()
                     .reset_index(name="zones")), ""]
    review = centroids[centroids["confidence"].isin(["medium", "low", "none"])]
    if len(review):
        keep = ["zone_id", "taz_id", "zone_type", "location", f"trip_ends_{period}", "method",
                "score", "runner_up_score", "confidence", "node_id", "note"]
        lines += ["Zones to review:", "", _table(review[[c for c in keep if c in review.columns]]), ""]

    lines += ["## Decisions for the analyst", "",
              "- `vdf > on_ramp > vdf_type`: 8 follows the report's on-ramp function; 7 gives the "
              "ramps Table 16-2 All Others. Compare both against the loaded delay above.",
              "- `vdf > period_capacity_factor`: SCAG's own E per period (default) or "
              "`clock_hours`, which would give the night period nine hours of capacity "
              "instead of SCAG's eight.",
              "- Low-confidence centroids in the table above.", ""]
    (root / "CONVERSION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return {"field_provenance": str(root / "FIELD_PROVENANCE.csv"),
            "report": str(root / "CONVERSION_REPORT.md"), "status_counts": status}
