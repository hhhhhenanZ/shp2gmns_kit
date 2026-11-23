# CMAP period capacity (ul2) by period

**Purpose.** Record how CMAP computes link capacity for each of its 8 time periods, from CMAP's own code, and check it on every link of CMAP's own period networks (scenario c25q4_100).
**Results and discussion.** `period_capacity_results.md`.

## 1. Inputs

CMAP's files are not in this repository. Download them from CMAP:

- **CMAP Travel Demand Model Data, c25q4** (CMAP Data Hub): https://datahub.cmap.illinois.gov/documents/a14d641dbe184704ab597479b103986c/explore. Take the scenario `c25q4_100` package.
- **CMAP model code** (read only, not run): links in [`data/input/cmap/docs/cmap_code/README.md`](../../../../input/cmap/docs/cmap_code/README.md) (CMAP-REPOS/cmap_trip-based_model, commit e52b318).

| CMAP file | What is used | Where to put it |
|---|---|---|
| `emmenet_highway_c25q4_100.zip` (in the c25q4_100 package) | `network_p1.txt` ... `network_p8.txt`: link section (i, j, length in miles, modes, type, lanes, vdf, Data1 = ul1, Data2 = ul2, Data3 = ul3). `attribs_p1.txt` ... `attribs_p8.txt`: @emcap, @vadt, timau | Leave it zipped. Put it in `../c25q4_100/` (one level above the kit, as for `emmemat_c25q4_100.zip`) or in `data/input/cmap/network/`. The script reads the zip directly. |
| `data_user_guide.html` (in the c25q4_100 package) | Clock times of periods 1-8; "period link capacity = @emcap x lanes x hours" | `data/input/cmap/docs/` (only for reading) |
| `TOD_network_prep.py` (CMAP model code) | Hours per period (lines 149-158); ul2 rule (lines 176-221); ul2 = 1 default (lines 186-200) | Not needed to run |
| `Ftime_capacity.py` (CMAP model code) | How @emcap is computed (freeway lines 108-118; arterial lines 245-337; ramps lines 380-418) | Not needed to run |

## 2. Code

`period_capacity.py` (this folder). Run time about 1 min. From the kit root:

```
python data/output/cmap/report/period_capacity/period_capacity.py [zip_or_folder] [out_dir]
```

- `zip_or_folder` (optional): path to `emmenet_highway_c25q4_100.zip`, or to a folder with its 16 unzipped files. Without it, the script looks in `../c25q4_100/` and then `data/input/cmap/network/`, and stops with a download message if the zip is not found.
- `out_dir` (optional): default is this folder.

The script:
1. Reads the links of each period network and joins @emcap, @vadt and timau from that period's attribs file.
2. Applies CMAP's rule and compares it with CMAP's ul2.
3. Writes the three tables below. The per-link table (about 48 MB) is in `.gitignore`.

## 3. CMAP's rule (summary)

- Hourly link capacity = factor x @emcap x lanes.
- Period capacity ul2 = factor x @emcap x lanes x hours.
- factor:
  - 0.75 for vdf 1-5. CMAP's code comment calls this the LOS D capacity used in its volume-delay functions.
  - 1.00 for vdf 8 (metered ramps).
  - The factor is the same in all 8 periods.
- hours: p1 5 (the clock period is 10 h), p2 1, p3 2, p4 1, p5 4, p6 2, p7 2, p8 2.
- vdf 6 (zone connectors) and vdf 7 (toll links):
  - Their link time does not depend on volume (fd6 = 3 x length, with length in miles and time in minutes, i.e. 3 min/mi = 20 mph; fd7 = ul1, a fixed time in minutes).
  - @emcap is never computed for them, so it stays 0.
  - ul2 keeps its default value of 1.

## 4. Outputs and field names

### 4.1 `cmap_period_capacity_rules.csv`

One row per period x facility type (vdf 1, 2, 3, 4, 5, 8): 48 rows.

