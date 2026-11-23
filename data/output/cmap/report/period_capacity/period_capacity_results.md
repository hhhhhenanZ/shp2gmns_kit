# CMAP period capacity (ul2) by period: results (Nov 23, 2026)

Run: see `README.md` in this folder.

## 1. CMAP's rule

Source: CMAP model code `TOD_network_prep.py` lines 149-158 (hours) and 176-221 (ul2); `Ftime_capacity.py` (@emcap); period clock times from `c25q4_100/data_user_guide.html`. Links to the code: `data/input/cmap/docs/cmap_code/README.md`.

- Hourly capacity of a link = factor x @emcap x lanes.
- Period capacity ul2 = factor x @emcap x lanes x hours.
- factor = 0.75 for vdf 1-5 (arterials, freeways, expressways, ramps); 1.00 for vdf 8 (metered ramps, @emcap = 720); none for vdf 6 (connectors) and 7 (toll links), where ul2 = 1.
- **The 0.75 factor is the same in all 8 periods.** It does not change by period. Only the hours change. (The code comment: "vdf=1,5 at 75% and vdf=8 at 100%".) CMAP's code calls 0.75 x @emcap (LOS E) the LOS D capacity used in its volume-delay functions (TOD_network_prep.py L177-179).
- @emcap (veh/h/lane, LOS E) is computed by Ftime_capacity.py on each period's network, so it is read from attribs_pX for each period. It is the same in all periods on most links, but differs on 1,270 links (1,268 arterials, 2 expressways), 996 of them where the lane count also changes: the arterial parking and lane adjustments depend on the period's lanes and parking. vdf 6 and 7 get no @emcap (0). Freeway: 1500 + 100 (speed >= 50) + 200/100/100 for lane width >= 10/11/12 ft, so 2,000 on a 12-ft, 55+ mph freeway.

| Period | Clock time | Clock hours | Hours in ul2 | ul2 / (@emcap x lanes), vdf 1-5 | Same, vdf 8 |
|---|---|---|---|---|---|
| 1 | 8pm-6am | 10 | **5** | 3.75 | 5 |
| 2 | 6-7am | 1 | 1 | 0.75 | 1 |
| 3 | 7-9am (AM peak) | 2 | 2 | 1.50 | 2 |
| 4 | 9-10am | 1 | 1 | 0.75 | 1 |
| 5 | 10am-2pm | 4 | 4 | 3.00 | 4 |
| 6 | 2-4pm | 2 | 2 | 1.50 | 2 |
| 7 | 4-6pm (PM peak) | 2 | 2 | 1.50 | 2 |
| 8 | 6-8pm | 2 | 2 | 1.50 | 2 |

Period 1 covers 10 clock hours but CMAP sets it to 5 ("set period 1 == 5 hours", code comment).

## 2. Check against CMAP's networks

`ul2` (Data2 in `network_p1..p8.txt`) recomputed from the rule on every capacity link (vdf 1-5, 8) in every period: **match on 100 %** of link-periods (0 mismatches). Example 21416-21403 (freeway, 4 lanes, @emcap 2,000): ul2 = 30,000 / 6,000 / 12,000 / 6,000 / 24,000 / 12,000 / 12,000 / 12,000 for p1-p8.

**Lanes change by period on 1,033 links** (`cmap_links_lanes_vary_by_period.csv`): peak-period parking bans (e.g. 2 lanes off-peak, 3 lanes in p3 or p7) and reversible links that exist only in some periods (blank = link absent).

## 3. Outputs

- `cmap_period_capacity_rules.csv`: 8 periods x 6 facility types; hours, factor, formula, ratio, link counts, @emcap range, check share, source.
- `cmap_link_period_capacity_c25q4_100.csv` (not in the repository; about 48 MB; written by the script): one row per link and period (440,054 rows): lanes, @emcap, factor, hourly lane and link capacity, ul2 recomputed and from Emme, ul1, @vadt, timau.
- `cmap_links_lanes_vary_by_period.csv`.
