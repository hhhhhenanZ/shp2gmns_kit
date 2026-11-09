# Gate run folders

One folder per region and scenario (e.g. `cmap_2019_pm/`, `scag_2050plan/`), outside this repository.
The folder is the evidence; this repository is the code.

    python code/run_gates.py --region region.cmap.yaml --run ../cmap_2019_pm

Steps: raw, convert, publish, demand, L0, L1, manifest. The demand step resumes where it
stopped; exit code 2 means run it again (`--steps demand L0 L1 manifest`).

```
<region>_<scenario>/
  README.md        one line: the level reached
  manifest.csv     path, bytes, sha256, source, script @ commit, date
  00_raw/          agency files, read-only; EXTERNAL.csv lists files too large to copy
  01_topology/     node.csv link.csv zone.csv L0_counts.csv
  02_demand/       demand_<class>_<period>.csv mode_type.csv L1_conservation.csv L1_class_map.csv
  03_supply/       capacity_lookup.csv link_vdf.csv L2_unmatched.csv            (next)
  04_assignment/   settings.yaml link_performance.csv L3_vmt_vht.csv           (next)
  05_counts/       counts_raw.csv L4_fit.csv
  06_congestion/   speed_obs.csv fd_fit_<ftype>.csv L5_speed_index.csv
  99_log/          worklog.md produced.csv rerun.md
  _work/           intermediate, rebuilt by run_gates.py, not in the manifest
```

Rules: every L file is written by a script from 00_raw and the level below; the script is
in the manifest. A level is stated in README.md only when every L file up to it exists and
was rerun. A gate that cannot be produced is BLOCKED, with what was requested from whom and when.

| Gate | Script | Identity |
|---|---|---|
| L0 | gates/gate_L0.py | disconnected zones = 0; unreachable positive-demand OD pairs by class (paths may not pass through other centroids) |
| L1 | gates/gate_L1.py | sum_j Q_ij = P_i, sum_i Q_ij = A_j, sum Q = source total, by class |
| L2 | gates/gate_L2.py | capacity and VDF with source; time at CMAP volume vs timau |
| L3 | gates/gate_L3.py | VMT, VHT, VHD by facility type, model / CMAP |
| L4-L6 not produced | gates/gate_status.py | one-line file: status, reason, requested from whom and when |
| manifest | gates/make_manifest.py | sha256 of every file |

## Export to the repository

`--steps export` copies the small evidence files of a run folder into `gate_runs/<run folder>/`
(README, manifest, every L file, settings, capacity_lookup, zone_split, 99_log/*.md, rerun_compare.csv).
Large data files stay in the run folder; their sha256 is in manifest.csv.
