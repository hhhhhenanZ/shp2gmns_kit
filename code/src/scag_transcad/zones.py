"""Tier-1 zone centroids for node.csv.

SCAG's trip tables (``<P>_OD.mtx``) are keyed by Tier-1 TAZ id (8 digits, e.g. 14001000).
The network export has no node layer, so no field says which node is a zone centroid.
Each zone's centroid is recovered as follows, and every decision is written to
``parameters/zone_centroids.csv``.

1. Internal zones: the node inside the zone's ``T1TAZ_24RTP`` polygon that carries Tier-1
   centroid connectors (facility type 100, User's Guide facility table). Nodes whose
   links are all connectors are preferred. A polygon with more than one candidate is
   decided by flow balance.
2. External cordon stations: SCAG codes them at the region edge rather than with
   connectors. Candidates are highway nodes within ``external_boundary_distance_m`` of the
   Tier-1 boundary, on a link in the station's county (``External Zone IDs.xlsx``).
3. Airports, seaports, and any internal zone left without a polygon candidate: the Tier-1
   connector nodes not used in step 1.

Flow balance. In SCAG's loaded network a centroid's outgoing class flows equal the zone's
trips by class, and its incoming flows the trips it attracts. A candidate's score for a
zone is ``(|out - O| + |in - D|)`` summed over the classes, divided by ``O + D``, for one
period (intrazonal trips excluded). Steps 2 and 3 are solved as one-to-one assignments, so
no node serves two zones. Scores are rounded to 0.01 before the assignment, and among
equal scores the node with fewer road neighbours wins: a divided road that ends at the
cordon carries the same flows on consecutive nodes, and the centroid is the end one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

UNRESOLVED = -1


def zone_types(zone_ids, ranges: dict) -> np.ndarray:
    ids = np.asarray(zone_ids)
    kinds = np.full(len(ids), "", dtype=object)
    for kind, (low, high) in ranges.items():
        kinds[(ids >= int(low)) & (ids <= int(high))] = kind
    if (kinds == "").any():
        raise ValueError(f"zone ids outside zones > zone_types: {sorted(ids[kinds == ''])[:10]}")
    return kinds


def load_crosswalk(region) -> pd.DataFrame:
    """Tier-1 TAZ id -> zone_id (the Tier-1 internal sequence number, 1..4192)."""
    cfg = region.zones
    id_field, seq_field = cfg["crosswalk_taz_id_field"], cfg["crosswalk_zone_field"]
    path = region.path("taz_correspondence")
    table = (pd.read_csv(path, usecols=[id_field, seq_field]).drop_duplicates()
             .rename(columns={id_field: "taz_id", seq_field: "zone_id"}))
    for column in ("taz_id", "zone_id"):
        if table[column].duplicated().any():
            raise ValueError(f"{path.name}: {id_field} -> {seq_field} is not one-to-one")
    table["zone_type"] = zone_types(table["zone_id"], cfg["zone_types"])
    return table.sort_values("zone_id").reset_index(drop=True)


def read_special_zones(path, sheet: str) -> pd.DataFrame:
    """External cordon stations, airports and seaports from ``External Zone IDs.xlsx``."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_row = next(i for i in range(len(raw)) if str(raw.iat[i, 0]).strip() == "Node")
    header = [str(v).strip() for v in raw.iloc[header_row]]
    starts = [j for j, value in enumerate(header) if value == "Node"]
    rows = []
    for number, start in enumerate(starts):
        stop = starts[number + 1] if number + 1 < len(starts) else len(header)
        names = {header[j].lower(): j for j in range(start, stop)
                 if header[j] and header[j].lower() != "nan"}
        location = next(j for key, j in names.items() if key.startswith("location"))
        county, taz, listed = names["county code"], names["taz id"], names.get("port type")
        for i in range(header_row + 1, len(raw)):
            node = pd.to_numeric(raw.iat[i, start], errors="coerce")
            if pd.isna(node):
                continue
            rows.append({
                "zone_id": int(node),
                "location": str(raw.iat[i, location]).strip(),
                "county_code": int(raw.iat[i, county]),
                "listed_taz_id": int(raw.iat[i, taz]),
                "listed_as": str(raw.iat[i, listed]).strip() if listed is not None
                else "External cordon",
            })
    return pd.DataFrame(rows)


