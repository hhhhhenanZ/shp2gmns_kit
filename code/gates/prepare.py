"""Steps before the gates: 00_raw, conversion, and the standard topology and demand files.

raw      copy the agency files named in ``gates > raw`` of the region file into 00_raw/
         (read-only); files marked ``copy: false`` are too large to copy and are listed in
         00_raw/EXTERNAL.csv with their path and sha256 instead.
convert  unpack the network files from 00_raw, write _work/region.run.yaml (the region file
         with its inputs pointed at 00_raw and its output at _work/convert), and run
         code/main_convert.py on it. The conversion code is the kit's, unchanged.
publish  copy the converted network and demand into 01_topology/ and 02_demand/ under the
         standard names: node.csv, link.csv, zone.csv; demand_<class>_<period>.csv, mode_type.csv.
demand   write the trip tables straight into 02_demand/, one class at a time, resumable: a class
         whose file is complete is skipped, so the step can be repeated until all are written.
         The conversion itself runs with --skip-demand.
"""

from __future__ import annotations

import copy
import os
import tempfile
import time
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .common import KIT_ROOT, folder, kit_path, load_region, record, sha256, worklog, write_csv

SCRIPT = "code/gates/prepare.py"


def raw_entries(region_file: Path) -> dict:
    return load_region(region_file)["gates"]["raw"]


def raw_location(run: Path, region_file: Path, entry: dict) -> Path:
    src = kit_path(region_file, entry["file"])
    return run / "00_raw" / src.name if entry.get("copy", True) else src


def step_raw(region_file: Path, run: Path) -> None:
    raw = folder(run, "raw")
    external = []
    for role, entry in raw_entries(region_file).items():
        src = kit_path(region_file, entry["file"])
        if not src.exists():
            raise SystemExit(f"raw file missing: {src}")
        if entry.get("copy", True):
            dst = raw / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                os.chmod(dst, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                print(f"  copied {src.name}")
        else:
            external.append({"role": role, "file": src.name, "original_path": entry["file"],
                             "bytes": src.stat().st_size, "sha256": sha256(src),
                             "source": entry.get("source", "")})
    if external:
        write_csv(pd.DataFrame(external), raw / "EXTERNAL.csv")
    worklog(run, "raw: agency files placed in 00_raw (large ones listed in 00_raw/EXTERNAL.csv)")


def _absolute(value, base: Path):
    """Turn every relative path in the region file into an absolute one."""
    if isinstance(value, dict):
        return {k: _absolute(v, base) for k, v in value.items()}
    if isinstance(value, list):
        return [_absolute(v, base) for v in value]
    if isinstance(value, str) and (value.startswith("data/") or value.startswith("../")):
        return str((base / value).resolve())
    return value


def step_convert(region_file: Path, run: Path, period: str) -> Path:
    work = folder(run, "work")
    raw = load_region(region_file)
    g = raw["gates"]
    unpacked = work / "unpacked"
    for role in ("network_shapefile", "network_emme"):
        entry = g["raw"][role]
        z = raw_location(run, region_file, entry)
        dst = unpacked / entry["unpack_to"]
        dst.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if not (dst / name).exists():
                    zf.extract(name, dst)
    run_cfg = _absolute(copy.deepcopy(raw), region_file.parent)
    for key, target in g["inputs"].items():                  # input > key > period
        run_cfg["input"][key] = {period: str((unpacked / target).resolve())}
    run_cfg["demand"]["emmemat_zip"] = str(raw_location(run, region_file, g["raw"]["demand_matrices"]))
    run_cfg["output"]["root"] = str((work / "convert").resolve())
    run_file = work / "region.run.yaml"
    with open(run_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(run_cfg, f, sort_keys=False, allow_unicode=True)
    cmd = [sys.executable, str(KIT_ROOT / "code" / "main_convert.py"),
           "--region", str(run_file), "--periods", period, "--skip-demand"]
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    worklog(run, f"convert: main_convert.py on _work/region.run.yaml, period {period}")
    return work / "convert"


def step_publish(region_file: Path, run: Path, period: str) -> None:
    conv = run / "_work" / "convert"
    g = load_region(region_file)["gates"]
    topo, dem = folder(run, "topology"), folder(run, "demand")
    node = pd.read_csv(conv / "network" / period / "node.csv", encoding="utf-8-sig")
    link = pd.read_csv(conv / "network" / period / "link.csv", encoding="utf-8-sig", low_memory=False)
    write_csv(node, topo / "node.csv")
    write_csv(link, topo / "link.csv")
    lo, hi = g["external_zones"]
    zone = node[node.zone_id.fillna(0) > 0][["zone_id", "node_id", "x_coord", "y_coord"]].copy()
    zone["zone_id"] = zone.zone_id.astype(int)
    zone["external"] = zone.zone_id.between(lo, hi).astype(int)
    write_csv(zone, topo / "zone.csv")
    record(run, [topo / "node.csv", topo / "link.csv", topo / "zone.csv"], SCRIPT,
           "_work/convert (main_convert.py from 00_raw)")
    worklog(run, "publish: 01_topology/{node,link,zone}.csv")


def step_demand(region_file: Path, run: Path, period: str, budget_s: float = 140) -> bool:
    """Write 02_demand/demand_<class>_<period>.csv; return True when every class is written."""
    sys.path.insert(0, str(KIT_ROOT / "code" / "src"))
    from cmap_emme.demand import EmxReader, build_tables, sov_vot

    t0 = time.time()
    cfg = load_region(region_file)
    dcfg, g = cfg["demand"], cfg["gates"]
    dem = folder(run, "demand")
    floor = float(dcfg["min_volume"])
    emx = EmxReader(raw_location(run, region_file, g["raw"]["demand_matrices"]), int(dcfg["zones"]))
    tables, notes = build_tables(dcfg, period, emx)
    done_all = True
    for m, mat in tables.items():
        dst = dem / f"demand_{m}_{period}.csv"
        flag = dem / f".{dst.name}.done"
        if flag.exists():
            continue
        if time.time() - t0 > budget_s / 3:
            done_all = False
            print(f"  time budget reached; run the demand step again to continue ({m} next)")
            break
        o, d = np.nonzero(mat > floor)
        frame = pd.DataFrame({"o_zone_id": o + 1, "d_zone_id": d + 1, "volume": mat[o, d]})
        # write on the local disk first, then copy: much faster than many small writes
        # to a network or mounted folder
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / dst.name
            frame.to_csv(tmp, index=False, float_format="%.9g", encoding="utf-8")
            shutil.copyfile(tmp, dst)
        flag.write_text("ok")
        record(run, [dst], SCRIPT, f"00_raw demand matrices: {notes[m]}; threshold {floor}")
        print(f"  {m}: {len(frame):,} cells, {frame.volume.sum():,.1f} trips")
    if done_all:
        vot = round(sov_vot(dcfg, period, emx), 2)
        mt = pd.DataFrame([{"mode_type_id": i, "mode_type": m["mode_type"], "name": m["name"],
                            "vot": vot if m["vot"] == "weighted" else m["vot"], "pce": m["pce"],
                            "occ": m["occ"], "demand_file": f"demand_{m['mode_type']}_{period}.csv"}
                           for i, m in enumerate(dcfg["mode_types"], start=1)])
        write_csv(mt, dem / "mode_type.csv")
        record(run, [dem / "mode_type.csv"], SCRIPT, "region file demand > mode_types; SOV VOT weighted [C]")
        worklog(run, f"demand: all classes written to 02_demand, threshold {floor}")
    return done_all
