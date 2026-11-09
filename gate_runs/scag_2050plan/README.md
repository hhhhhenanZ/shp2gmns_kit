Level reached: L3 (L0-L3 rerun by the author from the raw files in clean folders, all 32 files identical; independent rerun pending). See 99_log/rerun.md.

SCAG RTP24 2050 Plan, AM 6-9 am, TransCAD loaded network converted to GMNS.
Built by `python code/run_gates.py --region region.yaml --data-root <SCAG kit> --run <SCAG>/scag_2050plan`
in shp2gmns_replay_kit. Scope of the SCAG task: replicate SCAG's loaded assignment; congestion and speed
analysis were not part of it. SCAG's 2026-10-15 email (data, class rule) is recorded in
SCAG/SCAG_data_delivery_2026-10-15.md.

| Gate | File | Result |
|---|---|---|
| L0 | 01_topology/L0_counts.csv, zone_split.csv | PASS. 124,076 lines -> 224,288 directed = 173,793 written - 92 split connectors + 50,587 excluded; 4,109 internal zones = T1TAZ polygons (+40 external, 31 seaport, 12 airport); 0 disconnected zones; 0 unreachable trips in all 8 classes. 46 zone nodes that sat on the road network (all 40 external stations, 4 internal zones, 2 seaports) are split off it during conversion (stage 4b, code/src/scag_transcad/zone_split.py): before the split, zone 4140 (I-8 station) and 4181 (seaport, whose only connector led to zone 4179) were cut off and 1,026 AM trips could not be assigned |
| L1 | 02_demand/L1_conservation.csv, L1_class_map.csv | PASS. Source 8,352,381 (AM_OD.mtx.csv) = written 8,291,200 + 61,182 below the 0.01 threshold (trucks 15-17 %, cars < 0.2 %); no trip lost otherwise; all 40 external zones kept. Class map: six SCAG classes, HOV merged with NONHOV (SCAG, Q4) |
| L2 | 03_supply/link.csv, link_vdf.csv, capacity_lookup.csv, L2_unmatched.csv, L2_replay.csv | PASS. 0 unmatched links. At SCAG's own loaded AM flow, Table 16-2 gives road VHT 1.02 x SCAG, median link time ratio 1.000 (freeway 1.04, expressway 1.00, others 1.01). Ramps: vdf_type 7 gives 1.006 x SCAG; type 8 (report's on-ramp function) gives 3,141 x, so ramps now use type 7 |
| L3 | 04_assignment/settings.yaml, link_performance.csv, L3_vmt_vht.csv | PASS (run kept as is). The 2026-09-26 AM run, 8 classes, 20 iterations, relative gap 13.4 % at the end. To converge, set number_of_iterations higher in settings.csv (e.g. 100) and rerun; nothing else needs to change. Road links, model / SCAG: VMT 0.985, VHT 1.29, volume R2 0.84. This run still had vdf_type 8 on the ramps (before the L2 fix): ramp VHT is 17 x SCAG and freeway VMT 0.78 x, so the rerun should also use the current region.yaml (ramps on type 7) |
| L4 | 05_counts/L4_fit.csv | FAIL (comparison pending): screenline counts delivered by SCAG 2026-10-15; comparison left for the next person |
| L5 | 06_congestion/L5_speed_index.csv | BLOCKED: no independent speed data declared yet |
| L6 | 07_transit/L6_station_volume.csv | BLOCKED: transit network not considered for now |
| R | manifest.csv, 99_log/rerun.md | author rerun 2026-11-09 (conversion and gates): all 32 files identical by sha256; rerun by a second person pending |

Network in 01_topology: main_convert.py on region.yaml with --output-root data/output_gates; stage 4b splits the zone
nodes that sit on roads (region.yaml > zones > split_road_zone_nodes). Demand in 02_demand: the 2026-09-26 conversion
(data/output); the split does not change zone ids. data/output itself is left as it was, because the 2026-09-26
assignment run links to its files. L0 and L1 check against SCAG's raw files, read in place (00_raw/EXTERNAL.csv, sha256).
