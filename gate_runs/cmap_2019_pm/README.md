Level reached: L1 (L0 and L1 rerun from 00_raw in a clean folder, all files identical; independent rerun pending). L2 and L3 produced, not passed. See 99_log/rerun.md.

CMAP c25q4 scenario 100 (2019), PM 4-6 pm, 8 classes as CMAP defines them.
Built by `python code/run_gates.py --region region.cmap.yaml --run ../cmap_2019_pm` in shp2gmns_replay_kit.

| Gate | File | Result |
|---|---|---|
| L0 | 01_topology/L0_counts.csv | 20,190 nodes, 55,005 links, 3,649 zones (17 external) = 00_raw; 0 disconnected zones; 0 unreachable positive-demand OD pairs in every class |
| L1 | 02_demand/L1_conservation.csv, L1_class_map.csv | source 3,527,729 = written 3,481,077 + removed below threshold 46,653; nothing else lost; 17 external zones kept |
| L2 | 03_supply/link.csv, link_vdf.csv, capacity_lookup.csv, L2_unmatched.csv, L2_replay.csv | 0 unmatched links; TAPLite uses BPR (0.15, 4) for now, CMAP fd1-fd8 kept in cmap_* columns. At CMAP's own volume, road VHT = 0.70 x timau with BPR and 0.73 x timau with CMAP's fd1-fd8: the functions are not the main gap (see below) |
| L3 | 04_assignment/settings.yaml, link_performance.csv, L3_vmt_vht.csv | 5 classes (car = sov+hov2+hov3+apv, merged for the 8 GB limit, see settings.yaml), BPR, gap 0.18 % after 9 iterations, peak memory 4.8 GB. Road links, model / CMAP: VMT 0.92, VHT 0.66 (657,375 / 998,112), VHD 0.11 (33,952 / 314,283); link volume R2 0.93, slope 0.96 |
| L4 | 05_counts/L4_fit.csv | BLOCKED, question open: 2023 IDOT AADT is in hand and already matched to the City of Chicago network: 26,312 links (count year >= 2022), converted to 4-6 pm directional volume as AADT x w x h x D with IDOT factors (Dataset/04_aadt/idot_aadt_pipeline, aadt_pm2h_by_link.csv; method AADT_to_PM_volume_method.md); used for the 2023 city model (R5a, VMT ratio 1.04). Not used here: this run is 2019 on CMAP links. Asked whether the 2023 counts may be used here |
| L5 | - | BLOCKED, question open: no 2019 speed data in hand. An S3 / QVDF fit on 2023 INRIX TMC speeds exists for the City of Chicago network (PM, clear and weather cases; 6_final_data2023/qvdf_chicago1104_strict_dry, copy in Dataset/07_qvdf_cbi). Asked whether the 2023 fit may be used for L5 here, with 2019 (model) and 2023 (speeds) stated as separate scopes and only city links checked |
| L6 | 07_transit/L6_station_volume.csv | BLOCKED: transit network not considered for now; highway network and highway demand only |
| R | manifest.csv, 99_log/rerun.md | author rerun 2026-11-09: L0-L2 and all inputs identical (sha256); rerun by a second person pending |

Threshold `min_volume = 0.01` veh per 2 h (region.cmap.yaml). CMAP's truck tables spread their
trips over almost every one of the 13.3 M OD cells, mostly in amounts of about 0.001 vehicle.
Cutting cells at 0.01 removes about 12 M cells per truck class, which carry 28 % of light and
29 % of medium trucks (3.5 % B-plate, 12 % heavy); car tables are concentrated, so cars lose
under 0.01 %. Without the cut the demand files are 1.3 GB and TAPLite does not fit in 8 GB.
For the full dataset set `min_volume: 0` and rerun.

L2 replay. With volume fixed at DATA1, CMAP's own fd1-fd8 give only 0.73 of CMAP's road VHT,
and BPR gives 0.70. So replacing BPR by fd1-fd8 closes about 3 points. The rest is in what
CMAP puts into v and t: trucks as vehicle equivalents (x2, x3) and the bus preload in v, and
signal delay on arterials (fd1, fd3), which needs @cycle and @gc (not in the exported files).

Bus preload: not included for now; this run covers the road network only. CMAP adds bus
vehicle equivalents to v in fd1-fd5. They are not in the exported files and are computed from
the transit network (bus.itinerary_4: 60 / headway x 2 x 3 per bus line on each link).

Reference volume. DATA1 (= @vadt) is in vehicles and already includes buses: @vadt = @avauv +
@avh2v + @avh3v + @avbqv + @avlqv + @avmqv/2 + @avhqv/3 + @busveq/3 [G, data_user_guide.html].
CMAP's functions use vehicle equivalents (medium trucks x2, heavy x3, buses x3), so DATA1 is
smaller than the v in fd1-fd8. This is part of why fd1-fd8 at DATA1 give 0.73 of timau. The
per-class link volumes (@avmqv, @avhqv, @busveq) are not exported, so v cannot be rebuilt exactly.

L3 reading. Volumes match CMAP (R2 0.93) while VHT is 0.66 and VHD 0.11: the gap is in link
times, not in demand. L2 shows where: at CMAP's own volume, BPR gives 0.70 of CMAP's VHT and
CMAP's fd1-fd8 give 0.73; the rest is arterial signal delay (@cycle, @gc) and CMAP's use of
vehicle equivalents in v, neither of which is in the exported files.
