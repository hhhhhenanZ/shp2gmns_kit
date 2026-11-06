"""Conic overlay: turn a converted QVDF ``link.csv`` into the Cube conical configuration.

Applied after conversion. It reads a ``link.csv`` produced by the original converter
and rewrites five columns; every other column passes through byte-for-byte.

==============  ============================================  ======================
column          conic value                                   replaces
==============  ============================================  ======================
``vdf_type``    1 for road links, 0 for connectors            2 (QVDF)
``vdf_alpha``   alpha for the link's facility x area type     QVDF alpha
``vdf_beta``    Spiess beta = (2a-1)/(2a-2); 1 on connectors  QVDF beta
``vdf_plf``     E / H for the period                          per-link PLF
``ref_volume``  Cube's assigned volume                        0
``name``        street name, placeholder blanked (new)        --
==============  ============================================  ======================

TAPlite reads ``vdf_alpha`` / ``vdf_beta`` as the conical a / b when ``conic_a`` /
``conic_b`` are absent, so no new column names are introduced. ``vdf_type`` is the
discriminator between the QVDF and conic folders.

All parameters arrive in :class:`ConicParameters`, built from the region file and the
derived parameter tables. Nothing about any particular network is written here.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# ---- rules that hold for any Cube conical replay ------------------------------------

# Connectors get BPR with alpha = 0, which is exactly t = t0 at every volume. No conical
# (alpha, beta) returns 1: alpha = 0 gives 2, because the leading "2 +" survives.
# beta = 1 rather than anything else: beta is read by kernel paths that never check alpha
# first, and beta < 1 with zero volume yields NaN. 1 is safe everywhere.
CONNECTOR_RULE = {"vdf_type": 0, "vdf_alpha": 0.0, "vdf_beta": 1.0}
CONIC_VDF_TYPE = 1
OVERLAY_COLUMNS = ("vdf_type", "vdf_alpha", "vdf_beta", "vdf_plf", "ref_volume")
NAME_COLUMN = "name"

FIELDNAMECONFIG = (
    Path(__file__).resolve().parents[1] / "dtalite4cube" / "cube2gmns" / "fieldnameconfig.py"
)


def converter_field_names() -> dict:
    """Shapefile field names the original converter uses, read from its own config.

    Loaded by file path: ``fieldnameconfig.py`` is plain constants, while importing it
    through its package would pull in the whole converter and geopandas. Reading it
    here keeps one source of truth for names such as the facility-type field.
    """
    spec = importlib.util.spec_from_file_location("_fieldnameconfig", FIELDNAMECONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.cube_base_link_mapping)


def spiess_beta(alpha: float) -> float:
    """Spiess' conical beta. This constraint forces t == t0 at zero volume."""
    if alpha <= 1.0:
        raise ValueError(f"Conic alpha must exceed 1; got {alpha!r}")
    return (2.0 * alpha - 1.0) / (2.0 * alpha - 2.0)


@dataclass
class ConicParameters:
    alpha_by_ft_at: dict            # {ftype: {atype: alpha}}
    alpha_pooled: dict              # {ftype: alpha}
    period_factor: dict             # {period: E}
    inherited_cells: dict = field(default_factory=dict)   # {(ftype, atype): reason}
    connector_ftype: int = 0
    link_type_divisor: int = 100
    facility_type_column: str = "FTYPE"
    street_name_column: str = "STREETNAME"
    street_name_placeholder: str = "0"

    def alpha(self, ftype, atype) -> tuple[float, str]:
        """Alpha for one link and where it came from. Refuses to guess."""
        ftype, atype = int(ftype), int(atype)
        if ftype not in self.alpha_pooled:
            raise ValueError(f"No conic alpha for facility type {ftype}; refusing to default")
        cells = self.alpha_by_ft_at.get(ftype, {})
        if atype in cells:
            return float(cells[atype]), "cell"
        return float(self.alpha_pooled[ftype]), "pooled_ftype"

    def plf(self, period: str, period_hours: float) -> float:
        """Cube's period basis as vdf_plf.

        TAPlite: x = volume / (lane_capacity x lanes x vdf_plf x H)
        Cube:    x = volume / (lane_capacity x lanes x E)
        Equal denominators need vdf_plf = E / H, with H the hours TAPlite assigns.
        """
        key = str(period).lower()
        if key not in self.period_factor:
            raise ValueError(f"No period factor E for period {period!r}")
        if not period_hours or period_hours <= 0:
            raise ValueError(f"period_hours must be positive; got {period_hours!r}")
        return float(self.period_factor[key]) / float(period_hours)


