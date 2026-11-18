"""CMAP OD by period: summary table, checks, Excel and figure.

    python od8_summary.py <shp2gmns_replay_kit> <output folder>

Reads the kit's demand output (main_convert.py --region region.cmap.yaml --demand-only) and the daily truck
matrices in c25q4_100/emmemat_c25q4_100.zip. Writes to the output folder:
  od_by_period.csv          period x class: vehicles, cells, kept share, dropped vehicles
  od_checks.csv             SOV = trip_roster per period; PM2 files = PM files; trucks over 8 periods = daily tables
  od_by_period.xlsx         sheets: README, vehicles, kept_share, dropped, checks
  od_by_period.png          vehicles by class and period
"""
import hashlib, json, sys, zipfile
from pathlib import Path
import numpy as np, pandas as pd, yaml
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

KIT, OUT = Path(sys.argv[1]), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
cfg = yaml.safe_load((KIT / "region.cmap.yaml").read_text(encoding="utf-8"))["demand"]
P = ["EA", "AM1", "AM2", "AM3", "MD", "PM1", "PM2", "PM3"]
HOURS = {"EA": "8pm-6am", "AM1": "6-7am", "AM2": "7-9am", "AM3": "9-10am", "MD": "10am-2pm", "PM1": "2-4pm", "PM2": "4-6pm", "PM3": "6-8pm"}
M = ["sov", "hov2", "hov3", "apv", "btrk", "ltrk", "mtrk", "htrk"]
par = KIT / "data/output/cmap/parameters/demand_by_period"
dem = KIT / "data/output/cmap/demand"

rows = []
for i, p in enumerate(P, 1):
    s = pd.read_csv(par / f"demand_summary_{p}.csv", encoding="utf-8-sig")
    s.insert(0, "period", p); s.insert(1, "cmap_period", i); s.insert(2, "hours", HOURS[p]); rows.append(s)
t = pd.concat(rows, ignore_index=True)
t.to_csv(OUT / "od_by_period.csv", index=False)

chk = []
for p in P:
    c = json.loads((par / f"demand_check_{p}.json").read_text(encoding="utf-8"))
    ok = abs(c["sov_demand_model_total"] - c["expected_sov_demand_model_total"]) < 1
    bad = [k for k, v in c["matrices"].items() if v != 3649 * 3649 * 4]
    chk.append({"check": "SOV mf41y+mf42y+mf43y = trip_roster mode 1", "period": p,
                "value": c["sov_demand_model_total"], "expected": c["expected_sov_demand_model_total"], "pass": ok})
    chk.append({"check": "every matrix 3649 x 3649 float32", "period": p, "value": len(c["matrices"]) - len(bad),
                "expected": len(c["matrices"]), "pass": not bad})
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
for m in M:
    same = sha(dem / "PM" / f"{m}_PM.csv") == sha(dem / "PM2" / f"{m}_PM2.csv")
    chk.append({"check": "PM2 file identical to the earlier PM file", "period": f"PM2 {m}", "value": int(same), "expected": 1, "pass": same})
z = zipfile.ZipFile(KIT / cfg["emmemat_zip"]) if Path(cfg["emmemat_zip"]).is_absolute() else zipfile.ZipFile((KIT / cfg["emmemat_zip"]).resolve())
day = {m: float(np.frombuffer(z.read(f"{m}.emx"), "<f4").astype(np.float64).sum()) for m in ["mf4", "mf5", "mf6", "mf7", "mf9"]}
tot = t.pivot(index="period", columns="mode_type", values="total_vehicles").loc[P]
for cls, src in [("btrk", ["mf4"]), ("ltrk", ["mf5"]), ("mtrk", ["mf6"]), ("htrk", ["mf7", "mf9"])]:
    d = sum(day[s] for s in src); v = float(tot[cls].sum())
    chk.append({"check": f"{cls}: sum over 8 periods = daily {'+'.join(src)} (factors sum to 1)", "period": "all",
                "value": round(v, 1), "expected": round(d, 1), "pass": abs(v / d - 1) < 0.001})
ck = pd.DataFrame(chk); ck.to_csv(OUT / "od_checks.csv", index=False)

veh = t.pivot(index="period", columns="mode_type", values="total_vehicles").loc[P, M]
veh["all"] = veh.sum(1); veh.loc["day"] = veh.sum()
kept = t.pivot(index="period", columns="mode_type", values="vehicles_written").loc[P, M]
kept["all"] = kept.sum(1); kept.loc["day"] = kept.sum()
share = (kept / veh).round(4)
drop = (veh - kept).round(1)
cells = t.pivot(index="period", columns="mode_type", values="cells_written").loc[P, M]
cells["all"] = cells.sum(1); cells.loc["day"] = cells.sum()
size = {p: round(sum(f.stat().st_size for f in (dem / p).glob("*.csv")) / 1e6, 1) for p in P}

