"""Charts for the replay analysis.

One PNG per question. Each figure is meant to be read on its own: the title states
what is plotted, and the numbers that answer the question are printed inside the axes
rather than left in a CSV the reader has to open separately.

Written for the AM 20-iteration run. The convergence chart uses every run.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display on this machine; write files only

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .config import (  # noqa: E402
    FTYPE_LABEL, CONIC_ALPHA, CONIC_ALPHA_BY_FT_AT, spiess_beta,
)
from .item4_vdf import conical_curvature  # noqa: E402
from .vdf_math import conical_vdf  # noqa: E402

DPI = 130
CUBE_COLOR = "#1f77b4"
TAP_COLOR = "#d62728"
GREY = "#888888"


def _save(figure, out_dir: Path, name: str) -> Path:
    path = Path(out_dir) / name
    figure.tight_layout()
    figure.savefig(path, dpi=DPI)
    plt.close(figure)
    print(f"    {name}")
    return path


def fig_conical_shape(out_dir: Path) -> Path:
    """The conical function per facility type, and how alpha moves with area type.

    Left: one curve per facility type at its pooled alpha, with a band spanning the
    six area-type values. The band is invisible for most facility types, which is the
    finding -- area type moves alpha very little.

    Right: the alpha table itself, so the 36 cells behind the band are legible.
    """
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    x = np.linspace(0, 1.6, 400)
    colors = plt.cm.viridis(np.linspace(0.05, 0.85, len(CONIC_ALPHA)))

    for index, (ftype, pooled) in enumerate(sorted(CONIC_ALPHA.items())):
        cells = CONIC_ALPHA_BY_FT_AT.get(ftype, {})
        values = sorted(cells.values()) or [pooled]
        low = conical_vdf(min(values), x, spiess_beta(min(values)))
        high = conical_vdf(max(values), x, spiess_beta(max(values)))
        axes[0].fill_between(x, low, high, color=colors[index], alpha=0.35, linewidth=0)
        axes[0].plot(x, conical_vdf(pooled, x, spiess_beta(pooled)), color=colors[index],
                     linewidth=1.6,
                     label=f"FT {ftype} {FTYPE_LABEL[ftype]}   "
                           f"vdf_alpha {min(values):g}-{max(values):g}")

    axes[0].axvline(1.0, color=GREY, linestyle=":", linewidth=1)
    axes[0].axhline(1.0, color=GREY, linestyle=":", linewidth=1)
    axes[0].set_xlabel("volume / capacity  (V/C)")
    axes[0].set_ylabel("travel time / free-flow time")
    axes[0].set_title("Conical function per facility type\n"
                      "t/t0 = 2 + sqrt(alpha^2 (1-x)^2 + beta^2) - alpha (1-x) - beta\n"
                      "band spans the six area-type values")
    axes[0].legend(fontsize=7.5, loc="upper left")
    axes[0].grid(alpha=0.3)

    area_types = sorted({at for cells in CONIC_ALPHA_BY_FT_AT.values() for at in cells})
    positions = np.arange(len(area_types))
    width = 0.13
    for index, (ftype, cells) in enumerate(sorted(CONIC_ALPHA_BY_FT_AT.items())):
        heights = [cells.get(at, np.nan) for at in area_types]
        offset = (index - (len(CONIC_ALPHA_BY_FT_AT) - 1) / 2) * width
        bars = axes[1].bar(positions + offset, heights, width, color=colors[index],
                           label=f"FT {ftype}")
        for bar, height in zip(bars, heights):
            if np.isfinite(height):
                axes[1].text(bar.get_x() + bar.get_width() / 2, height + 0.35,
                             f"{height:g}", ha="center", fontsize=6.2, rotation=90)
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels([f"AT {at}" for at in area_types])
    axes[1].set_ylabel("vdf_alpha")
    axes[1].set_ylim(0, 19.5)
    axes[1].set_title("Fitted vdf_alpha for each facility x area-type cell\n"
                      "36 cells, fitted independently from Cube's own output")
    axes[1].legend(fontsize=7.5, ncol=3, loc="upper left")
    axes[1].grid(alpha=0.3, axis="y")
    return _save(figure, out_dir, "fig1_conical_function.png")


def fig_kernel_check(three_way, out_dir: Path) -> Path:
    """Verification that TAPlite evaluates the specified conical function.

    Compares the travel time ratio t / t0 the kernel reported against the same
    quantity computed independently at the kernel's own volumes.
    """
    frame = three_way[~three_way["is_connector"]]
    x = frame["indep_at_taplite_v_vdf_ratio"].to_numpy(dtype=float)
    y = frame["taplite_vdf_ratio"].to_numpy(dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    error = np.abs(y - x)
    within = (error <= 0.01).mean()

    # Axes are clipped to 1-15 so the body of the data fills the panel. A small
    # number of heavily congested links sit beyond 15; they are counted in the
    # legend rather than shown, and the error histogram beside this panel covers
    # every link regardless.
    view = 15.0
    shown = (x <= view) & (y <= view)
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].plot([0, view], [0, view], color=GREY, linewidth=1.2,
                 label="line of equality")
    axes[0].scatter(x[shown], y[shown], s=2, alpha=0.12, color=TAP_COLOR,
                    edgecolors="none",
                    label=f"{shown.sum():,} links shown "
                          f"({(~shown).sum():,} beyond the axis)")
    axes[0].set_xlim(0, view)
    axes[0].set_ylim(0, view)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlabel("independent calculation,  t / t0")
    axes[0].set_ylabel("TAPlite,  travel_time / vdf_fftt")
    axes[0].set_title("Travel time ratio: TAPlite against\nindependent calculation, "
                      "at identical volumes")
    axes[0].legend(fontsize=8, loc="upper left")
    axes[0].grid(alpha=0.3)

    axes[1].hist(np.log10(np.maximum(error, 1e-12)), bins=70, color=TAP_COLOR)
    for threshold, style in ((0.01, "--"), (0.001, ":")):
        axes[1].axvline(np.log10(threshold), color=GREY, linestyle=style, linewidth=1.2,
                        label=f"absolute error = {threshold}")
    axes[1].set_xlabel("absolute error  (log10 scale)")
    axes[1].set_ylabel("number of links")
    axes[1].set_title("Distribution of absolute error\n"
                      f"median {np.median(error):.1e}  ·  {within:.2%} within 0.01  ·  "
                      f"maximum {error.max():.3f}")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    return _save(figure, out_dir, "fig2_kernel_check.png")


def fig_network_speed(network_speed, out_dir: Path, run_label: str) -> Path:
    """Network speed, total VMT / total VHT, Cube against TAPlite."""
    table = network_speed[network_speed["run"] == run_label]
    scopes = ["all_links", "road_links_only", "freeway_only", "connectors_only"]
    labels = ["All links", "Road links", "Freeway", "Connectors"]

    cube, tap = [], []
    for scope in scopes:
        rows = table[table["scope"] == scope]
        cube.append(float(rows[rows["source"] == "cube"]
                          ["network_speed_mph_CORRECT_vmt_over_vht"].iloc[0]))
        tap.append(float(rows[rows["source"] == "taplite"]
                         ["network_speed_mph_CORRECT_vmt_over_vht"].iloc[0]))

    figure, axis = plt.subplots(figsize=(7.2, 4.6))
    positions = np.arange(len(scopes))
    width = 0.38
    axis.bar(positions - width / 2, cube, width, label="Cube", color=CUBE_COLOR)
    axis.bar(positions + width / 2, tap, width, label="TAPlite (20 iterations)",
             color=TAP_COLOR)
    for index, (a, b) in enumerate(zip(cube, tap)):
        axis.text(index - width / 2, a + 0.6, f"{a:.1f}", ha="center", fontsize=9)
        axis.text(index + width / 2, b + 0.6, f"{b:.1f}", ha="center", fontsize=9)
    axis.set_xticks(positions)
    axis.set_xticklabels(labels)
    axis.set_ylabel("speed (mph)")
    axis.set_ylim(0, max(cube + tap) * 1.18)
    axis.set_title("Network speed = total VMT / total VHT\n"
                   f"all links: Cube {cube[0]:.2f} mph, TAPlite {tap[0]:.2f} mph "
                   f"({(tap[0] / cube[0] - 1) * 100:+.2f}%)")
    axis.legend(fontsize=9)
    axis.grid(alpha=0.3, axis="y")
    return _save(figure, out_dir, "fig3_network_speed.png")


def fig_vmt_by_facility(rollup, out_dir: Path, run_label: str) -> Path:
    """VMT and VHT by facility type, Cube against TAPlite."""
    table = rollup[(rollup["run"] == run_label)
                   & (rollup["dimension"] == "facility_type")
                   & (~rollup["category"].str.startswith("TOTAL"))]
    table = table.sort_values("cube_VMT", ascending=True)
    positions = np.arange(len(table))
    height = 0.38

    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for axis, measure, unit in ((axes[0], "VMT", "million vehicle-miles"),
                                (axes[1], "VHT", "thousand vehicle-hours")):
        scale = 1e6 if measure == "VMT" else 1e3
        axis.barh(positions - height / 2, table[f"cube_{measure}"] / scale, height,
                  label="Cube", color=CUBE_COLOR)
        axis.barh(positions + height / 2, table[f"taplite_{measure}"] / scale, height,
                  label="TAPlite", color=TAP_COLOR)
        axis.set_yticks(positions)
        axis.set_yticklabels(table["category"], fontsize=9)
        axis.set_xlabel(unit)
        axis.set_title(f"{measure} by facility type")
        axis.legend(fontsize=9)
        axis.grid(alpha=0.3, axis="x")
    return _save(figure, out_dir, "fig4_vmt_by_facility.png")


def fig_convergence(convergence, out_dir: Path) -> Path:
    """Relative gap by iteration."""
    logged = convergence[convergence["iteration"].notna()]
    if logged.empty:
        # A one-iteration run logs no gap: a relative gap needs a previous solution.
        # With nothing to plot, skip the chart instead of failing the whole analysis.
        print("    fig5_convergence.png skipped: no run logged a relative gap "
              "(one-iteration runs do not)")
        return None
    figure, axis = plt.subplots(figsize=(7.2, 4.4))

    for run, group in logged.groupby("run"):
        axis.semilogy(group["iteration"], group["relative_gap_pct"], "o-",
                      color=TAP_COLOR, markersize=4, label=run)
        final = group["relative_gap_pct"].iloc[-1]
        first = group["relative_gap_pct"].iloc[0]
    axis.set_xlabel("iteration")
    axis.set_ylabel("relative gap (%, log scale)")
    axis.set_title("Convergence of the Frank-Wolfe assignment\n"
                   f"gap falls from {first:.0f}% to {final:.2f}%; "
                   "no gap threshold is applied")
    axis.legend(fontsize=9)
    axis.grid(alpha=0.3, which="both")
    return _save(figure, out_dir, "fig5_convergence.png")


def fig_corridors(corridors, out_dir: Path, run_label: str) -> Path:
    """Corridor speeds, Cube against TAPlite."""
    table = corridors[corridors["run"] == run_label].copy()
    table = table.sort_values("cube_speed_mph")
    positions = np.arange(len(table))
    height = 0.38

    figure, axes = plt.subplots(1, 2, figsize=(13, 5.6),
                                gridspec_kw={"width_ratios": [1.5, 1]})
    axes[0].barh(positions - height / 2, table["cube_speed_mph"], height,
                 label="Cube", color=CUBE_COLOR)
    axes[0].barh(positions + height / 2, table["taplite_speed_mph"], height,
                 label="TAPlite", color=TAP_COLOR)
    axes[0].set_yticks(positions)
    axes[0].set_yticklabels(table["corridor"], fontsize=9)
    axes[0].set_xlabel("speed (mph) = corridor VMT / corridor VHT")
    axes[0].set_title("Corridor speeds, AM peak")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=0.3, axis="x")

    difference = table["taplite_minus_cube_speed_mph"]
    colors = [TAP_COLOR if value < 0 else CUBE_COLOR for value in difference]
    axes[1].barh(positions, difference, 0.6, color=colors)
    axes[1].axvline(0, color="black", linewidth=1)
    axes[1].set_yticks(positions)
    axes[1].set_yticklabels([])
    axes[1].set_xlabel("TAPlite minus Cube (mph)")
    axes[1].set_title(f"Difference\nlargest {difference.abs().max():.2f} mph")
    axes[1].grid(alpha=0.3, axis="x")
    return _save(figure, out_dir, "fig6_corridors.png")


def make_all(tables: dict, out_dir: Path, run_label: str = "iter20") -> list:
    """Write every figure. ``tables`` holds the concatenated analysis outputs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    three_way = tables["three_way"]
    three_way = three_way[three_way["run"] == run_label]

    written.append(fig_conical_shape(out_dir))
    written.append(fig_kernel_check(three_way, out_dir))
    if "network_speed" in tables:
        written.append(fig_network_speed(tables["network_speed"], out_dir, run_label))
        written.append(fig_vmt_by_facility(tables["rollup"], out_dir, run_label))
    if "convergence" in tables:
        written.append(fig_convergence(tables["convergence"], out_dir))
        written.append(fig_corridors(tables["corridors"], out_dir, run_label))
    return [path for path in written if path is not None]
