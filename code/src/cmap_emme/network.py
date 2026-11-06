"""node.csv and link.csv from the period shapefiles and the extra-attribute file.

Rules: CMAP_network_workplan.md section 4. Units: section 4.8 (kit convention,
code/src/dtalite4cube/unit_contract.py): length in metres, free_speed in km/h,
capacity in vehicles per hour per lane, times in minutes, coordinates EPSG:4326.

Reference fields: ref_volume, ref_time, timau
---------------------------------------------
CMAP runs a static equilibrium assignment for each period. The PM period (4-6 pm) loads
the 2-hour OD at once; at equilibrium every link ends with one volume and one time:

* ``ref_volume`` = DATA1 (= @vadt): vehicles on the link over the whole 2-hour period
  (not per hour) [G "PM Peak Highway Network Shapefiles"].
* ``ref_time`` = ``timau`` = TIMAU: the link's VDF time (fd1-fd8, [C] vdf_tod.in) at that
  final volume, in minutes. Volume and capacity both cover 2 hours, so it is ONE time for
  4-6 pm, at the period-average flow rate: no within-period change, no queue spillback.
  It is a model output, not observed data [G: "raw model results"].
* Every link has both values. Zero-volume links (2,823 in PM) get their free-flow time;
  connectors (VDF 6) are distance-based in every period [G].
* Check: 3634-11223 (freeway, 3 lanes): v = 4,605, ul2 = 0.75 x 2,000 x 3 x 2 = 9,000,
  fd2 -> 0.50 min vs TIMAU 0.52 min; the gap is CMAP's vehicle/bus equivalents (heavy
  truck = 3), which DATA1 does not carry. fd5, fd8 at DATA1 reproduce TIMAU (median 0.0 %).
* Use: the answer key for a TAPLite replay with the same OD (volumes and times should come
  back close to ref_volume and ref_time). For time-of-day congestion use TMC / QVDF instead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import crs

METERS_PER_MILE = 1609.344
KPH_PER_MPH = 1.609344

LINK_COLUMNS = [
    "link_id", "from_node_id", "to_node_id", "dir_flag", "length", "lanes", "capacity",
    "free_speed", "toll", "link_type", "allowed_use", "vdf_type", "vdf_alpha", "vdf_beta",
    "vdf_plf", "ref_volume", "ref_time", "vdf_free_speed_mph", "vdf_length_mi", "vdf_fftt",
    "org_link_id", "vdf_code", "facility_type", "capacity_source", "hourly_link_capacity",
    "tipid", "width", "parkl", "sigic", "timau",
]
NODE_COLUMNS = ["node_id", "zone_id", "x_coord", "y_coord", "node_type", "cmap_label"]


def build_nodes(raw: pd.DataFrame, region) -> tuple[pd.DataFrame, str]:
    f, z = region.nodes, region.raw["zones"]
    lon, lat, method = crs.to_wgs84(raw[f["x"]].to_numpy(), raw[f["y"]].to_numpy())
    node_id = raw[f["id"]].astype(np.int64).to_numpy()
    is_zone = pd.to_numeric(raw[f["zone_flag"]], errors="coerce").fillna(0).to_numpy() == 1
    nodes = pd.DataFrame({
        "node_id": node_id,
        "zone_id": np.where(is_zone, node_id, -1),
        "x_coord": np.round(lon, 8),
        "y_coord": np.round(lat, 8),
        "node_type": np.where(is_zone, "centroid", "road"),
        "cmap_label": raw[f["label"]].astype(str).to_numpy(),
        "_x_ft": raw[f["x"]].to_numpy(float),
        "_y_ft": raw[f["y"]].to_numpy(float),
    })
    nodes["zone_id"] = nodes["zone_id"].astype("Int64").where(nodes["zone_id"] > 0)
    return nodes.sort_values("node_id").reset_index(drop=True), method


def build_links(raw: pd.DataFrame, extra: pd.DataFrame, region, hours: float) -> pd.DataFrame:
    lf, ef = region.links, region.extra
    key = raw[[lf["inode"], lf["jnode"]]].astype(np.int64)
    key.columns = ["_i", "_j"]
    ex = extra.rename(columns={ef["inode"]: "_i", ef["jnode"]: "_j"})
    joined = pd.concat([key, raw.reset_index(drop=True)], axis=1).merge(
        ex, on=["_i", "_j"], how="left", validate="one_to_one", indicator=True)
    functions = {int(k): v for k, v in region.vdf["functions"].items()}
    fixed = set(region.raw["toll"]["fixed_vdf_codes"])

    length_mi = joined[lf["length_mi"]].to_numpy(float)
    ftime = joined[ef["free_time_min"]].to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ffs_mph = np.where(ftime > 0, length_mi / ftime * 60.0, np.nan)
    vdf_code = joined[lf["vdf"]].astype(int)
    lanes = joined[lf["lanes"]].to_numpy(float)
    toll_raw = joined[ef["toll"]].to_numpy(float)
    emcap = joined[ef["lane_capacity"]].to_numpy(float)

    links = pd.DataFrame({
        "link_id": np.arange(1, len(joined) + 1),
        "from_node_id": joined["_i"].to_numpy(),
        "to_node_id": joined["_j"].to_numpy(),
        "dir_flag": 1,
        "length": np.round(length_mi * METERS_PER_MILE, 3),
        "lanes": lanes.astype(int),
        "free_speed": np.round(ffs_mph * KPH_PER_MPH, 4),
        # @toll is already dollars per link in the Emme network: CMAP's assignment adds it as
        # the link cost unchanged [C SOLA_assignment.py]. The per-mile rate in [A Table 1] is the
        # MHN field TOLLDOLLARS, converted before the Emme export.
        "toll": toll_raw,
        "link_type": vdf_code.to_numpy(),
        "vdf_plf": 1.0,
        "vdf_free_speed_mph": np.round(ffs_mph, 4),
        "vdf_length_mi": length_mi,
        "vdf_fftt": ftime,
        "org_link_id": joined[lf["id"]].astype(str).to_numpy(),
        "vdf_code": vdf_code.to_numpy(),
        "facility_type": vdf_code.map(lambda c: functions[c]["name"]).to_numpy(),
        "tipid": joined[ef["tip_id"]].to_numpy(),
        "width": joined[ef["lane_width_ft"]].to_numpy(float),
        "parkl": joined[ef["parking_lanes"]].to_numpy(float),
        "sigic": joined[ef["signal_interconnect"]].to_numpy(float),
        "ref_volume": joined[lf["volume"]].to_numpy(float),   # DATA1, vehicles per PM period
        "ref_time": joined[lf["time"]].to_numpy(float),       # TIMAU, minutes
        "timau": joined[lf["time"]].to_numpy(float),
        "_modes": joined[lf["modes"]].astype(str).to_numpy(),
        "_speed": joined[ef["speed_mph"]].to_numpy(float),
        "_toll_raw": toll_raw,
        "_emcap": emcap,
        "_vadt": joined[ef["volume"]].to_numpy(float),
        "_timau": joined[ef["time"]].to_numpy(float),
        "_joined": (joined["_merge"] == "both").to_numpy(),
    })
    return links


def finish_links(links: pd.DataFrame) -> pd.DataFrame:
    links["hourly_link_capacity"] = links["capacity"] * links["lanes"]
    return links


def geometry_table(links: pd.DataFrame, lines: list[np.ndarray]) -> tuple[pd.DataFrame, str]:
    counts = np.array([len(c) for c in lines])
    allpts = np.vstack([c for c in lines if len(c)]) if counts.sum() else np.empty((0, 2))
    lon, lat, method = crs.to_wgs84(allpts[:, 0], allpts[:, 1])
    out, pos = [], 0
    for n in counts:
        seg = zip(lon[pos:pos + n], lat[pos:pos + n])
        out.append("LINESTRING (" + ", ".join(f"{x:.7f} {y:.7f}" for x, y in seg) + ")"
                   if n else "")
        pos += n
    frame = pd.DataFrame({"link_id": links["link_id"], "org_link_id": links["org_link_id"],
                          "crs": "EPSG:4326", "geometry": out})
    return frame, method
