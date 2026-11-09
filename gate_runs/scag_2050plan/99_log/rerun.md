# Rerun

Rerun from the raw files with the same repository commit (see manifest.csv), then compare every L file.

| Date | By | Commit | Command | Files compared | Difference | Within tolerance |
|---|---|---|---|---|---|---|
| 2026-11-09 | author, clean folders | b15bc4c (tag gates-2026-11-09) | 1. `python code/main_convert.py --region region.yaml --periods AM --output-root data/output_gates_rerun --skip-demand --skip-stage` (stage 4b finished with `python code/src/scag_transcad/zone_split.py data/output_gates_rerun/network --periods AM`); 2. `python code/run_gates.py --region region.yaml --data-root <SCAG kit> --conversion data/output_gates_rerun --run ../scag_2050plan_rerun` (raw publish L0 L1 L2 L3 status) | conversion: network/AM link.csv, node.csv, zone_split.csv (md5 identical); run folder: 32 files in 00_raw to 07_transit, all L files included | none: sha256 identical for all 32 (`../scag_2050plan_rerun/rerun_compare.csv`) | yes |

Not rerun: the demand conversion (2026-09-26, data/output; L1 checks it against AM_OD.mtx.csv) and the TAPLite run behind L3 (L3 is recomputed from its link_performance.csv). Independent rerun by a second person: pending.