def load_parameters(region) -> ConicParameters:
    """Build :class:`ConicParameters` from a region and its parameter tables."""
    alpha_path = region.alpha_table_path
    factor_path = region.period_factor_path
    for path, what in ((alpha_path, "alpha table"), (factor_path, "period factor table")):
        if not path.is_file():
            raise FileNotFoundError(
                f"{what} not found: {path}. Run main_convert.py, which derives it, "
                "or set conic > alpha_table to a published CSV."
            )

    table = pd.read_csv(alpha_path)
    for column in ("FTYPE", "ATYPE", "alpha"):
        if column not in table.columns:
            raise KeyError(f"{alpha_path.name} needs a '{column}' column")
    by_cell: dict = {}
    for row in table.itertuples(index=False):
        by_cell.setdefault(int(row.FTYPE), {})[int(row.ATYPE)] = float(row.alpha)
    if "pooled_ftype_alpha" in table.columns:
        pooled = table.groupby("FTYPE")["pooled_ftype_alpha"].first()
    else:
        pooled = table.groupby("FTYPE")["alpha"].mean()
    pooled = {int(k): float(v) for k, v in pooled.items()}

    inherited = {}
    if "identified" in table.columns:
        flags = table["identified"].astype(str).str.lower().isin(("true", "1", "yes"))
        for row, ok in zip(table.itertuples(index=False), flags):
            if not ok:
                reason = getattr(row, "reason", "") or "cell not identified"
                inherited[(int(row.FTYPE), int(row.ATYPE))] = str(reason)

    factors = pd.read_csv(factor_path)
    period_factor = {str(p).lower(): float(e) for p, e in zip(factors["period"], factors["E"])}

    conic = region.conic
    fields = converter_field_names()
    return ConicParameters(
        alpha_by_ft_at=by_cell,
        alpha_pooled=pooled,
        period_factor=period_factor,
        inherited_cells=inherited,
        connector_ftype=int(conic.get("connector_ftype", 0)),
        link_type_divisor=int(region.classification.get("link_type_divisor", 100)),
        facility_type_column=str(fields.get("facility_type_field", "FTYPE")),
        street_name_column=region.static_field("street_name"),
        street_name_placeholder=region.street_name_placeholder,
    )


def _format_number(value: float) -> str:
    return f"{value:.10g}"


def add_gmns_name(frame: pd.DataFrame, source_column: str, placeholder: str) -> pd.DataFrame:
    """Add GMNS ``name`` from the street-name field, blanking the Cube placeholder."""
    if source_column not in frame.columns:
        raise KeyError(f"link.csv has no {source_column} column; cannot build 'name'")
    source = frame[source_column].astype(str).str.strip()
    frame[NAME_COLUMN] = source.mask(source == placeholder, "")
    columns = [column for column in frame.columns if column != NAME_COLUMN]
    insert_at = columns.index("to_node_id") + 1 if "to_node_id" in columns else len(columns)
    columns.insert(insert_at, NAME_COLUMN)
    return frame[columns]


