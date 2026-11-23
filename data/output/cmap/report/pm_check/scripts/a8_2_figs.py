"""A8 step 2: figures (PNG 200 dpi + PDF) for the summary and the slides, from the step-1 outputs."""
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O, F = os.path.join(HERE, "outputs"), os.path.join(HERE, "figs")
INK, MUTED, GRID = "#1f2328", "#57606a", "#d0d7de"
REAL, METB, VMTC, VHTC = "#1f5fbf", "#a0a7b0", "#1f5fbf", "#d9822b"
SEC = {"Dan Ryan": "#f2f4f7", "Circle": "#e6ebf2", "Kennedy": "#f2f4f7"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 12, "axes.titleweight": "bold", "legend.frameon": False})

def save(fig, name):
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(F, f"{name}.{ext}"), dpi=200)
    plt.close(fig)

def band(ax, lo=.95, hi=1.05, horizontal=True):
    if horizontal:
        ax.axhspan(lo, hi, color="#eef3fb", zorder=0); ax.axhline(1, color=MUTED, lw=1, zorder=1)
    else:
        ax.axvspan(lo, hi, color="#eef3fb", zorder=0); ax.axvline(1, color=MUTED, lw=1, zorder=1)

# ---------------------------------------------------------------- Fig 1: CMAP self-check, VHT ratio and time within 1 % by facility
p1 = pd.read_csv(os.path.join(O, "a8_part1_cmap_selfcheck_by_facility.csv"))
order = ["Freeway", "Expressway", "Arterial", "Ramp to arterial", "Freeway ramp", "Metered ramp", "All"]
s = p1.set_index("facility").reindex(order)
labels = [o.replace(" to ", "\nto ").replace("way ramp", "way\nramp").replace("Metered ramp", "Metered\nramp") for o in order]
fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
ax = axs[0]
ax.bar(range(len(order)), s.VHT_ratio, .6, color=REAL, zorder=2)
for xi, v in enumerate(s.VHT_ratio):
    ax.text(xi, v + .002, f"{v:.3f}", ha="center", va="bottom", fontsize=9, color=INK)
band(ax); ax.set_ylim(.94, 1.06); ax.set_xticks(range(len(order))); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("VHT: ours / CMAP"); ax.set_title("VHT against CMAP")
ax = axs[1]
ax.bar(range(len(order)), s.time_within_1pct * 100, .6, color=REAL, zorder=2)
for xi, v in enumerate(s.time_within_1pct * 100):
    ax.text(xi, v + .5, f"{v:.1f}", ha="center", va="bottom", fontsize=9, color=INK)
ax.set_ylim(80, 102); ax.set_xticks(range(len(order))); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("% of links"); ax.set_title("Link time within 1 % of CMAP's timau")
fig.suptitle("CMAP self-check, PM: CMAP's class volumes through CMAP's link-time functions", fontweight="bold")
save(fig, "a8_fig1_cmap_selfcheck_by_facility")

# ---------------------------------------------------------------- Fig 2: time ratio against V/ul2, freeways and arterials
full1 = pd.read_csv(os.path.join(O, "a8_part1_links_pm.csv.gz"))
fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
for ax, v, lab in [(axs[0], 2, "Freeways (vdf 2)"), (axs[1], 1, "Arterials (vdf 1)")]:
    g = full1[(full1.vdf == v) & (full1.ul2 > 1)]
    band(ax)
    ax.scatter(g.x_real, g.ratio_real, s=6, color=REAL, alpha=.45, lw=0, zorder=2)
    w1 = (g.ratio_real.sub(1).abs() <= .01).mean(); w5 = (g.ratio_real.sub(1).abs() <= .05).mean()
    ax.set_title(f"{lab}\n{w1:.1%} within 1 %, {w5:.1%} within 5 %")
    ax.set_xlabel("V / ul2 (CMAP volume over CMAP period capacity)")
    ax.set_xlim(0, min(2.5, float(g.x_real.quantile(.999)) * 1.05))
axs[0].set_ylabel("Link time: ours / CMAP timau"); axs[0].set_ylim(.8, 1.2)
save(fig, "a8_fig2_selfcheck_time_ratio_vs_vc")

# ---------------------------------------------------------------- Fig 3: corridor, CMAP time and our time
cl = pd.read_csv(os.path.join(O, "a8_part1_corridor_links.csv")).sort_values("road_order").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(11, 4.2))
xs = np.arange(len(cl))
for sec, g in cl.groupby("section", sort=False):
    ax.axvspan(g.index.min() - .5, g.index.max() + .5, color=SEC.get(sec, "#f2f4f7"), zorder=0)
ax.plot(xs, cl.timau / cl.length_mi, "-", color=INK, lw=2.5, label="CMAP timau", zorder=2)
ax.plot(xs, cl.t_real / cl.length_mi, "o", color=REAL, ms=4, label="Ours (CMAP functions, CMAP volumes)", zorder=3)
top = float((cl.timau / cl.length_mi).max()) * 1.12
for sec, g in cl.groupby("section", sort=False):
    ax.text((g.index.min() + g.index.max()) / 2, top * .97, sec, ha="center", color=MUTED, fontsize=10)