readme = pd.DataFrame({"item": [
    "What", "Source", "Rule", "Small cells", "Classes", "Periods", "Not included", "Files", "Made by"], "text": [
    "CMAP c25q4 2019 base (scenario 100): vehicle OD tables for the 8 CMAP periods, 8 classes. OD only (no network, no assignment).",
    "c25q4_100/emmemat_c25q4_100.zip: mf41y-mf45y (period y autos: SOV VOT1-3, HOV2, HOV3+), daily mf4-mf7 (B-plate, light, medium, heavy trucks), mf8 (auto point of entry), mf9 (truck point of entry), mf10 (airport).",
    "As CMAP's ttables.mac builds the period tables: autos as they are; trucks, externals and airport = daily table x period factor (tod_factors.p1-p8 = data user guide TOD table). Vehicles, not vehicle equivalents (medium x2, heavy x3 go in pce).",
    f"OD cells with <= {cfg['min_volume']} vehicles per period are not written and not rescaled (as for the earlier PM files). Sheets kept_share and dropped show what this removes.",
    "sov = SOV VOT1-3 + auto point of entry; hov2; hov3 = HOV3+; apv = airport (CMAP adds it to SOV); btrk = B-plate; ltrk = light; mtrk = medium; htrk = heavy + truck point of entry.",
    "EA 8pm-6am, AM1 6-7am, AM2 7-9am, AM3 9-10am, MD 10am-2pm, PM1 2-4pm, PM2 4-6pm, PM3 6-8pm (CMAP periods 1-8).",
    "Park-and-ride first legs (mf59, built inside CMAP's run), bus preload (link, not OD), taxi and TNC (trip_roster modes 4-6).",
    "shp2gmns_replay_kit/data/output/cmap/demand/<period>/<class>_<period>.csv (o_zone_id, d_zone_id, volume = vehicles in the period); " + ", ".join(f"{p} {size[p]} MB" for p in P),
    "shp2gmns_replay_kit: python code/main_convert.py --region region.cmap.yaml --demand-only; this table: od8_summary.py"]})

with pd.ExcelWriter(OUT / "od_by_period.xlsx", engine="openpyxl") as x:
    readme.to_excel(x, "README", index=False)
    veh.round(1).to_excel(x, "vehicles")
    share.to_excel(x, "kept_share")
    drop.to_excel(x, "dropped")
    cells.to_excel(x, "cells_written")
    ck.to_excel(x, "checks", index=False)
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = load_workbook(OUT / "od_by_period.xlsx")
for ws in wb:
    for row in ws.iter_rows():
        for c in row:
            c.font = Font(name="Arial", bold=(c.row == 1 or (c.column == 1 and ws.title != "README")))
            if c.row == 1: c.fill = PatternFill("solid", fgColor="DDEBF7")
    ws.column_dimensions["A"].width = 14 if ws.title != "checks" else 60
    for col in "BCDEFGHIJ": ws.column_dimensions[col].width = 13
    if ws.title == "README":
        ws.column_dimensions["B"].width = 140
        for c in ws["B"]: c.alignment = Alignment(wrap_text=True, vertical="top")
    if ws.title == "vehicles" or ws.title == "dropped":
        for row in ws.iter_rows(min_row=2, min_col=2):
            for c in row: c.number_format = "#,##0"
    if ws.title == "kept_share":
        for row in ws.iter_rows(min_row=2, min_col=2):
            for c in row:
                c.number_format = "0.0%"
                if isinstance(c.value, float) and c.value < 0.95: c.fill = PatternFill("solid", fgColor="FCE4D6")
    if ws.title == "cells_written":
        for row in ws.iter_rows(min_row=2, min_col=2):
            for c in row: c.number_format = "#,##0"
    if ws.title == "checks":
        ws.column_dimensions["B"].width = 12
        for row in ws.iter_rows(min_row=2):
            if row[4].value is False: row[4].fill = PatternFill("solid", fgColor="FFC7CE")
wb.save(OUT / "od_by_period.xlsx")

# figure: vehicles by class and period (millions), stacked
fig, ax = plt.subplots(figsize=(9, 4.6))
col = {"sov": "#2E6DB4", "hov2": "#6FA8DC", "hov3": "#B4D3EE", "apv": "#9E9E9E", "btrk": "#E69F00", "ltrk": "#F2C46D", "mtrk": "#C0504D", "htrk": "#7B2C2A"}
bottom = np.zeros(len(P)); v = veh.loc[P, M] / 1e6
for m in M:
    ax.bar(P, v[m], bottom=bottom, color=col[m], label=m, edgecolor="white", linewidth=0.6); bottom += v[m].values
for i, p in enumerate(P):
    ax.text(i, bottom[i] + 0.05, f"{bottom[i]:.2f}", ha="center", fontsize=9)
ax.set_xticks(range(len(P))); ax.set_xticklabels([f"{p}\n{HOURS[p]}" for p in P], fontsize=9)
ax.set_ylabel("vehicles in the period (million)"); ax.spines[["top", "right"]].set_visible(False)
ax.set_title(f"CMAP c25q4 2019: vehicle OD by period and class (day {veh.loc['day','all']/1e6:.2f} M vehicles)", fontsize=11)
ax.legend(ncol=8, fontsize=8.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17))
ax.grid(axis="y", color="#e5e5e5"); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig(OUT / "od_by_period.png", dpi=200)
print(veh.round(0).to_string()); print(share.to_string()); print(ck.to_string())