def node_class_flows(region, fields, directed, period: str, node_count: int,
                     highway: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Loaded flow leaving and entering every node, one column per mode."""
    modes = region.modes
    a, b = directed["a"].to_numpy(), directed["b"].to_numpy()
    out = np.zeros((node_count, len(modes)))
    inn = np.zeros((node_count, len(modes)))
    template = region.link_field("flow")
    for k, mode in enumerate(modes):
        flow = np.nan_to_num(fields.per_direction(template, P=period, C=mode.flow_class))
        flow = np.where(highway, flow, 0.0)
        np.add.at(out[:, k], a, flow)
        np.add.at(inn[:, k], b, flow)
    return out, inn


def node_incidence(directed, highway, facility_type, county, connector_types) -> pd.DataFrame:
    """Facility types, counties and road-neighbour count of every highway node."""
    a = directed["a"].to_numpy()[highway]
    b = directed["b"].to_numpy()[highway]
    ft, cn = facility_type[highway], county[highway]
    ends = pd.DataFrame({"node": np.r_[a, b], "other": np.r_[b, a],
                         "ft": np.r_[ft, ft], "county": np.r_[cn, cn]})
    grouped = ends.groupby("node")

    def as_set(values):
        return frozenset(int(v) for v in values.unique() if np.isfinite(v))

    info = pd.DataFrame({"facility_types": grouped["ft"].agg(as_set),
                         "counties": grouped["county"].agg(as_set)})
    road = ends[~np.isin(ends["ft"], list(connector_types))]
    info["road_neighbors"] = (road.groupby("node")["other"].nunique()
                              .reindex(info.index).fillna(0).astype(int))
    return info


def _confidence(score: float, runner_up: float, rules: dict) -> str:
    if score <= rules["high_score"] and (not np.isfinite(runner_up)
                                         or runner_up >= rules["high_ratio"] * score):
        return "high"
    if score <= rules["medium_score"]:
        return "medium"
    return "low"


def resolve_centroids(region, topology, directed, fields, highway, facility_type,
                      crosswalk: pd.DataFrame, origins: pd.DataFrame,
                      destinations: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return one row per Tier-1 zone with its centroid node index, and run notes."""
    import geopandas as gpd
    from scipy.optimize import linear_sum_assignment
    from shapely.ops import unary_union

    cfg, rules = region.zones, region.zones["resolve"]
    connector_types = {int(v) for v in region.vdf["connectors"]["facility_types"]}
    tier1_connector = int(cfg["tier1_connector_facility_type"])
    period = str(rules["period"])
    xy = topology.node_xy
    crs = topology.frame.crs
    notes: dict = {"period": period}

    out, inn = node_class_flows(region, fields, directed, period, topology.node_count, highway)
    county = fields.per_direction(region.link_field("county"))
    incidence = node_incidence(directed, highway, facility_type, county, connector_types)

    mode_types = [m.mode_type for m in region.modes]
    zone_ids = crosswalk["zone_id"].to_numpy()
    row_of = {int(z): i for i, z in enumerate(zone_ids)}
    O = origins.reindex(zone_ids).fillna(0.0)[mode_types].to_numpy()
    D = destinations.reindex(zone_ids).fillna(0.0)[mode_types].to_numpy()
    trip_ends = O.sum(axis=1) + D.sum(axis=1)

    def score(nodes: np.ndarray, zone: int) -> np.ndarray:
        i = row_of[zone]
        gap = np.abs(out[nodes] - O[i]).sum(axis=1) + np.abs(inn[nodes] - D[i]).sum(axis=1)
        return gap / max(trip_ends[i], 1e-9)

    polygons = gpd.read_file(region.path("tier1_taz_shapefile"))
    if polygons.crs is None:
        polygons = polygons.set_crs(crs)
        notes["tier1_polygon_crs"] = "none in the file; the network CRS was assumed"
    else:
        polygons = polygons.to_crs(crs)
        notes["tier1_polygon_crs"] = str(polygons.crs)
    seq_field = cfg["tier1_zone_field"]

    facility_sets = incidence["facility_types"]
    with_connector = facility_sets[facility_sets.map(lambda s: tier1_connector in s)].index.to_numpy()
    connector_only = set(facility_sets[facility_sets.map(
        lambda s: tier1_connector in s and s <= connector_types)].index.tolist())

    records: dict[int, dict] = {}
    used: set[int] = set()

    # 1. internal zones: polygon, then flow balance among the polygon's candidates
    points = gpd.GeoDataFrame({"node": with_connector},
                              geometry=gpd.points_from_xy(xy[with_connector, 0],
                                                          xy[with_connector, 1]), crs=crs)
    joined = gpd.sjoin(points, polygons[[seq_field, "geometry"]], how="inner", predicate="within")
    for zone, group in joined.groupby(seq_field):
        zone = int(zone)
        if zone not in row_of:
            continue
        nodes = group["node"].to_numpy()
        preferred = np.array([n for n in nodes if n in connector_only], dtype=np.int64)
        pool = preferred if len(preferred) else nodes
        s = score(pool, zone)
        order = np.argsort(s, kind="stable")
        runner_up = float(s[order[1]]) if len(pool) > 1 else float("nan")
        best = int(pool[order[0]])
        records[zone] = {
            "node_index": best,
            "method": "tier1_polygon" if len(preferred) else "tier1_polygon_road_node",
            "candidates": int(len(pool)), "score": float(s[order[0]]), "runner_up_score": runner_up,
            "confidence": "high" if len(pool) == 1 else _confidence(float(s[order[0]]), runner_up, rules),
        }
        used.add(best)

    # 2-3. externals, airports, seaports, internal zones with no polygon candidate
    specials = read_special_zones(region.path("external_zones"), cfg["external_zones_sheet"])
    special_by_zone = specials.set_index("zone_id")
    kind_of = dict(zip(crosswalk["zone_id"].astype(int), crosswalk["zone_type"]))
    minimum = float(rules["min_trip_ends"])
    groups: dict[str, list[int]] = {"external": [], "connector": []}
    for zone in (int(z) for z in zone_ids):
        if zone in records:
            continue
        if trip_ends[row_of[zone]] <= minimum:
            records[zone] = {"node_index": UNRESOLVED, "method": "unresolved", "candidates": 0,
                             "score": float("nan"), "runner_up_score": float("nan"),
                             "confidence": "none",
                             "note": f"{trip_ends[row_of[zone]]:.3g} trip ends in {period}: "
                                     "no loaded flow to locate it"}
            continue
        groups["external" if kind_of[zone] == "external" else "connector"].append(zone)

    highway_nodes = incidence.index.to_numpy()
    boundary = unary_union(polygons.geometry.values).boundary
    distance = gpd.GeoSeries(gpd.points_from_xy(xy[highway_nodes, 0], xy[highway_nodes, 1]),
                             crs=crs).distance(boundary).to_numpy()
    near = highway_nodes[distance <= float(rules["external_boundary_distance_m"])]

    def solve(zones: list[int], candidates: np.ndarray, method: str, county_rule: bool) -> None:
        if not zones:
            return
        if len(candidates) < len(zones):
            raise ValueError(f"{method}: {len(zones)} zones but only {len(candidates)} candidates")
        raw = np.vstack([score(candidates, zone) for zone in zones])
        if county_rule:
            counties = incidence.loc[candidates, "counties"].to_numpy()
            for r, zone in enumerate(zones):
                if zone in special_by_zone.index:
                    code = int(special_by_zone.at[zone, "county_code"])
                    raw[r, [code not in c for c in counties]] = np.inf
        neighbors = incidence.loc[candidates, "road_neighbors"].to_numpy()
        cost = np.where(np.isfinite(raw), np.round(raw, 2) + 0.001 * np.minimum(neighbors, 9), 1e9)
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols):
            zone = zones[r]
            feasible = np.isfinite(raw[r])
            if not feasible[c]:
                records[zone] = {"node_index": UNRESOLVED, "method": "unresolved", "candidates": 0,
                                 "score": float("nan"), "runner_up_score": float("nan"),
                                 "confidence": "none", "note": "no candidate node in its county"}
                continue
            others = raw[r][feasible & (np.arange(len(candidates)) != c)]
            runner_up = float(others.min()) if len(others) else float("nan")
            chosen = float(raw[r, c])
            note = ""
            if int(neighbors[c]) > 1:
                note = (f"node also has {int(neighbors[c])} road neighbours; TAPlite does not "
                        "route through zone nodes")
            records[zone] = {"node_index": int(candidates[c]), "method": method,
                             "candidates": int(feasible.sum()), "score": chosen,
                             "runner_up_score": runner_up,
                             "confidence": _confidence(chosen, runner_up, rules), "note": note}
            used.add(int(candidates[c]))

    solve(groups["external"], np.array([n for n in near if n not in used], dtype=np.int64),
          "external_boundary_flow", county_rule=True)
    solve(groups["connector"], np.array(sorted(connector_only - used), dtype=np.int64),
          "connector_flow", county_rule=False)

    # 4. Zones no rule could place, because they carry almost no demand: the near-empty
    # port and airport zones. Their connectors are in the network; only the zone id is
    # missing. SCAG's ccportzone field says which node is which terminal, but it is past
    # the shapefile's 255-field limit, so each takes an unused connector node in its own
    # county, near the located zones of its own type, paired zone id against node position.
    # The set of nodes is right; the terminal-level pairing is an assumption, marked so.
    if bool(rules.get("place_unmatched_specials", False)):
        pool = sorted(connector_only - used)
        limit = float(rules.get("assumed_max_km", 15.0)) * 1000.0
        for kind in ("airport", "seaport", "external", "internal"):
            anchors = np.array([records[z]["node_index"] for z in row_of
                                if kind_of[z] == kind and records[z]["node_index"] >= 0],
                               dtype=np.int64)
            waiting = sorted(z for z in row_of if kind_of[z] == kind
                             and records[z]["method"] == "unresolved"
                             and z in special_by_zone.index)
            for zone in waiting:
                code = int(special_by_zone.at[zone, "county_code"])
                in_county = [n for n in pool if code in incidence.at[n, "counties"]]
                nearby = in_county
                if len(anchors) and in_county:
                    close = [n for n in in_county
                             if np.min(np.hypot(xy[anchors, 0] - xy[n, 0],
                                                xy[anchors, 1] - xy[n, 1])) <= limit]
                    # Proximity narrows the choice where it can; a county with no located
                    # zone of this type (Ventura's one airport) keeps the county list.
                    nearby = close or in_county
                if not nearby:
                    continue
                nearby.sort(key=lambda n: (xy[n, 0], xy[n, 1]))
                node = int(nearby[0])
                pool.remove(node)
                used.add(node)
                records[zone] = {
                    "node_index": node, "method": "assumed_by_location",
                    "candidates": len(nearby), "score": float("nan"),
                    "runner_up_score": float("nan"), "confidence": "assumed",
                    "note": f"too little demand to locate by flow; took an unused connector "
                            f"node in county {code} near the located {kind} zones. SCAG's "
                            "ccportzone would confirm which terminal this is."}

    table = crosswalk.copy()
    for column in ("node_index", "method", "candidates", "score", "runner_up_score",
                   "confidence", "note"):
        table[column] = [records[int(z)].get(column, "") for z in zone_ids]
    table["node_index"] = table["node_index"].astype(np.int64)
    table["trip_ends_" + period] = trip_ends
    table = table.merge(specials[["zone_id", "location", "county_code", "listed_as",
                                  "listed_taz_id"]], on="zone_id", how="left")
    mismatch = table["listed_taz_id"].notna() & (table["listed_taz_id"] != table["taz_id"])
    notes["external_zone_taz_id_mismatches"] = int(mismatch.sum())
    road = table["node_index"] >= 0
    table["road_neighbors"] = 0
    table.loc[road, "road_neighbors"] = (incidence["road_neighbors"]
                                         .reindex(table.loc[road, "node_index"]).fillna(0)
                                         .astype(int).to_numpy())
    notes["resolved"] = int(road.sum())
    notes["unresolved"] = int((~road).sum())
    notes["by_confidence"] = table["confidence"].value_counts().to_dict()
    notes["by_method"] = table["method"].value_counts().to_dict()
    return table, notes
