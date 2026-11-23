"""CMAP period capacity (ul2) by period and link, from CMAP's own c25q4_100 Emme networks.

Rule (CMAP TOD_network_prep.py, lines 149-158 and 176-221):
    ul2 = 0.75 * @emcap * lanes * hours   for vdf 1-5
    ul2 = 1.00 * @emcap * lanes * hours   for vdf 8 (metered ramps)
    ul2 = 1 (placeholder) for vdf 6, 7 (connectors, toll links: no capacity term)
hours = {1:5, 2:1, 3:2, 4:1, 5:4, 6:2, 7:2, 8:2}; period 1 is 8pm-6am (10 clock hours) but is set to 5.
@emcap is the lane capacity at LOS E (veh/h/lane) from Ftime_capacity.py; it does not depend on the period.
Input: CMAP's emmenet_highway_c25q4_100.zip, read directly (no unzipping). It holds network_p1..p8.txt (Data2 = ul2)
and attribs_p1..p8.txt (@emcap). Download the c25q4_100 package from the CMAP Data Hub (see README.md).
The script looks for the zip in, in order: the path given as the first argument; ../c25q4_100/ (one level above the kit,
as for emmemat_c25q4_100.zip); data/input/cmap/network/. A folder holding the 16 unzipped files also works.
Usage (from the kit root): python data/output/cmap/report/period_capacity/period_capacity.py [zip_or_folder] [out_dir]
"""
import sys, os, io, zipfile
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
ZIP_NAME = "emmenet_highway_c25q4_100.zip"
CANDIDATES = ([sys.argv[1]] if len(sys.argv) > 1 else []) + [
    os.path.join(KIT, "..", "c25q4_100", ZIP_NAME),
    os.path.join(KIT, "data", "input", "cmap", "network", ZIP_NAME)]
SRC = next((c for c in CANDIDATES if os.path.exists(c)), None)
if SRC is None:
    sys.exit("emmenet_highway_c25q4_100.zip not found. Download the c25q4_100 package from the CMAP Data Hub "
             "(see README.md) and put the zip in ../c25q4_100/ or data/input/cmap/network/, or pass its path.")
ZF = zipfile.ZipFile(SRC) if zipfile.is_zipfile(SRC) else None
print("reading", os.path.abspath(SRC))


def open_member(name):
    """Open network_pX.txt / attribs_pX.txt from the zip or from an unzipped folder."""
    if ZF is not None:
        return io.TextIOWrapper(ZF.open(name), encoding="utf-8", errors="ignore")
    return open(os.path.join(SRC, name), encoding="utf-8", errors="ignore")


OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
CLOCK = {1: "8pm-6am", 2: "6-7am", 3: "7-9am", 4: "9-10am", 5: "10am-2pm", 6: "2-4pm", 7: "4-6pm", 8: "6-8pm"}
CLOCK_H = {1: 10, 2: 1, 3: 2, 4: 1, 5: 4, 6: 2, 7: 2, 8: 2}
MODEL_H = {1: 5, 2: 1, 3: 2, 4: 1, 5: 4, 6: 2, 7: 2, 8: 2}
NAME = {1: "overnight", 2: "early AM shoulder", 3: "AM peak", 4: "late AM shoulder", 5: "midday",
        6: "early PM shoulder", 7: "PM peak", 8: "evening"}


def factor(vdf):
    return np.where(np.isin(vdf, [1, 2, 3, 4, 5]), 0.75, np.where(vdf == 8, 1.0, np.nan))


def read_links(p):
    rows, on = [], False
    with open_member(f"network_p{p}.txt") as f:
        for line in f:
            if line.startswith("t links"):
                on = True; continue
            if on and line.startswith("a"):
                s = line.split()
                rows.append((int(s[1]), int(s[2]), float(s[3]), s[4], int(s[5]), float(s[6]), int(s[7]),
                             float(s[8]), float(s[9]), float(s[10])))
    return pd.DataFrame(rows, columns=["i_node", "j_node", "length_mi", "modes", "link_type", "lanes", "vdf",
                                       "ul1_ftime_min", "ul2_emme", "ul3"])


