"""A8 step 1: PM (period 7, 4-6 pm) check of CMAP's link times, VMT and VHT with CMAP's own class volumes.

Part 1 (CMAP self-check): CMAP's period-7 class volumes -> CMAP fd1-fd8 (cmap_vdf.py) -> link time, VMT, VHT,
        against CMAP's timau and @vadt.
Part 2 (assignment check): TAPLite R4 (CMAP fd1-fd8, ul2, class tolls, bus preload; A5) assigned class volumes,
        link times, VMT and VHT against CMAP's period-7 class volumes, timau and @vadt.

Units: CMAP class columns are vehicle equivalents (veq): medium x2, heavy x3, bus x3. Vehicles (= @vadt) =
auto + HOV2 + HOV3 + B-plate + light + medium/2 + heavy/3 (no bus). V in the link-time functions = all classes + busveq (veq).
VMT = vehicles x length; VHT = vehicles x time / 60 (no bus, as in CMAP @vadt).
Usage: python a8_1_tables.py <ROOT>   (ROOT = materails_tensor_city_1005)
"""
import io, os, sys, zipfile
import numpy as np, pandas as pd, openpyxl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmap_vdf import link_time

ROOT = sys.argv[1]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "outputs")
P = lambda *a: os.path.join(ROOT, *a)
NEW = P("CMAP_model", "cmap_vehicle_volume_per_period", "c25q4_100_link_volume_by_vehtype", "c25q4_100_link_volume_by_vehtype.csv")
NETZIP = P("CMAP_model", "c25q4_100", "emmenet_highway_c25q4_100.zip")
A = P("1_papers", "paperA_1108", "Ncurve_tasks_1122", "A_cmap_agency_check")
SHEET = os.path.join(A, "A2_relabel_JO", "outputs", "I9094WB_PM_CMAP_only_v5_A2.xlsx")
A4 = os.path.join(A, "A4_truck_share", "outputs", "a4_link_table.csv")
R4 = os.path.join(HERE, "inputs", "taplite_R4_links_pm.csv.gz")
FAC = {1: "Arterial", 2: "Freeway", 3: "Ramp to arterial", 4: "Expressway", 5: "Freeway ramp", 6: "Connector", 7: "Toll link", 8: "Metered ramp"}
log = []
def say(s): print(s); log.append(str(s))

# ---------------------------------------------------------------- CMAP period 7: network, attribs, class volumes
zf = zipfile.ZipFile(NETZIP)
rows, on = [], False
for line in io.TextIOWrapper(zf.open("network_p7.txt"), encoding="utf-8", errors="ignore"):
    if line.startswith("t links"): on = True; continue
    if on and line.startswith("a"):
        s = line.split(); rows.append((int(s[1]), int(s[2]), float(s[3]), float(s[6]), int(s[7]), float(s[8]), float(s[9]), float(s[10])))
L = pd.DataFrame(rows, columns=["i", "j", "length_mi", "lanes", "vdf", "ul1", "ul2", "ul3"])
at = pd.read_csv(io.TextIOWrapper(zf.open("attribs_p7.txt")), sep=r"\s+")[["i_node", "j_node", "@vadt", "timau"]]
at.columns = ["i", "j", "vadt", "timau"]
N = pd.read_csv(NEW); N = N[N.timeperiod == 7].drop(columns="timeperiod").rename(columns={"i_node": "i", "j_node": "j"})
D = L.merge(at, on=["i", "j"]).merge(N, on=["i", "j"])
D["cmap_id"] = D.i.astype(str) + "-" + D.j.astype(str)
D["facility"] = D.vdf.map(FAC)
D["auto"] = D.avauv + D.avh2v + D.avh3v
D["veh"] = D.auto + D.avbqv + D.avlqv + D.avmqv / 2 + D.avhqv / 3
say(f"PM links {len(D)}; max |vehicles - @vadt| {np.abs(D.veh - D.vadt).max():.4f}")
D["V_real"] = D[["avauv", "avh2v", "avh3v", "avbqv", "avlqv", "avmqv", "avhqv", "busveq"]].sum(axis=1)

D["t_real"] = link_time(D.vdf, D.V_real, D.ul1, D.ul2, D.ul3, D.length_mi)
D["ratio_real"] = D.t_real / D.timau.replace(0, np.nan)
D["x_real"] = np.where(D.ul2 > 1, D.V_real / D.ul2, np.nan)