| Field | Meaning |
|---|---|
| timeperiod | CMAP period 1-8 |
| period_name | Short name (overnight, AM peak, PM peak, ...) |
| period_clock | Clock time from the data user guide |
| clock_hours | Real length of the period (h) |
| model_hours | Hours CMAP uses in ul2 (p1 = 5, not 10) |
| vdf, facility | CMAP volume-delay function code and its name |
| cap_factor | 0.75 (vdf 1-5) or 1.00 (vdf 8) |
| hourly_cap_formula | Text of the hourly formula |
| period_cap_formula | Text of the ul2 formula for this period |
| period_to_hourly_ratio | cap_factor x model_hours = ul2 / (@emcap x lanes) |
| period_cap_per_lane_if_emcap2000 | ul2 per lane for @emcap = 2,000 (a 12-ft, 55+ mph freeway) |
| n_links | Links of this vdf in this period's network |
| lane_miles | Sum of lanes x length (mi) |
| emcap_median, emcap_min, emcap_max | @emcap over these links (veh/h/lane) |
| hourly_cap_link_median | Median over these links of cap_factor x @emcap x lanes (veh/h) |
| ul2_median | Median of CMAP's ul2 (Data2 of network_pX) over these links (veh per period) |
| ul2_match_share | Share of links where the recomputed ul2 equals CMAP's ul2 within 0.5 veh + 0.01 % (CMAP stores 2 decimals) |
| source | Code files and lines |

### 4.2 `cmap_link_period_capacity_c25q4_100.csv` (written by the script; not in the repository)

One row per link x period: 440,054 rows. vdf 6 and 7 links are included, with empty capacity fields.

| Field | Meaning |
|---|---|
| i_node, j_node | CMAP node ids (same keys as the CMAP class-volume file) |
| timeperiod, period_clock | Period 1-8 and its clock time |
| clock_hours, model_hours | Real hours, and hours used in ul2 |
| vdf, link_type | CMAP vdf code; CMAP link type (network_pX "Typ") |
| length_mi | Link length (mi) |
| lanes | Lanes in this period's network (can change by period) |
| emcap_vphpl | @emcap for this period (veh/h/lane, LOS E); 0 for vdf 6, 7 |
| cap_factor | 0.75 / 1.00 / empty |
| hourly_cap_lane_vphpl | cap_factor x emcap_vphpl |
| hourly_cap_link_vph | cap_factor x emcap_vphpl x lanes |
| period_cap_ratio_to_hourly | model_hours x cap_factor |
| period_cap_calc_veh | hourly_cap_link_vph x model_hours (our recomputed ul2) |
| ul2_emme | CMAP's ul2 (network_pX Data2); 1 for vdf 6, 7 |
| ul2_check_abs_diff | abs(period_cap_calc_veh - ul2_emme) |
| ul2_match | 1 if within tolerance, 0 if not, empty for vdf 6, 7 |
| ul1_ftime_min | CMAP's ul1 = free-flow time (min) (network_pX Data1) |
| vadt_period_veh | CMAP's assigned volume in the period, vehicles (attribs_pX @vadt; no buses) |
| timau_min | CMAP's final congested link time (min) (attribs_pX timau) |

### 4.3 `cmap_links_lanes_vary_by_period.csv`

Links (vdf 1-5, 8) whose lane count is not the same in all 8 period networks: 1,033 links.

| Field | Meaning |
|---|---|
| i_node, j_node | CMAP node ids |
| lanes_p1 ... lanes_p8 | Lanes in network_p1 ... network_p8; blank = the link is not in that period's network (e.g. a reversible link) |

The data show only that the lanes change. CMAP does not give the reason; peak parking bans and reversible lanes are likely reasons.

## 5. Checks

- ul2 recomputed = CMAP ul2 on 100 % of capacity link-periods (0 mismatches).
- Link 21416-21403 (freeway, 4 lanes, @emcap 2,000): ul2 = 30,000 / 6,000 / 12,000 / 6,000 / 24,000 / 12,000 / 12,000 / 12,000 for p1-p8.
- Link 8609-8612 (arterial): 2 lanes and @emcap 1,376.55 off-peak; 3 lanes and @emcap 1,449 in p3 and p7. p7 ul2 = 0.75 x 1,449 x 3 x 2 = 6,520.5 = CMAP.

## 6. Notes

- @emcap is read for each period. It changes by period on 1,270 links (1,268 arterials, 2 expressways), because the arterial lane and parking adjustments in Ftime_capacity.py depend on the period's lanes and parking.
