"""Maps for the PM-check deck (period 7, 4-6 pm). No basemap; link shapes from the kit's GMNS conversion.
Inputs (kit-relative): data/output/cmap/network/link_geometry.csv, data/output/cmap/network/PM/link.csv (vdf_fftt = CMAP ul1),
pm_check/tables/link_level/a8_links_pm.csv.gz (CMAP and TAPLite volumes and times, not public),
pm_check/tables/link_level/a8_part1_corridor_links.csv (I-90/94 WB links).
Connectors (vdf 6) are not drawn. Two directions of a link are merged: volumes summed (two-way), time ratio = worse direction.
Usage (from pm_check/): python scripts/make_maps.py
"""
import os, re
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize, TwoSlopeNorm, LogNorm

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET = os.path.abspath(os.path.join(HERE, "..", "..", "network"))
F = os.path.join(HERE, "figs")
INK, MUTED = "#1f2328", "#57606a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
CITY = (-87.95, -87.52, 41.64, 42.03)          # lon_min, lon_max, lat_min, lat_max (City of Chicago and edge)

G = pd.read_csv(os.path.join(NET, "link_geometry.csv"), encoding="utf-8-sig")[["org_link_id", "geometry"]]
G["xy"] = [np.array([[float(a), float(b)] for a, b in re.findall(r"(-?\d+\.\d+) (-?\d+\.\d+)", g)]) for g in G.geometry]
L = pd.read_csv(os.path.join(NET, "PM", "link.csv"), encoding="utf-8-sig", usecols=["org_link_id", "from_node_id", "to_node_id", "vdf_code", "vdf_fftt", "lanes"])
A = pd.read_csv(os.path.join(HERE, "tables", "link_level", "a8_links_pm.csv.gz")).rename(columns={"cmap_id": "org_link_id"})
D = L.merge(A, on="org_link_id").merge(G[["org_link_id", "xy"]], on="org_link_id")
D = D[D.vdf_code != 6].copy()
D["tr_cmap"] = D.timau / D.vdf_fftt.replace(0, np.nan)
D["miss"] = (D.t_real / D.timau.replace(0, np.nan) - 1).abs() > .01
D["key"] = [tuple(sorted(p)) for p in zip(D.from_node_id, D.to_node_id)]
P = D.groupby("key").agg(xy=("xy", "first"), vdf=("vdf_code", "first"), cm=("vadt", "sum"), tap=("tap_veh", "sum"),
                         tr=("tr_cmap", "max"), miss=("miss", "max")).reset_index()
P["diff"] = P.tap - P.cm
cor = set(pd.read_csv(os.path.join(HERE, "tables", "link_level", "a8_part1_corridor_links.csv")).cmap_id)
C = D[D.org_link_id.isin(cor)]
asp = 1 / np.cos(np.radians(41.85))

def base(ax, box=None):
    ax.set_aspect(asp); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)
    if box: ax.set_xlim(box[0], box[1]); ax.set_ylim(box[2], box[3])

def draw(ax, df, colors, widths, z=2):
    ax.add_collection(LineCollection(list(df.xy), colors=colors, linewidths=widths, zorder=z, capstyle="round"))

def save(fig, name):
    fig.tight_layout()
    for e in ("png", "pdf"):
        fig.savefig(os.path.join(F, f"{name}.{e}"), dpi=200)
    plt.close(fig)

FAC = {1: ("Arterial", "#9aa5b1", .35), 3: ("Ramps", "#c08a3e", .5), 5: ("Ramps", "#c08a3e", .5), 8: ("Ramps", "#c08a3e", .5),
       4: ("Expressway", "#2b8a3e", 1.0), 2: ("Freeway", "#1f5fbf", 1.2), 7: ("Toll link", "#b02a37", 1.6)}

