# CMAP highway network -> GMNS: conversion report (PM)

Generated 2026-10-28 01:22 UTC by `code/src/cmap_emme` (`region.cmap.yaml`).

## Sources

- **[G]** CMAP Travel Demand Model Data User Guide (c25q4): `data/input/cmap/docs/data_user_guide.html`. Download (CMAP Data Hub, c25q4 package): https://datahub.cmap.illinois.gov/documents/a14d641dbe184704ab597479b103986c/explore
- **[A]** ON TO 2050 plan update: Travel demand model appendix: `data/input/cmap/docs/ON-TO-2050-Update-Travel-Demand-Model-Documentation-Appendix.pdf`. Download: https://cmap.illinois.gov/wp-content/uploads/ON-TO-2050-Update-Travel-Demand-Model-Documentation-Appendix.pdf (printed page numbers)
- **[C]** CMAP trip-based model code (Ftime_capacity.py, TOD_network_prep.py, vdf_tod.in): `data/input/cmap/docs/cmap_code/`. Source: https://github.com/CMAP-REPOS/cmap_trip-based_model/tree/e52b3185920b139fb77983a74458b05fa4923890/Database
- Model: CMAP trip-based model, conformity cycle c25q4, scenario 100 = 2019 base year.
- Period: PM = Emme period 7, 16:00-18:00 (2 h).

## Result

- `network/PM/node.csv`: 20,190 nodes, of which 3,649 zone centroids (ids 1-3649).
- `network/PM/link.csv`: 55,005 links; none excluded.
- Gates: 29 PASS, 0 FAIL, 17 INFO (`checks/gate_report.csv`).
- Shapefile read with: built-in reader. Reprojection: built-in (TM inverse, Clarke 1866 + Molodensky NAD27 CONUS).

## Assignment test (TAPLite, BPR)

This network and demand were assigned in TAPLite as a first end-to-end test (PM, BPR alpha 0.15, beta 4, no tolls, 10 iterations, gap 0.18 %). Against CMAP's own PM assignment, all links: VMT 0.925, VHT 0.710, delay 0.109, link volume R^2 0.93 (road links). Volumes match; BPR adds too little delay. Inputs, run scripts and evaluation: https://github.com/hhhhhenanZ/city-tensor/tree/main/cmap_ta_bpr_allmodes. Summary: `report/CMAP_progress_report.pdf`, sections 4-5.

## By VDF class

| vdf_code | facility_type | links | miles | lane_miles | lanes_min | lanes_median | lanes_max | capacity_vphpl_median | capacity_vphpl_range | free_speed_mph_median | pm_vmt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | arterial street | 41861 | 30632.2 | 36969.3 | 1 | 1.0 | 6 | 790.0 | 288-1449 | 35.0 | 16836841 |
| 2 | freeway | 1998 | 2047.1 | 5512.2 | 1 | 3.0 | 7 | 2000.0 | 1140-2000 | 55.0 | 10565352 |
| 3 | freeway-arterial ramp | 1992 | 547.8 | 586.1 | 1 | 1.0 | 4 | 1450.0 | 620-1600 | 30.0 | 364490 |
| 4 | expressway | 930 | 595.4 | 1296.6 | 1 | 2.0 | 5 | 1700.0 | 1020-2000 | 45.0 | 1436129 |
| 5 | freeway-freeway ramp | 664 | 229.0 | 303.5 | 1 | 1.0 | 4 | 1450.0 | 1060-1600 | 30.0 | 338540 |
| 6 | zone centroid connector | 7264 | 5051.6 | 5051.6 | 1 | 1.0 | 1 | placeholder 99999 | - | 20.0 | 3893909 |
| 7 | toll collection link | 188 | 31.0 | 81.8 | 1 | 2.0 | 9 | placeholder 99999 | - | 30.0 | 67954 |
| 8 | metered entrance ramp | 108 | 23.1 | 23.1 | 1 | 1.0 | 1 | 720.0 | 720-720 | 25.0 | 19478 |

## Units

