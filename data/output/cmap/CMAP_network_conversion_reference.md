# CMAP Emme → GMNS/TAPLite Conversion: Quick Reference

Conformity cycle `c25q4`, scenario 100 (2019 base year) · PM period (Emme period 7, 4–6 pm) · 55,005 Emme links → 55,005 GMNS links · 3,649 zones · 27 Oct 2026

Compiled version: `CMAP_network_conversion_reference.pdf`, built from `CMAP_network_conversion_reference.tex` in this folder.

---

## 1. Inputs → code → outputs

| INPUT | CODE | OUTPUT |
|---|---|---|
| `highwayshp_pmpk/emme_links.shp`, `emme_nodes.shp` (+ `.dbf .shx .prj .cpg`) | `cmap_emme/emme_read.py`, `cmap_emme/network.py` | `network/PM/node.csv`, `network/PM/link.csv`, `network/link_geometry.csv` |
| `emmenet_highway/attribs_p7.txt` (`@speed @ftime @emcap @toll` …) | `cmap_emme/vdf.py`, `cmap_emme/access.py` | capacity, free-flow, VDF, `allowed_use`; `parameters/vdf_parameters.csv` |
| `c25q4_100/emmemat_c25q4_100.zip` (`.emx`, read in place) | `cmap_emme/demand.py` | `demand/PM/sov_PM.csv` … (8 files); `parameters/mode_type_by_period.csv` |
| `emmenet_highway/network_p7.txt` | `cmap_emme/checks.py` | `checks/gate_report.csv` (cross-check only) |

| | |
|---|---|
| Driver | `python code/main_convert.py --region region.cmap.yaml --periods PM` (`--skip-demand`: network only) |
| Code root | `shp2gmns_replay_kit/code/src/cmap_emme/`; every CMAP number lives in `region.cmap.yaml` |
| Output root | `shp2gmns_replay_kit/data/output/cmap/`; gates: 29 PASS, 0 FAIL, 17 INFO |

## 2. Source tags used below

