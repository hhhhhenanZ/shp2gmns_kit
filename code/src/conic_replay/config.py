"""Constants for the analysis, built from the region file and the parameter tables.

The analysis modules import names from here. Each name is computed from the active
region (``CONIC_REPLAY_REGION``, set by the drivers), so nothing in the analysis is
specific to one network.

Prefer the resolved snapshot ``<output>/region.resolved.json``: it records the exact
configuration that produced the network being analysed.
"""

from __future__ import annotations

from .conic_vdf import CONNECTOR_RULE, converter_field_names, load_parameters, spiess_beta  # noqa: F401
from .region import MODES, Region

REGION = Region.load()
_PARAMS = load_parameters(REGION)

# ---- conical parameters ---------------------------------------------------------------
CONNECTOR_FTYPE = _PARAMS.connector_ftype
CONIC_ALPHA = _PARAMS.alpha_pooled                  # {ftype: alpha}, pooled
CONIC_ALPHA_BY_FT_AT = _PARAMS.alpha_by_ft_at       # {ftype: {atype: alpha}}
ALPHA_INHERITED_CELLS = _PARAMS.inherited_cells
PERIOD_FACTOR = _PARAMS.period_factor               # {period: E}


def conic_alpha(ftype, atype):
    return _PARAMS.alpha(ftype, atype)


# ---- field names --------------------------------------------------------------------
PERIODS = tuple(REGION.periods)
_KEY_MAP = {
    "vol": "volume", "vc": "vc_ratio", "vdf": "travel_time_ratio", "spd": "speed",
    "ffspd": "free_speed", "vmt": "vmt", "link_cap": "link_capacity",
    "lane_cap": "lane_capacity", "limit": "limit",
}
CUBE_FIELDS = {
    p: {short: REGION.cube_field(long, p) for short, long in _KEY_MAP.items()} for p in PERIODS
}
CUBE_MODE_FIELDS = {p: {m: REGION.mode_field(m, p) for m in MODES} for p in PERIODS}
TAPLITE_MODE_COLUMNS = {mode: f"mod_vol_{mode}" for mode in MODES}

# Region field -> the canonical column name the analysis modules use.
FACILITY_TYPE_COLUMN = converter_field_names().get("facility_type_field", "FTYPE")
CANONICAL_COLUMNS = {
    FACILITY_TYPE_COLUMN: "FTYPE",
    REGION.static_field("toll_group"): "TOLLGRP",
    REGION.static_field("jurisdiction"): "JUR",
    REGION.static_field("street_name"): "STREETNAME",
}

# ---- classification and labels ------------------------------------------------------
_cls = REGION.classification
LINK_TYPE_ATYPE_DIVISOR = int(_cls.get("link_type_divisor", 100))
DOCUMENTED_ATYPE_CODES = tuple(int(v) for v in _cls.get("documented_area_types", []))
FTYPE_LABEL = {int(k): str(v) for k, v in (_cls.get("facility_types") or {}).items()}
LIMIT_LABEL = {int(k): str(v) for k, v in (_cls.get("limit_codes") or {}).items()}
HOV_LIMIT_CODES = tuple(int(v) for v in _cls.get("hov_limit_codes", []))
CLOSED_LIMIT_CODE = int(_cls.get("closed_limit_code", -1))

# ---- analysis -----------------------------------------------------------------------
_ana = REGION.analysis
HOV3_OCCUPANCY_SENSITIVITY = tuple(float(v) for v in _ana.get("hov3_occupancy_sensitivity", []))
CORRIDORS = tuple((str(c["name"]), str(c["pattern"])) for c in (_ana.get("corridors") or []))

# ---- files the analysis reads -------------------------------------------------------
LINK_PERFORMANCE = "link_performance.csv"
SUMMARY_LOG = "summary_log_file.txt"
RUN_RECORD = "RUN_RECORD.json"
SETTINGS = "settings.csv"
MODE_TYPE = "mode_type.csv"
