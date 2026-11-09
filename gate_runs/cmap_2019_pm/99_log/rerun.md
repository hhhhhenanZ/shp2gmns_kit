# Rerun

Rerun from 00_raw with the same repository commit (see manifest.csv), then compare every L file.

| Date | By | Commit | Command | Files compared | Difference | Within tolerance |
|---|---|---|---|---|---|---|
| 2026-11-09 | author, clean folder `../cmap_2019_pm_rerun` | b15bc4c (tag gates-2026-11-09) | `python code/run_gates.py --region region.cmap.yaml --run ../cmap_2019_pm_rerun --steps raw convert publish demand L0 L1 L2` | 24 files in 00_raw, 01_topology, 02_demand, 03_supply (incl. L0_counts, L1_conservation, L1_class_map, L2_replay, L2_unmatched) | none: sha256 identical for all 24 (`../cmap_2019_pm_rerun/rerun_compare.csv`) | yes |

Not rerun: L3 (TAPLite, about 12 min). Independent rerun by a second person: pending.
