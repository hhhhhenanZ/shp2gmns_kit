"""Run history of the TAPLite PM assignment against CMAP (network VMT and VHT ratios), for the PM-check deck.
Sources: BPR run (Nov 6): ../CMAP_progress_report.tex, section 5 (VMT 0.925, VHT 0.710, all links).
R1, R2: task_C3_taplite_allmodes/outputs/R1_by_vdf.csv, R2_by_vdf.csv (row "all").
R3, R4: A5_arterial_gap/outputs/a5_r4_by_vdf.csv (rows R3, R4, vdf "all"); copied to tables/taplite_run_history.csv.
Usage: python fig_run_history.py   (reads tables/taplite_run_history.csv, writes figs/fig7_taplite_run_history.png/pdf)"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = pd.read_csv(os.path.join(HERE, "tables", "taplite_run_history.csv"))
INK, MUTED = "#1f2328", "#57606a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False})
fig, ax = plt.subplots(figsize=(10, 4.4))
x = range(len(H))
ax.axhspan(.95, 1.05, color="#eef3fb", zorder=0); ax.axhline(1, color=MUTED, lw=1)
ax.plot(x, H.VMT_ratio, "-o", color="#1f5fbf", lw=2, label="VMT")
ax.plot(x, H.VHT_ratio, "-o", color="#d9822b", lw=2, label="VHT")
for xi, (a, b) in enumerate(zip(H.VMT_ratio, H.VHT_ratio)):
    ax.text(xi, a + .012, f"{a:.3f}", ha="center", color="#1f5fbf", fontsize=9)
    ax.text(xi, b - .03, f"{b:.3f}", ha="center", color="#d9822b", fontsize=9)
ax.set_xticks(list(x)); ax.set_xticklabels([f"{r}\n{c}" for r, c in zip(H.run, H.change)], fontsize=9)
ax.set_ylim(.65, 1.07); ax.set_ylabel("TAPLite / CMAP, all links")
ax.set_title("TAPLite PM runs against CMAP: network VMT and VHT", fontweight="bold")
ax.legend(loc="lower right")
fig.tight_layout()
for e in ("png", "pdf"):
    fig.savefig(os.path.join(HERE, "figs", f"fig7_taplite_run_history.{e}"), dpi=200)