def summarize(g, tcol, vcol="vadt"):
    r = (g[tcol] / g.timau.replace(0, np.nan) - 1).abs()
    return dict(links=len(g), time_within_1pct=float((r <= .01).mean()), time_within_5pct=float((r <= .05).mean()),
                VMT_calc=float((g[vcol] * g.length_mi).sum()), VMT_CMAP=float((g.vadt * g.length_mi).sum()),
                VHT_calc=float((g[vcol] * g[tcol]).sum() / 60), VHT_CMAP=float((g.vadt * g.timau).sum() / 60))

D[["cmap_id", "vdf", "facility", "length_mi", "lanes", "ul2", "vadt", "V_real", "x_real", "timau", "t_real", "ratio_real"]].to_csv(
    os.path.join(OUT, "a8_part1_links_pm.csv.gz"), index=False, compression="gzip")

# ---------------------------------------------------------------- Part 1: by facility
rows = []
for lab, tcol in [("CMAP class volumes", "t_real")]:
    for v in list(range(1, 9)) + ["all"]:
        g = D if v == "all" else D[D.vdf == v]
        s = summarize(g, tcol); s.update(volumes=lab, vdf=v, facility="All" if v == "all" else FAC[v])
        s["VMT_ratio"] = s["VMT_calc"] / s["VMT_CMAP"]; s["VHT_ratio"] = s["VHT_calc"] / s["VHT_CMAP"]
        rows.append(s)
P1 = pd.DataFrame(rows)[["volumes", "vdf", "facility", "links", "time_within_1pct", "time_within_5pct", "VMT_calc", "VMT_CMAP", "VMT_ratio", "VHT_calc", "VHT_CMAP", "VHT_ratio"]]
P1.to_csv(os.path.join(OUT, "a8_part1_cmap_selfcheck_by_facility.csv"), index=False)
say("Part 1 by facility:\n" + P1[["volumes", "facility", "links", "time_within_1pct", "time_within_5pct", "VHT_ratio"]].round(4).to_string(index=False))

# ---------------------------------------------------------------- Part 1: corridor (55 CMAP links, 77 TMC rows)
a4 = pd.read_csv(A4)[["cmap_id", "road_order", "section"]]
ws = openpyxl.load_workbook(SHEET, data_only=True, read_only=True)["CMAP_only"]
sh = []
for r in ws.iter_rows(min_row=2, values_only=True):
    if r[2]: sh.append(dict(sheet_row=r[0], tmc=r[1], cmap_id=str(r[2])))
sh = pd.DataFrame(sh)
say(f"corridor sheet: {len(sh)} TMC rows, {sh.cmap_id.nunique()} CMAP links")
cols = ["cmap_id", "vdf", "facility", "length_mi", "lanes", "ul1", "ul2", "avauv", "avh2v", "avh3v", "avbqv", "avlqv", "avmqv", "avhqv", "busveq",
        "vadt", "V_real", "x_real", "timau", "t_real", "ratio_real"]
CL = a4.merge(D[cols], on="cmap_id", how="left").sort_values("road_order")
CL["VMT_CMAP"] = CL.vadt * CL.length_mi
CL["VHT_CMAP"] = CL.vadt * CL.timau / 60
CL["VHT_calc"] = CL.vadt * CL.t_real / 60
CL.to_csv(os.path.join(OUT, "a8_part1_corridor_links.csv"), index=False)
T77 = sh.merge(CL, on="cmap_id", how="left")
T77.to_csv(os.path.join(OUT, "a8_part1_corridor_77_rows.csv"), index=False)
say(f"corridor links: {len(CL)}; time within 1 %: {(CL.ratio_real.sub(1).abs() <= .01).sum()}, within 5 %: {(CL.ratio_real.sub(1).abs() <= .05).sum()}; "
    f"corridor VHT calc/CMAP {CL.VHT_calc.sum() / CL.VHT_CMAP.sum():.4f}; max |time ratio - 1| {CL.ratio_real.sub(1).abs().max():.5f}")