| Quantity | Source (CMAP) | Output (GMNS, kit convention) | Reference |
|---|---|---|---|
| length | miles (`LENGTH`) | metres (`length`); miles kept in `vdf_length_mi` | [A] Table 18 p.47; [G] link field 4 |
| speed | mph (`@speed`, posted; `@ftime` uses it rounded up to a bin) | km/h (`free_speed`); mph in `vdf_free_speed_mph`, both from `@ftime` | [G]; [C] Ftime_capacity.py |
| free-flow time | minutes (`@ftime`) | minutes (`vdf_fftt`) | [A] Table 18 p.47, p.49 |
| capacity | vehicles/hour/**lane**, LOS E (`@emcap`) | vehicles/hour/lane (`capacity`); per link in `hourly_link_capacity` | [G]; [A] pp.48-49 |
| volume | vehicles per **2-hour** period (`DATA1` = `@vadt`) | same (`ref_volume`) | [G] PM Peak Highway Network Shapefiles |
| congested time | minutes (`TIMAU`) | minutes (`ref_time`, `timau`) | [G] |
| toll | US dollars per link (`@toll`; CMAP adds it unchanged as link cost) | US dollars per link (`toll`) | [C] SOLA_assignment.py; [G] |
| coordinates | US survey feet, NAD27 / Illinois East (EPSG:26771) | degrees, EPSG:4326 | [A] Table 19 p.48 |

Units are also given per column in `FIELD_PROVENANCE.csv`.

`@ftime` is computed by CMAP's `Ftime_capacity.py` ([C]): `@speed` is rounded up to a bin and `@ftime = length / binned speed x 60`. Bins: VDF 2, 4 = 40-65 (> 60 -> 65); VDF 1 = 15-55; VDF 3, 5, 8 = 15-50; VDF 8 adds 0.083 min (5-s meter delay); VDF 6 = length x 3 (20 mph); VDF 7 uses the incoming link's speed. `vdf_fftt` uses `@ftime` as given; where it differs from `LENGTH / @speed` is listed in `checks/ftime_vs_posted_speed.csv`.

## Decisions

1. **Connector and toll-link capacity = 99,999 placeholder (CMAP only).** CMAP's `@emcap` is 0 on every VDF 6 (centroid connector) and VDF 7 (toll collection) link and CMAP does not constrain them ([G]; [A] p.126). There is no reference value, so 99,999 is written only to avoid dividing by zero, with vdf_type 0, alpha 0.0, beta 1.0: time stays at `@ftime` at every volume, so the value does not change the assignment. 7,452 links carry it, marked `capacity_source = placeholder_no_constraint`. Set in `region.cmap.yaml > vdf > no_capacity_links`. NVTA (3,150) and SCAG (their own file) are not affected.
2. **Connectors are VDF 6, not every link touching a zone.** The road links leaving zones 3633-3649 keep `@emcap` and their own VDF (`checks/zone_road_links.csv`).
3. **Toll links are kept.** They are in series on the tollways; deleting them disconnects part of the network and removes the toll from route choice.
4. **Capacity is CMAP's own `@emcap` only.** The 0.75 (VDF 1, 3) and +300 (VDF 2) are part of CMAP's functions and are kept in `parameters/vdf_parameters.csv`, not in `capacity`.
5. **TAPLite form for VDF 1-5 and 8 is left open** (blank vdf_type/alpha/beta). CMAP's min-term and signal delay are not kernel functions; the form is chosen in the replay step.

## Volume-delay functions vs CMAP's own PM times

v = `DATA1` (vehicles). CMAP's functions use vehicle equivalents including buses, which the PM files do not carry, so the error tail on VDF 2 and 4 is expected.

- Functions are evaluated as CMAP runs them ([C] `vdf_tod.in`, `TOD_network_prep.py`): ul2 = 0.75 x `@emcap` x lanes x 2 on VDF 1-5 (the appendix names the 0.75 only for arterials), `@emcap` x lanes x 2 on VDF 8; fd2 divides ul1 by 1.15.
- Remaining error: v here is `DATA1` in vehicles; CMAP uses vehicle equivalents plus bus equivalents (el2), which the PM files do not carry.
- **VDF 1, 3.** Signal delay needs `@cycle`, `@gc` (ul3), not exported.

| vdf_code | name | variant | links | links_evaluated | median_rel_error | p90_abs_rel_error | timau_over_ftime_at_vc_below_0.1 | note |
|---|---|---|---|---|---|---|---|---|
| 1 | arterial street | as documented | 41861 | 41861 | -0.2179 | 0.5664 | 1.144 | BPR part only: intersection delay needs @gc, @cycle (not exported) |
| 2 | freeway | as documented | 1998 | 1998 | -0.0951 | 0.4162 | 0.886 |  |
| 2 | freeway | without the /1.15 on T0 | 1998 | 1998 | 0.0407 | 0.3287 | 0.886 |  |
| 3 | freeway-arterial ramp | as documented | 1992 | 1992 | -0.0004 | 0.401 | 1.0 | BPR part only: intersection delay needs @gc, @cycle (not exported) |
| 4 | expressway | as documented | 930 | 930 | -0.0131 | 0.1957 | 1.017 |  |
| 5 | freeway-freeway ramp | as documented | 664 | 664 | -0.0004 | 0.1938 | 1.0 |  |
| 6 | zone centroid connector | as documented | 7264 | 7264 | 0.0 | 0.0 |  | fixed time |
| 7 | toll collection link | as documented | 188 | 188 | 0.0 | 0.0 |  | fixed time |
| 8 | metered entrance ramp | as documented | 108 | 108 | -0.0004 | 0.1564 | 1.0 |  |

## Reference fields: ref_volume, ref_time, timau

CMAP runs a static equilibrium assignment per period. For PM (4-6 pm) every link ends with one volume and one time:

- `ref_volume` = `DATA1` (= `@vadt`): vehicles over the whole **2-hour** period, not per hour.
- `ref_time` = `timau` = `TIMAU`: the VDF time ([C] `vdf_tod.in`) at that final volume, in minutes. One time for 4-6 pm at the period-average flow rate; no change within the period, no queue spillback. A model output, not observed ([G]: "raw model results").
- Every link has both values; 2,823 links have zero volume and keep their free-flow time. Connectors are distance-based in every period ([G]).
- Use: the answer key for a TAPLite replay with the same OD. Time-of-day congestion comes from TMC / QVDF, not from these fields.

## allowed_use

| MODES | links | allowed_use |
|---|---|---|
| ASHThmlb | 50274 | sov;hov2;hov3;apv;btrk;ltrk;mtrk;htrk |
| ASHTb | 1995 | sov;hov2;hov3;apv;btrk |
| ASH | 1518 | sov;hov2;hov3;apv |
| ASHTlb | 875 | sov;hov2;hov3;apv;btrk;ltrk |
| ASHTmlb | 343 | sov;hov2;hov3;apv;btrk;ltrk;mtrk |

## Demand (PM)

Built as CMAP's `Database/macros/ttables.mac` builds the period-7 tables ([C]); factors from `tod_factors.p7` = [G] TOD conversion table, TOD7. Matrices from `emmemat_c25q4_100.zip` (mf417-mf457 PM auto vehicles from the demand model; mf4-mf10 daily, factored). Files `demand/PM/<mode_type>_PM.csv`: `o_zone_id,d_zone_id,volume`, vehicles per 2-hour period.

- Total 3,527,729 vehicles; written 3,481,077 (98.68%). Cells at or below 0.01 are not written and **not rescaled** (first version).
- Medium and heavy trucks are in vehicles; CMAP's x2 / x3 vehicle equivalents are `pce` in `parameters/mode_type_by_period.csv`.
- Airport trips (mf10) are `apv`; CMAP folds them into SOV.
- Not included: park-and-ride first legs (mf59, built inside CMAP's run, not exported); bus vehicle equivalents (a link preload, replay step).

| mode_type | rule | total_vehicles | cells_written | vehicles_written | share_kept | vehicles_dropped |
|---|---|---|---|---|---|---|
| sov | 1.0 x mf417 + 1.0 x mf427 + 1.0 x mf437 + 0.155 x mf8 | 2393512.6 | 818885 | 2393483.0 | 1.0 | 29.7 |
| hov2 | 1.0 x mf447 | 513112.0 | 342932 | 513112.0 | 1.0 | 0.0 |
| hov3 | 1.0 x mf457 | 141611.8 | 204014 | 141611.8 | 1.0 | 0.0 |
| apv | mf10 x 0.155 to airport zones + x 0.155 from airport zones to unflagged zones | 11838.7 | 26944 | 11828.9 | 0.9992 | 9.8 |
| btrk | 0.176 x mf4 | 307562.9 | 1338781 | 296930.8 | 0.9654 | 10632.1 |
| ltrk | 0.176 x mf5 | 51627.0 | 718863 | 37108.4 | 0.7188 | 14518.6 |
| mtrk | 0.176 x mf6 | 48066.4 | 664820 | 34066.9 | 0.7087 | 13999.6 |
| htrk | 0.103 x mf7 + 0.103 x mf9 | 60398.0 | 659707 | 52935.2 | 0.8764 | 7462.8 |

mode_type values:

| mode_type_id | mode_type | name | vot | pce | occ | demand_file |
|---|---|---|---|---|---|---|
| 1 | sov | SOV + external auto | 20.49 | 1 | 1.0 | sov_PM.csv |
| 2 | hov2 | HOV2 | 20.25 | 1 | 2.0 | hov2_PM.csv |
| 3 | hov3 | HOV3+ | 31.5 | 1 | 3.36 | hov3_PM.csv |
| 4 | apv | air passenger | 30.0 | 1 | 1.0 | apv_PM.csv |
| 5 | btrk | B-plate truck | 24.0 | 1 | 1.0 | btrk_PM.csv |
| 6 | ltrk | light truck | 32.0 | 1 | 1.0 | ltrk_PM.csv |
| 7 | mtrk | medium truck | 47.0 | 2 | 1.0 | mtrk_PM.csv |
| 8 | htrk | heavy truck | 52.0 | 3 | 1.0 | htrk_PM.csv |

## Not converted / not found

- `emme_turns.dbf` (turn penalties and bans): listed, not converted.
- `@gc`, `@cycle` (signal green/cycle) are not exported, so the arterial intersection delay (VDF 1, 3) cannot be reproduced.
- Class volumes for the PM period are not in the PM files.
- `VOLAU` in the shapefile is not a volume and is not used.

## Gates

| gate | check | status | value | expected |
|---|---|---|---|---|
| G1 | node count | PASS | 20190 | 20190 |
| G1 | link count | PASS | 55005 | 55005 |
| G1 | zones flagged ISZONE = 1, ids contiguous | PASS | 3649 zones, ids 1-3649 | 3649 zones, ids 1-3649 |
| G1 | every link end is a node | PASS | 0 | 0 |
| G2 | shapefile joined to extra attributes on (i, j) | PASS | 55005 / 55005 | 55005 / 55005 |
| G3 | lanes >= 1 | PASS | 0 | 0 |
| G4 | @emcap > 0 on every VDF 1-5 and 8 link | PASS | 0 | 0 |
| G5 | placeholder 99999 only on VDF 6 and 7, alpha 0 | PASS | 7452 links (VDF 6: 7264, VDF 7: 188) | VDF 6 + VDF 7 count |
| G5 | road links touching a zone keep @emcap (not treated as connectors) | PASS | 32 links, VDF [1, 2, 4] | all cmap_emcap |
| G6 | one strongly connected network | PASS | 0 nodes / 0 zones outside the largest component | 0 / 0 |
| G7 | every zone has an outgoing and an incoming link | PASS | 0 | 0 |
| G8 | coordinates inside the CMAP region | PASS | lat 40.994-42.967, lon -89.456--86.484 | lat [40.5, 43.5], lon [-90.0, -86.0] |
| G9 | ref_volume (DATA1) = @vadt | PASS | max diff 0.0005 | equal |
| G9 | ref_time and timau (TIMAU) = attribs timau | PASS | max diff 1e-06 | equal |
| G10 | VDF 1 arterial street: median error vs CMAP timau | INFO | -0.2179 | reported |
| G10 | VDF 2 freeway: median error vs CMAP timau | INFO | -0.0951 | reported |
| G10 | VDF 3 freeway-arterial ramp: median error vs CMAP timau | INFO | -0.0004 | reported |
| G10 | VDF 4 expressway: median error vs CMAP timau | INFO | -0.0131 | reported |
| G10 | VDF 5 freeway-freeway ramp: median error vs CMAP timau | PASS | -0.0004 | |e| < 0.01 |
| G10 | VDF 6 zone centroid connector: median error vs CMAP timau | PASS | 0.0 | |e| < 0.01 |
| G10 | VDF 7 toll collection link: median error vs CMAP timau | PASS | 0.0 | |e| < 0.01 |
| G10 | VDF 8 metered entrance ramp: median error vs CMAP timau | PASS | -0.0004 | |e| < 0.01 |
| G10 | VDF 2 freeway (without the /1.15 on T0) | INFO | 0.0407 | reported |
| G11 | free speed 5-85 mph on non-connector links | INFO | 0 outside (listed in checks/free_speed_outliers.csv) | reported |
| G11 | links with @speed = 0 | INFO | 159 (VDF [7]) | reported |
| G11 | units: median @ftime / (LENGTH / @speed x 60) = 1 (min, mi, mph) | PASS | median 1.0000; 0.9844 of 47582 links exactly | 1.00 within 1% |
| G11 | links where @ftime follows a CMAP free-speed rule, not @speed | INFO | 741 links in 10 (VDF, posted speed) groups (checks/ftime_vs_posted_speed.csv) | reported; @ftime is used as given |
| G11 | connector effective speed LENGTH / @ftime | INFO | 20.0 mph | reported (posted 30) |
| G11 | units: LENGTH (mi) vs straight-line node distance (US ft / 5280) | PASS | median ratio 1.005 | within 5% of 1 |
| G12 | node count = network_p7.txt | PASS | 20190 | 20190 |
| G12 | link count = network_p7.txt | PASS | 55005 | 55005 |
| G12 | lanes = network_p7.txt | PASS | 1.0000 equal | 1.0000 |
| G12 | every link has a line geometry | PASS | 0 | 0 |
| D1 | every .emx is 3649 x 3649 float32 | PASS | 12 matrices read | 53,260,804 bytes each |
| D2 | zone ids 1-3649 are centroids in node.csv | PASS | 3649 centroids | 1-3649 |
| D3 | every demand file has o_zone_id,d_zone_id,volume and > 0 rows | PASS | 8 files | 8 files |
| D4 | mf417 + mf427 + mf437 = trip_roster PM2 mode 1 | PASS | 2,351,437.0 | 2,351,437 |
| D5 | demand modes = allowed_use modes | PASS | demand ['apv', 'btrk', 'hov2', 'hov3', 'htrk', 'ltrk', 'mtrk', 'sov'] | allowed_use ['apv', 'btrk', 'hov2', 'hov3', 'htrk', 'ltrk', 'mtrk', 'sov'] |
| D6 | sov: share kept at volume > 0.01 | INFO | 100.00% (30 veh dropped) | reported |
| D6 | hov2: share kept at volume > 0.01 | INFO | 100.00% (0 veh dropped) | reported |
| D6 | hov3: share kept at volume > 0.01 | INFO | 100.00% (0 veh dropped) | reported |
| D6 | apv: share kept at volume > 0.01 | INFO | 99.92% (10 veh dropped) | reported |
| D6 | btrk: share kept at volume > 0.01 | INFO | 96.54% (10,632 veh dropped) | reported |
| D6 | ltrk: share kept at volume > 0.01 | INFO | 71.88% (14,519 veh dropped) | reported |
| D6 | mtrk: share kept at volume > 0.01 | INFO | 70.87% (14,000 veh dropped) | reported |
| D6 | htrk: share kept at volume > 0.01 | INFO | 87.64% (7,463 veh dropped) | reported |