# ---------------------------------------------------------------- map 1: network by facility, region and city
fig, axs = plt.subplots(1, 2, figsize=(12, 6.2), gridspec_kw={"width_ratios": [1, 1.15]})
for ax, box, sc in [(axs[0], None, .6), (axs[1], CITY, 1.0)]:
    for v in [1, 3, 5, 8, 4, 2, 7]:
        g = P[P.vdf == v]; lab, col, w = FAC[v]
        draw(ax, g, col, w * sc, z=2 + (v in (2, 4, 7)))
    base(ax, box)
    if box is None:
        allxy = np.vstack(P.xy.values); ax.set_xlim(allxy[:, 0].min(), allxy[:, 0].max()); ax.set_ylim(allxy[:, 1].min(), allxy[:, 1].max())
        ax.add_patch(plt.Rectangle((CITY[0], CITY[2]), CITY[1] - CITY[0], CITY[3] - CITY[2], fill=False, ec=INK, lw=1, zorder=5))
draw(axs[1], C, "#f59f00", 3.0, z=6)
from matplotlib.lines import Line2D
h = [Line2D([], [], color=c, lw=2, label=l) for l, c in [("Freeway", "#1f5fbf"), ("Expressway", "#2b8a3e"), ("Arterial", "#9aa5b1"), ("Ramps", "#c08a3e"), ("Toll link", "#b02a37"), ("I-90/94 WB corridor", "#f59f00")]]
axs[1].legend(handles=h, loc="lower left", frameon=True, fontsize=9)
axs[0].set_title("CMAP region: 55,005 links (connectors not drawn)", fontsize=11)
axs[1].set_title("City of Chicago and edge (box at left)", fontsize=11)
save(fig, "map1_network_facility")

# ---------------------------------------------------------------- map 2: CMAP PM volume and congestion, city
Q = P[(P.vdf != 7)]
fig, axs = plt.subplots(1, 2, figsize=(12, 6.4))
ax = axs[0]; base(ax, CITY)
q = Q.sort_values("cm"); norm = LogNorm(vmin=200, vmax=30000)
cmap = plt.get_cmap("viridis_r")
draw(ax, q, cmap(norm(q.cm.clip(200, 30000))), .3 + 2.2 * (q.cm.clip(0, 30000) / 30000))
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); cb = fig.colorbar(sm, ax=ax, fraction=.035, pad=.01); cb.set_label("Two-way PM volume (veh, 2 h)")
ax.set_title("CMAP PM volume (both directions)", fontsize=11)
ax = axs[1]; base(ax, CITY)
q = Q.sort_values("tr"); norm = Normalize(1, 4); cmap = plt.get_cmap("YlOrRd")
draw(ax, q, cmap(norm(q.tr.clip(1, 4).fillna(1))), np.where(q.vdf.isin([2, 4]), 1.6, .5))
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); cb = fig.colorbar(sm, ax=ax, fraction=.035, pad=.01); cb.set_label("PM link time / free-flow time")
ax.set_title("CMAP PM congestion", fontsize=11)
save(fig, "map2_cmap_pm_volume_congestion")

# ---------------------------------------------------------------- map 3: TAPLite - CMAP volume, city
fig, ax = plt.subplots(figsize=(8.2, 6.6)); base(ax, CITY)
q = Q.assign(a=Q["diff"].abs()).sort_values("a"); lim = 2000
norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim); cmap = plt.get_cmap("RdBu_r")
draw(ax, q, cmap(norm(q["diff"].clip(-lim, lim))), .3 + 2.0 * (q.a.clip(0, lim) / lim))
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); cb = fig.colorbar(sm, ax=ax, fraction=.035, pad=.01)
cb.set_label("TAPLite - CMAP, two-way PM volume (veh, 2 h)")
ax.set_title("TAPLite (R4) against CMAP: where volume differs (red: TAPLite higher)", fontsize=11)
save(fig, "map3_taplite_minus_cmap_volume")

# ---------------------------------------------------------------- map 4: self-check, links over 1 %
fig, ax = plt.subplots(figsize=(8.2, 6.6)); base(ax, CITY)
draw(ax, Q, "#d0d7de", .35)
m = Q[Q.miss]
draw(ax, m, "#c2410c", 1.4, z=4)
ax.set_title("CMAP self-check: links where our time differs from timau by more than 1 %", fontsize=11)
ax.legend(handles=[Line2D([], [], color="#c2410c", lw=2, label=f"> 1 % ({int(D.miss.sum()):,} directed links, region)")], loc="lower left", frameon=True)
save(fig, "map4_selfcheck_misses")
print("maps written; pairs", len(P), "misses", int(D.miss.sum()))