frames = []
for p in range(1, 9):
    L = read_links(p)
    A = pd.read_csv(open_member(f"attribs_p{p}.txt"), sep=r"\s+")
    A = A[["i_node", "j_node", "@emcap", "@vadt", "timau"]].rename(
        columns={"@emcap": "emcap_vphpl", "@vadt": "vadt_period_veh", "timau": "timau_min"})
    d = L.merge(A, on=["i_node", "j_node"], how="left")
    d.insert(2, "timeperiod", p)
    d["period_clock"] = CLOCK[p]
    d["clock_hours"] = CLOCK_H[p]
    d["model_hours"] = MODEL_H[p]
    d["cap_factor"] = factor(d["vdf"].values)
    d["hourly_cap_lane_vphpl"] = d["cap_factor"] * d["emcap_vphpl"]
    d["hourly_cap_link_vph"] = d["cap_factor"] * d["emcap_vphpl"] * d["lanes"]
    d["period_cap_calc_veh"] = d["hourly_cap_link_vph"] * d["model_hours"]
    d["period_cap_ratio_to_hourly"] = d["model_hours"] * d["cap_factor"]
    d["ul2_check_abs_diff"] = (d["period_cap_calc_veh"] - d["ul2_emme"]).abs()
    frames.append(d)

D = pd.concat(frames, ignore_index=True)
cap = D["vdf"].isin([1, 2, 3, 4, 5, 8])
D["ul2_match"] = np.where(cap, D["ul2_check_abs_diff"] <= 0.5 + 1e-4 * D["ul2_emme"].abs(), np.nan)

cols = ["i_node", "j_node", "timeperiod", "period_clock", "clock_hours", "model_hours", "vdf", "link_type",
        "length_mi", "lanes", "emcap_vphpl", "cap_factor", "hourly_cap_lane_vphpl", "hourly_cap_link_vph",
        "period_cap_ratio_to_hourly", "period_cap_calc_veh", "ul2_emme", "ul2_check_abs_diff", "ul2_match",
        "ul1_ftime_min", "vadt_period_veh", "timau_min"]
D[cols].to_csv(os.path.join(OUT, "cmap_link_period_capacity_c25q4_100.csv"), index=False)

# lanes that change by period (reversible lanes, peak-only lanes)
W = D[D["vdf"].isin([1, 2, 3, 4, 5, 8])].pivot_table(index=["i_node", "j_node"], columns="timeperiod",
                                                     values="lanes", aggfunc="first")
W.columns = [f"lanes_p{c}" for c in W.columns]
var = W[W.nunique(axis=1, dropna=False) > 1].reset_index()
var.to_csv(os.path.join(OUT, "cmap_links_lanes_vary_by_period.csv"), index=False)

# period rule table
R = []
for p in range(1, 9):
    for v, lab in [(2, "freeway"), (4, "expressway"), (1, "arterial"), (3, "fwy/exp-to-arterial ramp"),
                   (5, "fwy-to-fwy ramp"), (8, "metered entrance ramp")]:
        s = D[(D.timeperiod == p) & (D.vdf == v)]
        f = 0.75 if v != 8 else 1.0
        R.append(dict(timeperiod=p, period_name=NAME[p], period_clock=CLOCK[p], clock_hours=CLOCK_H[p],
                      model_hours=MODEL_H[p], vdf=v, facility=lab, cap_factor=f,
                      hourly_cap_formula=f"{f} * @emcap * lanes",
                      period_cap_formula=f"ul2 = {f} * @emcap * lanes * {MODEL_H[p]}",
                      period_to_hourly_ratio=f * MODEL_H[p],
                      period_cap_per_lane_if_emcap2000=f * 2000 * MODEL_H[p],
                      n_links=len(s), lane_miles=round((s.lanes * s.length_mi).sum(), 1),
                      emcap_median=s.emcap_vphpl.median(), emcap_min=s.emcap_vphpl.min(), emcap_max=s.emcap_vphpl.max(),
                      hourly_cap_link_median=s.hourly_cap_link_vph.median(),
                      ul2_median=s.ul2_emme.median(),
                      ul2_match_share=float(s.ul2_match.mean()) if len(s) else np.nan,
                      source="TOD_network_prep.py L149-158, L176-221; Ftime_capacity.py (@emcap); data_user_guide.html (period hours)"))
pd.DataFrame(R).to_csv(os.path.join(OUT, "cmap_period_capacity_rules.csv"), index=False)

m = D[cap]
print("links per period:", D.groupby("timeperiod").size().to_dict())
print("ul2 match share (vdf 1-5,8):", round(m.ul2_match.mean(), 5), " mismatches:", int((m.ul2_match == 0).sum()))
print(m[m.ul2_match == 0].groupby(["timeperiod", "vdf"]).size().head(20))
print("links with lanes varying by period:", len(var))
print(D[(D.i_node == 21416) & (D.j_node == 21403)][["timeperiod", "vdf", "lanes", "emcap_vphpl", "cap_factor",
                                                     "model_hours", "period_cap_calc_veh", "ul2_emme"]].to_string(index=False))
