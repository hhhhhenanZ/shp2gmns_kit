# CMAP model code used by the conversion

The CMAP converter (`code/src/cmap_emme/`) follows these 7 files from CMAP's public model repository,
[CMAP-REPOS/cmap_trip-based_model](https://github.com/CMAP-REPOS/cmap_trip-based_model), commit `e52b318`.
That repository has no license file, so the files are not copied here. Download them from the links below and
put them in this folder.

| File | What the conversion takes from it |
|---|---|
| [Database/macros/Ftime_capacity.py](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/macros/Ftime_capacity.py) | `@ftime`, `@emcap`: free-speed bins, meter delay |
| [Database/macros/TOD_network_prep.py](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/macros/TOD_network_prep.py) | VDF capacity ul2 = 0.75 x `@emcap` x lanes x hours on VDF 1-5 |
| [Database/data/vdf_tod.in](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/data/vdf_tod.in) | Emme functions fd1-fd8 as run |
| [Database/macros/ttables.mac](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/macros/ttables.mac) | how the PM (period 7) trip tables are built |
| [Database/data/tod_factors.p7](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/data/tod_factors.p7) | PM time-of-day factors for trucks and externals |
| [Database/data/tod_flags.in](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/data/tod_flags.in) | CBD and airport zone flags |
| [Database/macros/SOLA_assignment.py](https://github.com/CMAP-REPOS/cmap_trip-based_model/blob/e52b3185920b139fb77983a74458b05fa4923890/Database/macros/SOLA_assignment.py) | `@toll` added unchanged as link cost |

The values taken from them are written into `region.cmap.yaml` with their line references, so the conversion
runs without these files. `code/check_inputs.py` only checks that this folder is not empty.
