"""Build cmap_report_data.js for CMAP_report.html from the converted PM network.

Reads ../network/PM/link.csv, ../network/link_geometry.csv, ../network/PM/node.csv.
Two directions of a link are merged into one feature (A->B and B->A values kept).
Centroid connectors (VDF 6) are left out of the map. Geometry is simplified to ~5 m
(Douglas-Peucker) and rounded to 5 decimals. Run: python make_map_data.py
"""
import json, re
import numpy as np, pandas as pd

L = pd.read_csv('../network/PM/link.csv', encoding='utf-8-sig')
G = pd.read_csv('../network/link_geometry.csv', encoding='utf-8-sig').set_index('link_id')
N = pd.read_csv('../network/PM/node.csv', encoding='utf-8-sig')

def dp(pts, tol):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]; ab = b - a; n = np.hypot(*ab)
    d = (np.abs(np.cross(ab, pts - a)) / n) if n > 0 else np.hypot(*(pts - a).T)
    i = int(np.argmax(d))
    if d[i] > tol: return np.vstack([dp(pts[:i+1], tol)[:-1], dp(pts[i:], tol)])
    return np.vstack([a, b])

L = L[L.vdf_code != 6].copy()
cap_vdf = np.where(L.vdf_code == 8, 1.0, 0.75) * L.capacity * L.lanes * 2   # CMAP ul2, PM
L['vc'] = np.where(L.capacity_source == 'cmap_emcap', L.ref_volume / cap_vdf, np.nan)
L['tr'] = L.ref_time / L.vdf_fftt
L['key'] = [tuple(sorted(p)) for p in zip(L.from_node_id, L.to_node_id)]
feats = []
for key, g in L.groupby('key', sort=False):
    g = g.sort_values('from_node_id')
    ab = g.iloc[0]; ba = g.iloc[1] if len(g) > 1 else None
    pts = np.array([[float(x) for x in p.split()] for p in
                    re.findall(r'-?\d+\.\d+ -?\d+\.\d+', G.at[int(ab.link_id), 'geometry'])])
    pts = dp(pts, 0.00005)
    r = lambda v: None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 2)
    feats.append([np.round(pts, 5).tolist(), int(ab.vdf_code),
                  ab.org_link_id, int(ab.lanes), r(ab.ref_volume), r(ab.tr), r(ab.vc), r(ab.capacity) if ab.capacity < 99999 else 0,
                  None if ba is None else ba.org_link_id, None if ba is None else int(ba.lanes),
                  None if ba is None else r(ba.ref_volume), None if ba is None else r(ba.tr),
                  None if ba is None else r(ba.vc), round(float(ab.toll), 2)])
air = {123,124,125,126,127,129,130,494,1733,1734,1969,2907}
zones = []
for _, z in N[N.node_type == 'centroid'].iterrows():
    k = int(z.node_id)
    t = 'airport' if k in air else 'external' if k >= 3633 else 'cbd' if k <= 47 else 'internal'
    zones.append([k, round(z.x_coord, 5), round(z.y_coord, 5), t])
out = {'fields': ['coords', 'vdf', 'id_ab', 'lanes_ab', 'vol_ab', 'tr_ab', 'vc_ab', 'cap_vphpl',
                  'id_ba', 'lanes_ba', 'vol_ba', 'tr_ba', 'vc_ba', 'toll'],
       'links': feats, 'zones': zones}
with open('cmap_report_data.js', 'w') as f:
    f.write('const CMAP_DATA = ' + json.dumps(out, separators=(',', ':')) + ';\n')
print(len(feats), 'features;', len(zones), 'zones')