# ---------------------------------------------------------------- Part 2: TAPLite R4 against CMAP
T = pd.read_csv(R4).rename(columns={"org_link_id": "cmap_id"})
M = D.merge(T, on="cmap_id", how="inner", suffixes=("", "_tap"))
say(f"TAPLite R4 links matched {len(M)} of {len(T)}")
M["tap_auto"] = M.mod_vol_car; M["tap_B"] = M.mod_vol_btrk; M["tap_L"] = M.mod_vol_ltrk; M["tap_M"] = M.mod_vol_mtrk; M["tap_H"] = M.mod_vol_htrk
M["tap_veh"] = M[["tap_auto", "tap_B", "tap_L", "tap_M", "tap_H"]].sum(axis=1)
M["cm_auto"] = M.auto; M["cm_B"] = M.avbqv; M["cm_L"] = M.avlqv; M["cm_M"] = M.avmqv / 2; M["cm_H"] = M.avhqv / 3; M["cm_veh"] = M.vadt
CLS = [("All vehicles", "veh"), ("Auto (SOV+HOV)", "auto"), ("B-plate truck", "B"), ("Light truck", "L"), ("Medium truck", "M"), ("Heavy truck", "H")]
GRP = [("Freeway", [2]), ("Expressway", [4]), ("Arterial", [1]), ("Ramps (3, 5, 8)", [3, 5, 8]), ("Connector", [6]), ("Toll link", [7]), ("All", list(range(1, 9)))]

def geh(m, c):  # hourly flows (period is 2 h)
    m, c = m / 2, c / 2
    return np.sqrt(2 * (m - c) ** 2 / np.maximum(m + c, 1e-9))

rows = []
for gname, vds in GRP:
    g = M[M.vdf.isin(vds)]
    for cname, k in CLS:
        m, c = g["tap_" + k], g["cm_" + k]
        big = c >= 100
        ss_res = ((m - c) ** 2).sum(); ss_tot = ((c - c.mean()) ** 2).sum()
        rows.append(dict(facility=gname, vehicle_class=cname, links=len(g),
                         VMT_TAPLite=float((m * g.length_mi).sum()), VMT_CMAP=float((c * g.length_mi).sum()),
                         VMT_ratio=float((m * g.length_mi).sum() / max((c * g.length_mi).sum(), 1e-9)),
                         link_volume_R2=float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
                         link_volume_pct_RMSE=float(np.sqrt(((m - c) ** 2).mean()) / max(c.mean(), 1e-9)),
                         links_CMAP_ge_100=int(big.sum()),
                         share_within_10pct_of_links_ge_100=float(((m - c).abs() <= .1 * c)[big].mean()) if big.any() else np.nan,
                         share_GEH_lt_5=float((geh(m, c) < 5).mean())))
P2 = pd.DataFrame(rows); P2.to_csv(os.path.join(OUT, "a8_part2_taplite_class_volume_by_facility.csv"), index=False)
say("Part 2 class volume, all facilities:\n" + P2[P2.facility == "All"][["vehicle_class", "VMT_ratio", "link_volume_R2", "link_volume_pct_RMSE", "share_GEH_lt_5"]].round(4).to_string(index=False))
say("Part 2 class VMT ratio by facility:\n" + P2.pivot(index="vehicle_class", columns="facility", values="VMT_ratio").round(3).to_string())

rows = []
for gname, vds in GRP:
    g = M[M.vdf.isin(vds)]
    r = (g.travel_time / g.timau.replace(0, np.nan) - 1).abs()
    rows.append(dict(facility=gname, links=len(g),
                     VMT_TAPLite=float((g.tap_veh * g.length_mi).sum()), VMT_CMAP=float((g.vadt * g.length_mi).sum()),
                     VHT_TAPLite=float((g.tap_veh * g.travel_time).sum() / 60), VHT_CMAP=float((g.vadt * g.timau).sum() / 60),
                     time_within_5pct=float((r <= .05).mean()), median_time_ratio=float((g.travel_time / g.timau.replace(0, np.nan)).median())))
P2b = pd.DataFrame(rows); P2b["VMT_ratio"] = P2b.VMT_TAPLite / P2b.VMT_CMAP; P2b["VHT_ratio"] = P2b.VHT_TAPLite / P2b.VHT_CMAP
P2b.to_csv(os.path.join(OUT, "a8_part2_taplite_vmt_vht_by_facility.csv"), index=False)
say("Part 2 VMT/VHT by facility:\n" + P2b[["facility", "links", "VMT_ratio", "VHT_ratio", "time_within_5pct", "median_time_ratio"]].round(4).to_string(index=False))

keep = ["cmap_id", "vdf", "facility", "length_mi", "vadt", "timau", "t_real", "travel_time", "tap_veh", "cm_auto", "tap_auto", "cm_B", "tap_B", "cm_L", "tap_L", "cm_M", "tap_M", "cm_H", "tap_H"]
M[keep].to_csv(os.path.join(OUT, "a8_links_pm.csv.gz"), index=False, compression="gzip")
open(os.path.join(OUT, "a8_log.txt"), "w").write("\n".join(log) + "\n")
