# CMAP PM check (period 7, 4-6 pm)

CMAP trip-based model, scenario c25q4_100 (2019). Two checks against CMAP's own PM results:

1. **CMAP self-check.** CMAP's PM link volumes by vehicle class go through CMAP's link-time functions (fd1-fd8) with CMAP's free-flow time ul1 and period capacity ul2; the link time is compared with CMAP's final link time `timau`. Network VHT 0.996 of CMAP; 98.9 % of links within 5 %.
2. **TAPLite.** TAPLite with CMAP's functions, period capacity, class tolls and bus preload assigns CMAP's PM OD (run R4) and is compared with CMAP by facility and vehicle class. Network VMT 0.992, VHT 0.980.

Deck: `CMAP_PM_check_deck.pdf` (source `CMAP_PM_check_deck.tex`, build with `xelatex` twice). Earlier report: `../CMAP_progress_report.pdf`. Period capacity rule: `../period_capacity/`.

## Contents

| Path | What it is |
|---|---|
| `CMAP_PM_check_deck.pdf`, `.tex` | The deck (20 slides) |
| `figs/` | Figures (PNG and PDF): `a8_fig1`-`a8_fig3` CMAP self-check, `a8_fig4`-`a8_fig6` TAPLite, `fig7` run history |
| `figs/map1`-`map4` | Maps (no basemap; connectors not drawn): network by facility with the I-90/94 WB corridor; CMAP PM volume and congestion; TAPLite minus CMAP volume; self-check links over 1 % |
| `scripts/make_maps.py` | Maps from the kit's link shapes and the link-level tables (the tables are not public) |
| `tables/a8_part1_cmap_selfcheck_by_facility.csv` | Self-check by vdf: links, share of links with time within 1 % / 5 % of timau, VMT and VHT (ours and CMAP) |
| `tables/a8_part2_taplite_vmt_vht_by_facility.csv` | TAPLite vs CMAP by facility group: VMT, VHT, ratios, share of links with time within 5 %, median time ratio |
| `tables/a8_part2_taplite_class_volume_by_facility.csv` | TAPLite vs CMAP by facility group and vehicle class: VMT and ratio, link-volume R², % RMSE, share within 10 % (links with CMAP volume >= 100), share with GEH < 5 (hourly flows) |
| `tables/taplite_run_history.csv` | Network VMT and VHT ratio of each TAPLite run (BPR of Nov 6, R1-R4), with sources |
| `tables/taplite_R4_run_info.csv` | R4 and two variants (R4a without bus preload, R4b without class tolls): wall time, memory, iterations, last gap, engine md5 |
| `tables/mode_type.csv`, `settings.csv` | TAPLite classes (VOT, PCE, demand file) and settings of R4 |
| `tables/truck_demand_summary.csv` | Truck OD: rule, total vehicles, cells written, share kept (floor 1e-4 veh) |
| `tables/cmap_period_capacity_rules.csv` | CMAP period capacity rule for the 8 periods (same file as `../period_capacity/`) |
| `scripts/a8_1_tables.py`, `a8_2_figs.py`, `cmap_vdf.py` | Scripts that made the tables and figures, and our Python version of CMAP's fd1-fd8. They ran in the project workspace (paths in each script's header); kept here as the record of the method. |
| `scripts/fig_run_history.py` | Figure 7 from `tables/taplite_run_history.csv` |

## Definitions

- CMAP class volumes are vehicle equivalents (medium x2, heavy x3, bus x3). Vehicles = auto + HOV2 + HOV3 + B-plate + light + medium / 2 + heavy / 3 = CMAP's `@vadt` (no buses).
- V in the link-time functions = all classes + bus (veq), as CMAP's `el1 + el2`.
- VMT = vehicles x length (mi); VHT = vehicles x time (min) / 60; buses not counted.
- GEH on hourly flows: sqrt(2 (m - c)^2 / (m + c)), m = TAPLite, c = CMAP.

## Not in this repository

- CMAP's files: download the c25q4 package from the CMAP Data Hub (link in the kit README). The period class-volume file (`c25q4_100_link_volume_by_vehtype.csv`) was provided by CMAP's data team.
- `tables/link_level/` (in `.gitignore`): link-level tables that carry CMAP's class volumes (all links, PM; I-90/94 WB corridor).
- The TAPLite R4 run folder (inputs about 220 MB, of which the 5 OD files 217 MB; link results, logs, engine source and build).