| Tag | Source | Tag | Source |
|---|---|---|---|
| [G] | CMAP Travel Demand Model Data User Guide (c25q4), in the data package: [CMAP Data Hub](https://datahub.cmap.illinois.gov/documents/a14d641dbe184704ab597479b103986c/explore) | [FT] | `Database/macros/Ftime_capacity.py` (`@ftime`, `@emcap`) |
| [A] | ON TO 2050 travel demand model appendix: [cmap.illinois.gov](https://cmap.illinois.gov/wp-content/uploads/ON-TO-2050-Update-Travel-Demand-Model-Documentation-Appendix.pdf) (printed page numbers) | [TOD] | `Database/macros/TOD_network_prep.py` (VDF inputs ul1–ul3) |
| [VDF] | `Database/data/vdf_tod.in` (functions fd1–fd8 as run) | [TT] | `Database/macros/ttables.mac` (period trip tables) |
| [TF] | `Database/data/tod_factors.p7` (PM factors r19–r26) | [FL] | `Database/data/tod_flags.in` (airport and CBD zone flags) |
| [SOLA] | `Database/macros/SOLA_assignment.py` (toll as link cost) | [Y] | `region.cmap.yaml` |
| [m] | measured from the c25q4 PM files | | |

The code files come from [CMAP-REPOS/cmap_trip-based_model](https://github.com/CMAP-REPOS/cmap_trip-based_model), commit `e52b318` (2026-04-30). Copies are in `data/input/cmap/docs/cmap_code/`.

## 3. The input files at a glance

| Facts [m] | What it actually is |
|---|---|
| 55,005 directed links, 20,190 nodes; no duplicate (i, j) | Emme PM-peak network exported to shapefile [G] |
| Zones 1–3649, contiguous, `ISZONE = 1`; node < 5000 is a centroid | Zones already come first: **no renumbering** |
| CRS NAD27 / Illinois East, US survey feet (EPSG:26771) → EPSG:4326 | [A] T19 p.48. The model area includes Winnebago County, northwestern Indiana and southeastern Wisconsin |
| The shapefile has **no** capacity, speed or free-flow time | These are in `attribs_p7.txt`, joined on (i, j): 55,005 / 55,005 |
| `DATA1` = `@vadt`; `TIMAU` = `timau` on every link | CMAP's assigned PM volume and congested time |

| | |
|---|---|
| **Used** | shapefile `ID INODE JNODE LENGTH MODES LANES VDF DATA1 TIMAU`; attribs `@speed @ftime @emcap @toll @tipid @width @parkl @sigic @vadt timau` |
| **Ignored** | `TYPE` (always 1); `VOLAU` / `VOLAD` (**not volumes**: median 3,648); `DATA2`, `DATA3` (all 0); `@avelw` (same kind as `@width`); `emme_turns.dbf` (turns, not converted) |

## 4. Code tables

**`VDF`: volume-delay function code** [A] T18 p.47, [G]

| Code | Meaning | Links | PM VMT |
|---|---|---|---|
| 1 | Arterial street | 41,861 | 16,836,841 |
| 2 | Freeway | 1,998 | 10,565,352 |
| 3 | Freeway → arterial ramp | 1,992 | 364,490 |
| 4 | Expressway | 930 | 1,436,129 |
| 5 | Freeway → freeway ramp | 664 | 338,540 |
| 6 | Zone centroid connector | 7,264 | 3,893,909 |
| 7 | Toll collection link | 188 | 67,954 |
| 8 | Metered entrance ramp | 108 | 19,478 |
| | **total** | **55,005** | **33,522,694** |

**`MODES` letters** [A] T18 p.47:

| Letter | Meaning |
|---|---|
| A | primary auto |
| S | SOV |
| H | HOV |
| T | general truck |
| b | B-plate truck |
| l | light truck |
| m | medium truck |
| h | heavy truck |

B-plate trucks ([A] p.111) are vans, pickups and SUVs under 8,000 lb that carry "B" plates. Only their commercial use is counted here; personal use is in the household trips.

**Mode codes** (= OD vehicle classes) [Y] `access`:

| Letter | Mode codes |
|---|---|
| A | `sov;apv` |
| S | `sov` |
| H | `hov2;hov3` |
| b | `btrk` |
| l | `ltrk` |
| m | `mtrk` |
| h | `htrk` |
| T | adds nothing |

**`MODES` → `allowed_use`** (NVTA convention: mode codes, `;`-separated)

| MODES | `allowed_use` written | Links | Meaning |
|---|---|---|---|
| `ASHThmlb` | `sov;hov2;hov3;apv;btrk;ltrk;mtrk;htrk` | 50,274 | all vehicles |
| `ASHTb` | `sov;hov2;hov3;apv;btrk` | 1,995 | autos and B-plate only |
| `ASH` | `sov;hov2;hov3;apv` | 1,518 | no trucks |
| `ASHTlb` | `sov;hov2;hov3;apv;btrk;ltrk` | 875 | no medium or heavy |
| `ASHTmlb` | `sov;hov2;hov3;apv;btrk;ltrk;mtrk` | 343 | no heavy |

Every PM link carries A, S and H (there are no HOV-only lanes), and no link is `closed`.

## 5. Master lookup: free-flow time, capacity, VDF

**Free-flow time `@ftime`** [FT]: `@speed` is rounded **up** to a bin, then `@ftime = length / bin speed × 60`. The converter uses `@ftime` as given. Recomputed from `@speed`, it matches on 100 % of VDF 1–6 and 8 links [m].

| VDF | Speed bins (mph) | Extra | `@ftime` ≠ `LENGTH/@speed` [m] |
|---|---|---|---|
| 2, 4 | 40, 45, 50, 55, 60, 65 (≤ 40 → 40, > 60 → 65) | — | 520 (e.g. freeway 70 → 65; expressway 25–35 → 40) |
| 1 | 15, 20, …, 50, 55 (> 50 → 55) | signal delay added later, in fd1 | 0 |
| 3, 5, 8 | 15, 20, …, 45, 50 (> 45 → 50) | VDF 8: + 0.083 min (5-second meter delay) | 220 (ramps 55–65 → 50; VDF 8) |
| 6 | — | `@ftime = length × 3` (20 mph) | — |
| 7 | — | posted speed of the incoming link | 1 |

**Capacity `@emcap`** (veh/h/**lane**, LOS E) [FT], [G]

| VDF | Facility | Median | Range | Distinct values |
|---|---|---|---|---|
| 1 | arterial | 790 | 288–1,449 | 254 |
| 2 | freeway | 2,000 | 1,140–2,000 | 7 |
| 3 | fwy → art ramp | 1,450 | 620–1,600 | 8 |
| 4 | expressway | 1,700 | 1,020–2,000 | 16 |
| 5 | fwy → fwy ramp | 1,450 | 1,060–1,600 | 6 |
| 8 | metered ramp | 720 | 720 | 1 |
| 6, 7 | connector, toll | 0 in CMAP → 99,999 placeholder | | |

Freeway `@emcap` is 2,000 for every lane count from 1 to 7, so it is a per-lane value. Arterial capacity depends on the downstream intersection: number of approaches, lane width and functional class ([FT] l.250–330).

**VDF inputs as CMAP runs them** [TOD], [VDF]

| Input | Value |
|---|---|
| `ul1` | `@ftime` |
| `ul2` | 0.75 × `@emcap` × lanes × H on **VDF 1–5**; `@emcap` × lanes × H on VDF 8; PM H = 2 |
| `ul3` | signal cycle and g/C (VDF 1, 3); **not exported** |
| v | `volau + el2`: vehicle equivalents plus bus vehicle equivalents |

[A] p.123 names the 0.75 only for arterials. The code applies it to VDF 1–5, and the conversion follows the code.

**Functions** [VDF], and how well they reproduce CMAP's `timau` with v = `DATA1` [m]:

| VDF | Name | fd (as run) | Median error | TAPLite form |
|---|---|---|---|---|
| 1, 3 | arterial, ramp | u1 [1 + 0.15 (v/u2)^4] + Webster uniform and incremental delay from u3, capped at one cycle | −21.8 %, −0.04 % | open |
| 2 | freeway | [1 + 0.15 min(v/u2, 1)] (u1 / 1.15) [1 + 0.15 (v / (u2 + 300))^8] | −9.5 % | open |
| 4 | expressway | [1 + 0.15 min(v/u2, 1)] u1 [1 + 0.15 (v/u2)^8] | −1.3 % | open |
| 5 | fwy → fwy ramp | u1 [1 + 0.15 (v/u2)^8] | −0.04 % | open |
| 6 | connector | length × 3 | 0.0 % | type 0, α = 0 |
| 7 | toll link | u1 | 0.0 % | type 0, α = 0 |
| 8 | metered ramp | u1 [1 + 0.15 (v/u2)^10] | −0.04 % | open |

The remaining error comes from the volume: `DATA1` counts vehicles, while CMAP's v counts vehicle and bus equivalents. VDF 1 also misses the signal delay, because `@cycle` and `@gc` were not exported.

The TAPLite form for VDF 1–5 and 8 is chosen in the replay step, so `vdf_type`, `vdf_alpha` and `vdf_beta` are blank on those links.

## 6. `node.csv`

| Column | From | Rule [Y], `network.py` |
|---|---|---|
| `node_id` | `emme_nodes.dbf ID` | Emme node number, unchanged |
| `zone_id` | `ISZONE` | = `node_id` where `ISZONE = 1` (1–3649); else blank |
| `x_coord` | `X` (US survey ft) | EPSG:26771 → EPSG:4326, degrees |
| `y_coord` | `Y` (US survey ft) | same |
| `node_type` | `ISZONE` | `centroid` or `road` |
| `cmap_label` | `LABEL` | as given |

20,190 rows, of which 3,649 are centroids.

Reprojection uses pyproj when it is installed. Otherwise the converter falls back to a built-in inverse Transverse Mercator (Clarke 1866) followed by a Molodensky NAD27 → WGS84 shift. The fallback was checked against a pyproj-based CMAP–OSM match: median distance 2.11 m vs 2.12 m [m].

## 7. `link.csv`

| Column | Formula | Unit | Note |
|---|---|---|---|
| `link_id` | row number 1..N | — | shapefile order |
| `from_node_id` | `INODE` | — | |
| `to_node_id` | `JNODE` | — | |
| `dir_flag` | 1 | — | Emme links are directed |
| `length` | `LENGTH` × 1609.344 | **meter** | source is miles [A] T18 |
| `lanes` | `LANES` | — | ≥ 1 on every link |
| `capacity` | `@emcap`; 99,999 on VDF 6, 7 | **veh/h/lane** | §5; placeholder in §11 |
| `free_speed` | `vdf_free_speed_mph` × 1.609344 | **kph** | from `@ftime`, not `@speed` |
| `toll` | `@toll` | **dollar per link** | CMAP adds it unchanged as link cost [SOLA] |
| `link_type` | `VDF` | — | = `vdf_code` |
| `allowed_use` | `MODES` → mode codes | — | §4 |
| `vdf_type` | 0 on VDF 6, 7; blank otherwise | — | set in the replay step |
| `vdf_alpha` | 0 on VDF 6, 7; blank otherwise | — | |
| `vdf_beta` | 1 on VDF 6, 7; blank otherwise | — | |
| `vdf_plf` | 1.0 | — | period capacity = `@emcap` × lanes × 2 [G] |
| `ref_volume` | `DATA1` (= `@vadt`) | **veh per 2-h period** | CMAP's assigned PM volume, not per hour |
| `ref_time` | `TIMAU` (= `timau`) | **minute** | VDF time at that volume; see below |
| `vdf_free_speed_mph` | `LENGTH / @ftime × 60` | **mph** | binned speed [FT] |
| `vdf_length_mi` | `LENGTH` | **mile** | |
| `vdf_fftt` | `@ftime` | **minute** | as given [FT] |
| `org_link_id` | `ID` (`"i-j"`) | — | |
| `vdf_code` | `VDF` | — | 1–8 |
| `facility_type` | name of the VDF code | — | §4 |
| `capacity_source` | `cmap_emcap` / `placeholder_no_constraint` | — | filter on this before computing D/C |
| `hourly_link_capacity` | `capacity` × `lanes` | veh/h/link | |
| `tipid`, `width`, `parkl`, `sigic` | `@tipid`, `@width`, `@parkl`, `@sigic` | —, ft, count, 0/1 | CMAP names without the `@` |
| `timau` | `TIMAU` | minute | same as `ref_time`, under CMAP's name |

**Unit contract** (kit convention, `dtalite4cube/unit_contract.py`):
- `length` = `vdf_length_mi` × 1609.344
- `free_speed` = `vdf_free_speed_mph` × 1.609344
- `vdf_fftt` = 60 × `vdf_length_mi` / `vdf_free_speed_mph`

**What `ref_time` / `timau` is** [G], [VDF]

CMAP runs a static equilibrium assignment for each period. Every link ends with one volume (`DATA1`, for the whole 2 hours) and the VDF time at that volume. That gives one time for 4–6 pm at the period-average flow rate: it does not change within the period and does not model queue spillback.

It is a model output, which [G] calls "raw model results". The 2,823 links with zero volume keep their free-flow time.

## 8. Demand

The PM tables are built the way CMAP's `ttables.mac` builds its period-7 tables [TT]. The factors come from [TF], which match the TOD7 column of the [G] table "Daily truck and external trip time-of-day conversion". Each `.emx` file is float32, 3649 × 3649, with no header.

| mode | File | Rule ([TT] line) | PM veh | Rows | Kept | MB |
|---|---|---|---|---|---|---|
| `sov` | `sov_PM.csv` | mf417 + mf427 + mf437 + 0.155 × mf8 (l.392–444) | 2,393,513 | 818,885 | 100.0 % | 10.1 |
| `hov2` | `hov2_PM.csv` | mf447 | 513,112 | 342,932 | 100.0 % | 4.3 |
| `hov3` | `hov3_PM.csv` | mf457 | 141,612 | 204,014 | 100.0 % | 3.6 |
| `apv` | `apv_PM.csv` | 0.155 × mf10, airport rule (l.464–465) | 11,839 | 26,944 | 99.9 % | 0.5 |
| `btrk` | `btrk_PM.csv` | 0.176 × mf4 (l.601) | 307,563 | 1,338,781 | 96.5 % | 25.1 |
| `ltrk` | `ltrk_PM.csv` | 0.176 × mf5 (l.626) | 51,627 | 718,863 | 71.9 % | 13.7 |
| `mtrk` | `mtrk_PM.csv` | 0.176 × mf6 (l.658) | 48,066 | 664,820 | 70.9 % | 12.7 |
| `htrk` | `htrk_PM.csv` | 0.103 × mf7 + 0.103 × mf9 (l.684–685) | 60,398 | 659,707 | 87.6 % | 12.7 |
| | | **total** | **3,527,730** | **4,774,946** | **98.7 %** | **82.7** |

| | |
|---|---|
| Format | `o_zone_id,d_zone_id,volume`. Zone ids 1–3649 are the centroid `node_id`s. Volume is **vehicles per 2-hour period**. Intrazonal cells are kept. |
| Floor | Cells ≤ 0.01 are not written and **not rescaled** (first version). The kept share per mode is in `parameters/demand_summary.csv`. |
| PM autos | mf417–mf457 are PM vehicle trips from CMAP's demand model (`mf41y..mf45y` with y = 7). PM2 = period 7 per `setup_transit_asmt_3_TOD_transit_demand.py`. mf417 + mf427 + mf437 = 2,351,437, which equals `trip_roster` PM2 mode 1 [m]. |
| Airport | Zones flagged ≥ 2 in [FL]: O'Hare 123–127, 129, 130; Midway 494; 1733, 1734, 1969, 2907. CBD zones 1–47 are flagged 1. A trip is kept if it goes to an airport, or from an airport to an unflagged zone. CMAP folds these trips into SOV; here they are kept as `apv` (our choice). |
| Trucks | CMAP converts trucks to vehicle equivalents inside `ttables.mac` (medium × 2, heavy × 3). Here they are written as vehicles, with the factor in `pce`. mf9 goes into heavy: "externals, which are assumed to be primarily heavy trucks" ([TT] l.676). |
| Not included | park-and-ride first legs (mf59, built inside CMAP's run); bus vehicle equivalents (a link preload, handled in the replay step) |
| Do not use | emmemat mf94–mf97 and mf14–mf18 hold period 8, the last period assigned (e.g. mf14 = 0.152 × mf4) |

## 9. `mode_type.csv` values (`parameters/mode_type_by_period.csv`)

| id | mode_type | vot | pce | occ | demand_file |
|---|---|---|---|---|---|
| 1 | `sov` | 20.49 | 1 | 1 | `sov_PM.csv` |
| 2 | `hov2` | 20.25 | 1 | 2 | `hov2_PM.csv` |
| 3 | `hov3` | 31.50 | 1 | 3.36 | `hov3_PM.csv` |
| 4 | `apv` | 30.00 | 1 | 1 | `apv_PM.csv` |
| 5 | `btrk` | 24.00 | 1 | 1 | `btrk_PM.csv` |
| 6 | `ltrk` | 32.00 | 1 | 1 | `ltrk_PM.csv` |
| 7 | `mtrk` | 47.00 | 2 | 1 | `mtrk_PM.csv` |
| 8 | `htrk` | 52.00 | 3 | 1 | `htrk_PM.csv` |

| | |
|---|---|
| `vot` | $/h, from [TT] r100–r114 × perception factors. `sov` is the PM-trip-weighted mean of VOT1 (2.3 × 2.25), VOT2 (7.2 × 2.25) and VOT3 (24 × 2.00); external trips are split 0.10 / 0.45 / 0.45 (r61–r63). |
| `pce` | medium 2, heavy 3: CMAP's vehicle equivalents ([TT], [A] p.122) |
| `occ` | HOV3+ 3.36 [G]; the others are definitional |

One `sov` class replaces CMAP's three VOT classes. This matters only on the 198 tolled links.

## 10. Worked example: link `3634` → `11223`

A freeway link leaving external zone 3634, at the north edge of the model area in Wisconsin. All values are the actual file values [m].

**1. Source rows**

| Field | Value | Field | Value |
|---|---|---|---|
| `ID` | 3634-11223 | `@speed` | 65 |
| `LENGTH` | 0.58 | `@ftime` | 0.535385 |
| `LANES` | 3 | `@emcap` | 2000 |
| `VDF` | 2 | `@toll` | 0 |
| `MODES` | `ASHThmlb` | `DATA1` | 4605.3213 |
| | | `TIMAU` | 0.521654 |

**2. `node.csv`**

| node_id | zone_id | x_coord | y_coord | node_type |
|---|---|---|---|---|
| 3634 | 3634 | −87.920880 | 42.966647 | centroid |
| 11223 | *blank* | −87.932119 | 42.965410 | road |

**3. `link.csv`**

| Column | How | Column | How |
|---|---|---|---|
| `link_id` | 3634 (row number) | `vdf_length_mi` | 0.58 |
| `from_node_id` | 3634 | `vdf_fftt` | 0.535385 = 0.58 / 65 × 60 |
| `to_node_id` | 11223 | `vdf_free_speed_mph` | 65.0 |
| `length` | 0.58 × 1609.344 = 933.42 | `free_speed` | 65 × 1.609344 = 104.6073 |
| `lanes` | 3 | `capacity` | 2000 (`cmap_emcap`) |
| `link_type` | 2 (freeway) | `hourly_link_capacity` | 6000 |
| `allowed_use` | `sov;hov2;hov3;apv;btrk;ltrk;mtrk;htrk` | `ref_volume` | 4605.3213 |
| `vdf_type/alpha/beta` | blank (replay step) | `ref_time`, `timau` | 0.521654 |

**fd2 check:**
- u2 = 0.75 × 2000 × 3 × 2 = 9,000, so v/u2 = 0.512.
- t = (1 + 0.15 × 0.512) × (0.535385 / 1.15) × [1 + 0.15 × (4605.32 / 9300)^8] = 0.502 min.
- `TIMAU` is 0.522 min. The −3.9 % gap is because CMAP's v counts trucks and buses as vehicle equivalents.

**4. Demand**: zone 3634 → 3636 (external → external, a through trip)

| File | Row | Source |
|---|---|---|
| `sov_PM.csv` | `3634,3636,402.734` | = 0.155 × mf8 (2,598.285) |
| `htrk_PM.csv` | `3634,3636,114.696` | = 0.103 × mf9 (1,113.551) |
| other modes | no row | mf417–457 and mf4–7 are internal trips only |

## 11. Gotchas

| Issue | What to know |
|---|---|
| `@speed` ≠ speed in `@ftime` | `@ftime` uses `@speed` rounded up to a bin [FT], so 741 links differ (`checks/ftime_vs_posted_speed.csv`). `@speed` is not written. |
| 0.75 on VDF 1–5 | [TOD] applies it to all of VDF 1–5, while [A] p.123 names arterials only. The conversion follows the code. |
| `/1.15` on freeways | applied inside fd2, not in `@ftime` |
| `VOLAU` in the shapefile | not a volume (median 3,648); use `DATA1` |
| `@toll` is per link | The per-mile rate in [A] T1 is the master-network field, converted before export; CMAP adds `@toll` unchanged as link cost [SOLA]. There are 198 tolled links: 188 VDF 7 (median $0.70) and 10 VDF 2 (median $0.535). |
| Connector capacity is 0 | VDF 6 and 7 have `@emcap = 0`. They get a 99,999 placeholder with α = 0 (`region.cmap.yaml > vdf > no_capacity_links`, CMAP only; NVTA uses 3,150 and SCAG its own file). This covers 7,452 links. |
| Zone links ≠ connectors | 32 road links (VDF 1, 2, 4) leave external zones 3633–3649 and keep `@emcap`. Connectors are found by VDF 6, not by touching a zone. |
| Toll links stay | They sit in series on the tollways; deleting them would drop 940 nodes and 1 zone from the connected network. |
| emmemat period tables | mf94–97 and mf14–18 are period 8, not PM |
| Trucks in veq | CMAP's tables are in vehicle equivalents; here they are vehicles plus `pce` |
| Floor 0.01 | drops 28–29 % of light and medium trucks and 12 % of heavy; not rescaled (first version) |
| Arterial delay | needs `@cycle` and `@gc`, which were not exported, so VDF 1 is −22 % |
| Base year | scenario 100 = 2019; `c25q4_200` (2025) has the same file structure |
| No pyogrio / pyproj | The built-in shapefile reader and reprojection are used; checked against pyproj to 0.0 m median difference. |
