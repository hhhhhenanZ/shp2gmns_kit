"""A8 step 4 (tracker 1.5): network totals by facility type, ours against CMAP, with CMAP's own class volumes.
CMAP's period VHT field @pvht ("p" = period, not PM; one per period, summed into the daily @vht in the macro) is not in any exported file (attribs_p1..p8, the three shapefiles); it is computed in CMAP's
vht.summary_v3_7c.mac as vehicles x timau / 60 with vehicles = auto + B-plate + light + medium/2 + heavy/3 + bus/3.
Here: CMAP PM VHT = that formula with CMAP's timau; ours = same vehicles x our link time (CMAP fd1-fd8, cmap_vdf.py).
Daily: CMAP's published daily @vadt (includes bus / 3, unlike the period @vadt; VMT = @vadt x length) and daily @vht (highwayshp_c25q4_100.zip);
ours = sum over the 8 periods of the same quantities from the period class volumes and our link times.
Usage: python a8_4_network_by_facility.py <ROOT>"""
import io, os, struct, sys, zipfile
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmap_vdf import link_time
ROOT = sys.argv[1]; OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
C = os.path.join(ROOT, "CMAP_model", "c25q4_100")
zf = zipfile.ZipFile(os.path.join(C, "emmenet_highway_c25q4_100.zip"))
N = pd.read_csv(os.path.join(ROOT, "CMAP_model", "cmap_vehicle_volume_per_period", "c25q4_100_link_volume_by_vehtype", "c25q4_100_link_volume_by_vehtype.csv"))
CL = ["avauv", "avh2v", "avh3v", "avbqv", "avlqv", "avmqv", "avhqv", "busveq"]
N["V"] = N[CL].sum(axis=1)
N["veh_bus"] = N.avauv + N.avh2v + N.avh3v + N.avbqv + N.avlqv + N.avmqv / 2 + N.avhqv / 3 + N.busveq / 3
FAC = {1: "Arterial", 2: "Freeway", 3: "Ramp to arterial", 4: "Expressway", 5: "Freeway ramp", 6: "Connector", 7: "Toll link", 8: "Metered ramp"}
per = []
for p in range(1, 9):
    rows, on = [], False
    for line in io.TextIOWrapper(zf.open(f"network_p{p}.txt"), errors="ignore"):
        if line.startswith("t links"): on = True; continue
        if on and line.startswith("a"):
            s = line.split(); rows.append((int(s[1]), int(s[2]), float(s[3]), int(s[7]), float(s[8]), float(s[9]), float(s[10])))
    L = pd.DataFrame(rows, columns=["i_node", "j_node", "len", "vdf", "ul1", "ul2", "ul3"])
    A = pd.read_csv(io.TextIOWrapper(zf.open(f"attribs_p{p}.txt")), sep=r"\s+")[["i_node", "j_node", "@vadt", "timau"]]
    d = L.merge(A, on=["i_node", "j_node"]).merge(N[N.timeperiod == p], on=["i_node", "j_node"])
    d["t"] = link_time(d.vdf, d.V, d.ul1, d.ul2, d.ul3, d.len)
    d["period"] = p
    per.append(d)
P = pd.concat(per)
P["VMT"] = P["@vadt"] * P.len            # period @vadt: vehicles without buses
P["VMT_bus"] = P.veh_bus * P.len          # with bus / 3, as CMAP's daily @vadt
P["VHT_cmap"] = P.veh_bus * P.timau / 60
P["VHT_ours"] = P.veh_bus * P.t / 60
# daily published
b = zipfile.ZipFile(os.path.join(C, "highwayshp_c25q4_100.zip")).read("emme_links.dbf")
n = struct.unpack("<I", b[4:8])[0]; hl, rl = struct.unpack("<HH", b[8:12]); f = []; k = 32
while b[k] != 0x0D: f.append((b[k:k + 11].split(b"\0")[0].decode(), b[k + 16])); k += 32
rec = []
for r in range(n):
    x = b[hl + r * rl + 1:hl + (r + 1) * rl]; q = 0; dd = {}
    for name, ln in f:
        if name in ("INODE", "JNODE", "LENGTH", "VDF", "@vadt", "@vht"): dd[name] = x[q:q + ln].decode(errors="ignore").strip()
        q += ln
    rec.append(dd)
Dy = pd.DataFrame(rec).apply(pd.to_numeric, errors="coerce")
Dy["VMT_day"] = Dy["@vadt"] * Dy.LENGTH
rows = []
for v in list(range(1, 9)) + ["all"]:
    pm = P[P.period == 7] if v == "all" else P[(P.period == 7) & (P.vdf == v)]
    dl = P if v == "all" else P[P.vdf == v]
    dy = Dy if v == "all" else Dy[Dy.VDF == v]
    rows.append(dict(vdf=v, facility="All" if v == "all" else FAC[v], links_pm=len(pm),
                     PM_VMT=pm.VMT.sum(), PM_VHT_CMAP=pm.VHT_cmap.sum(), PM_VHT_ours=pm.VHT_ours.sum(),
                     PM_VHT_ratio=pm.VHT_ours.sum() / pm.VHT_cmap.sum(),
                     daily_VMT_CMAP=dy.VMT_day.sum(), daily_VMT_ours_8periods=dl.VMT_bus.sum(),
                     daily_VMT_ratio=dl.VMT_bus.sum() / dy.VMT_day.sum(),
                     daily_VHT_CMAP=dy["@vht"].sum(), daily_VHT_ours_8periods=dl.VHT_ours.sum(),
                     daily_VHT_ratio=dl.VHT_ours.sum() / dy["@vht"].sum(),
                     daily_VHT_CMAP_timau_8periods=dl.VHT_cmap.sum()))
T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "a8_network_by_facility_pm_daily.csv"), index=False)
pd.set_option("display.width", 250)
print(T[["facility", "links_pm", "PM_VHT_ratio", "daily_VMT_ratio", "daily_VHT_ratio"]].round(4).to_string(index=False))
print("check: CMAP daily @vht vs sum of 8 periods with CMAP timau:", round(T.iloc[-1].daily_VHT_CMAP_timau_8periods / T.iloc[-1].daily_VHT_CMAP, 5))