ax.set_xlim(-.5, len(cl) - .5); ax.set_ylim(0, top)
ax.set_xlabel("CMAP link, in road order (I-90/94 WB, 55 links)"); ax.set_ylabel("PM link time (min per mile)")
ax.set_title(f"I-90/94 WB, PM: link time per mile; largest difference {cl.ratio_real.sub(1).abs().max():.2%}")
ax.legend(loc="upper center", bbox_to_anchor=(.5, -.18), ncol=2)
save(fig, "a8_fig3_corridor_time")

# ---------------------------------------------------------------- Fig 4: TAPLite vs CMAP link volume by class
p2 = pd.read_csv(os.path.join(O, "a8_part2_taplite_class_volume_by_facility.csv"))
pairs = [("All vehicles", "veh"), ("Auto (SOV+HOV)", "auto"), ("B-plate truck", "B"), ("Light truck", "L"), ("Medium truck", "M"), ("Heavy truck", "H")]
full = pd.read_csv(os.path.join(O, "a8_links_pm.csv.gz"))
full["cm_veh"] = full.vadt
fig, axs = plt.subplots(2, 3, figsize=(12, 7.4))
for ax, (lab, k) in zip(axs.flat, pairs):
    c = full["cm_" + k]; m = full["tap_" + k]
    keep = (c > 0) | (m > 0)
    ax.scatter(c[keep], m[keep], s=3, color=REAL, alpha=.25, lw=0)
    hi = float(np.nanpercentile(np.r_[c[keep], m[keep]], 99.9)) * 1.05
    ax.plot([0, hi], [0, hi], color=INK, lw=1)
    ax.set_xlim(0, hi); ax.set_ylim(0, hi)
    s = p2[(p2.facility == "All") & (p2.vehicle_class == lab)].iloc[0]
    ax.set_title(lab)
    ax.text(.04, .96, f"R² {s.link_volume_R2:.3f}\nVMT ratio {s.VMT_ratio:.3f}\nGEH<5 {s.share_GEH_lt_5:.1%}",
            transform=ax.transAxes, va="top", fontsize=9.5, color=INK)
    ax.set_xlabel("CMAP PM volume (veh)"); ax.set_ylabel("TAPLite PM volume (veh)")
fig.suptitle("TAPLite (CMAP functions, R4) against CMAP's own PM assignment: link volume by vehicle class (55,005 links)", fontweight="bold")
save(fig, "a8_fig4_taplite_volume_by_class")

# ---------------------------------------------------------------- Fig 5: TAPLite VMT and VHT ratio by facility
p2b = pd.read_csv(os.path.join(O, "a8_part2_taplite_vmt_vht_by_facility.csv"))
order = ["Freeway", "Expressway", "Arterial", "Ramps (3, 5, 8)", "Toll link", "Connector", "All"]
s = p2b.set_index("facility").reindex(order)
fig, ax = plt.subplots(figsize=(10, 4.6))
x = np.arange(len(order)); w = .38
for k, (col, lab, c) in enumerate([("VMT_ratio", "VMT", VMTC), ("VHT_ratio", "VHT", VHTC)]):
    ax.bar(x + (k - .5) * w, s[col], w * .92, color=c, label=lab, zorder=2)
    for xi, v in zip(x + (k - .5) * w, s[col]):
        ax.text(xi, v + .003, f"{v:.3f}", ha="center", va="bottom", fontsize=9, color=INK)
band(ax)
ax.set_xticks(x); ax.set_xticklabels(order); ax.set_ylim(.9, 1.12)
ax.set_ylabel("TAPLite / CMAP")
ax.set_title("TAPLite PM assignment (R4) against CMAP: VMT and VHT by facility")
ax.legend(loc="upper left", ncol=2)
save(fig, "a8_fig5_taplite_vmt_vht_by_facility")

# ---------------------------------------------------------------- Fig 6: class x facility VMT ratio
fac = ["Freeway", "Expressway", "Arterial", "Ramps (3, 5, 8)", "All"]
cls = [p[0] for p in pairs]
Mx = p2.pivot(index="vehicle_class", columns="facility", values="VMT_ratio").reindex(index=cls, columns=fac)
fig, ax = plt.subplots(figsize=(9, 4.6))
im = ax.imshow(Mx.values, cmap="RdBu_r", vmin=.8, vmax=1.2, aspect="auto")
for r in range(Mx.shape[0]):
    for c in range(Mx.shape[1]):
        v = Mx.values[r, c]
        ax.text(c, r, f"{v:.3f}", ha="center", va="center", fontsize=10, color="white" if abs(v - 1) > .13 else INK)
ax.set_xticks(range(len(fac))); ax.set_xticklabels(fac); ax.set_yticks(range(len(cls))); ax.set_yticklabels(cls)
ax.spines[:].set_visible(False)
cb = fig.colorbar(im, ax=ax, fraction=.04); cb.set_label("VMT: TAPLite / CMAP")
ax.set_title("TAPLite PM assignment (R4): VMT ratio by vehicle class and facility")
save(fig, "a8_fig6_taplite_class_vmt_ratio")
print("figures written")