def apply_conic_overlay(
    frame: pd.DataFrame,
    period: str,
    period_hours: float,
    params: ConicParameters,
    ref_volume_field: str,
) -> tuple[pd.DataFrame, dict]:
    """Rewrite the VDF columns of a converted link.csv. ``frame`` must be read as str."""
    ft_col = params.facility_type_column
    for required in (ft_col, "link_type", "vdf_type", "vdf_alpha", "vdf_beta",
                     "vdf_plf", "ref_volume", ref_volume_field):
        if required not in frame.columns:
            raise KeyError(f"link.csv has no {required} column")

    ftype = pd.to_numeric(frame[ft_col], errors="coerce")
    if ftype.isna().any():
        raise ValueError(f"{int(ftype.isna().sum())} links have a non-numeric {ft_col}")
    ftype = ftype.astype(int)

    # Area type comes from the converter's link_type = divisor x ATYPE + FTYPE.
    # Asserted, because a wrong decode would silently select wrong parameters.
    link_type = pd.to_numeric(frame["link_type"], errors="coerce")
    if link_type.isna().any():
        raise ValueError(f"{int(link_type.isna().sum())} links have a non-numeric link_type")
    link_type = link_type.astype(int)
    divisor = params.link_type_divisor
    atype = link_type // divisor
    mismatch = int(((link_type % divisor) != ftype).sum())
    if mismatch:
        raise ValueError(
            f"link_type does not decode to {ft_col} on {mismatch} links; the "
            f"{divisor}*ATYPE+FTYPE convention does not hold, so area type is unsafe"
        )

    unknown = sorted(set(ftype.unique()) - set(params.alpha_pooled) - {params.connector_ftype})
    if unknown:
        raise ValueError(f"No conic alpha for facility type {unknown}; refusing to default")

    plf = params.plf(period, period_hours)
    is_connector = ftype == params.connector_ftype
    resolved = [
        params.alpha(f, a) if f != params.connector_ftype
        else (CONNECTOR_RULE["vdf_alpha"], "connector")
        for f, a in zip(ftype, atype)
    ]
    alpha = pd.Series([v for v, _ in resolved], index=frame.index, dtype=float)
    alpha_source = pd.Series([s for _, s in resolved], index=frame.index)
    beta = alpha.map(lambda a: spiess_beta(a) if a > 1.0 else CONNECTOR_RULE["vdf_beta"])
    alpha = alpha.where(~is_connector, CONNECTOR_RULE["vdf_alpha"])
    beta = beta.where(~is_connector, CONNECTOR_RULE["vdf_beta"])

    frame = frame.copy()
    frame["vdf_type"] = pd.Series(
        [CONNECTOR_RULE["vdf_type"] if c else CONIC_VDF_TYPE for c in is_connector],
        index=frame.index,
    ).astype(str)
    frame["vdf_alpha"] = alpha.map(_format_number)
    frame["vdf_beta"] = beta.map(_format_number)
    frame["vdf_plf"] = _format_number(plf)

    ref_volume = pd.to_numeric(frame[ref_volume_field], errors="coerce")
    if ref_volume.isna().any():
        raise ValueError(f"{int(ref_volume.isna().sum())} links have a non-numeric {ref_volume_field}")
    frame["ref_volume"] = ref_volume.map(_format_number)

    frame = add_gmns_name(frame, params.street_name_column, params.street_name_placeholder)

    cells = pd.Series(1, index=pd.MultiIndex.from_arrays([ftype, atype])).groupby(level=[0, 1]).sum()
    stats = {
        "period": period,
        "period_hours": float(period_hours),
        "period_factor_E": params.period_factor[str(period).lower()],
        "vdf_plf": plf,
        "links": int(len(frame)),
        "connector_links": int(is_connector.sum()),
        "road_links": int((~is_connector).sum()),
        "alpha_source_counts": {str(k): int(v) for k, v in alpha_source.value_counts().items()},
        "alpha_inherited_cells": {f"{f}x{a}": r for (f, a), r in params.inherited_cells.items()},
        "links_by_ft_at": {f"{int(f)}x{int(a)}": int(n) for (f, a), n in cells.items()},
        "name_populated": int((frame[NAME_COLUMN] != "").sum()),
        "ref_volume_source": ref_volume_field,
        "ref_volume_total": float(ref_volume.sum()),
    }
    return frame, stats
