"""Pure VDF, capacity and speed functions. No I/O, no pandas-specific behaviour.

Single source of the conical formula for the whole replay. The overlay that built
the network and the analysis that checks it both resolve alpha/beta through
``conic_vdf``, and every VDF evaluation in the analysis goes through
``conical_vdf`` here, so "the formula" is one implementation rather than two that
happen to agree today.
"""

from __future__ import annotations

import numpy as np

from .conic_vdf import CONNECTOR_RULE, spiess_beta  # noqa: F401  (re-exported)


def conical_vdf(alpha, x, beta=None):
    """Spiess' conical congestion function -- the travel-time *ratio* t / t0.

        t/t0 = 2 + sqrt(alpha^2 (1-x)^2 + beta^2) - alpha (1-x) - beta
        beta = (2 alpha - 1) / (2 alpha - 2)

    The beta constraint is what forces t/t0 == 1 at x == 0; it is not a free
    parameter. Unlike BPR the function stays finite and strictly increasing above
    capacity, which is why Cube uses it and why x is not clipped here.
    """
    alpha = np.asarray(alpha, dtype=float)
    x = np.asarray(x, dtype=float)
    if beta is None:
        beta = (2.0 * alpha - 1.0) / (2.0 * alpha - 2.0)
    beta = np.asarray(beta, dtype=float)
    gap = 1.0 - x
    return 2.0 + np.sqrt(alpha * alpha * gap * gap + beta * beta) - alpha * gap - beta


def bpr_vdf(alpha, beta, x):
    """BPR ratio t/t0 = 1 + alpha * x^beta. With alpha == 0 this is exactly 1."""
    alpha = np.asarray(alpha, dtype=float)
    beta = np.asarray(beta, dtype=float)
    x = np.asarray(x, dtype=float)
    return 1.0 + alpha * np.power(np.maximum(x, 0.0), beta)


def vdf_ratio(vdf_type, alpha, beta, x):
    """Dispatch on ``vdf_type`` the way the kernel does: 1 -> conical, 0 -> BPR.

    Centroid connectors carry ``vdf_type = 0, alpha = 0``, so they return exactly
    1.0 and reproduce Cube's ``I4{P}VDF == 1`` on all 15,986 of them. No conical
    (alpha, beta) can return 1, which is why the connector rule exists at all.
    """
    vdf_type = np.asarray(vdf_type, dtype=float)
    conic = conical_vdf(alpha, x, beta)
    bpr = bpr_vdf(alpha, beta, x)
    return np.where(vdf_type == 1, conic, bpr)


def taplite_doc(volume, lane_capacity, lanes, vdf_plf, period_hours):
    """Degree of congestion as TAPlite computes it (TAPLite.cpp:7904).

        doc = volume / (lane_capacity * lanes * vdf_plf * H)

    ``vdf_plf`` is dimensionless. With ``vdf_plf = E / H`` the denominator collapses
    to Cube's ``lane_capacity * lanes * E``, which is the whole mechanism by which
    the Cube period basis survives without a ``capacity_period`` column.
    """
    denominator = (np.asarray(lane_capacity, dtype=float)
                   * np.asarray(lanes, dtype=float)
                   * np.asarray(vdf_plf, dtype=float)
                   * float(period_hours))
    return np.divide(np.asarray(volume, dtype=float), denominator,
                     out=np.zeros_like(np.asarray(volume, dtype=float)),
                     where=denominator > 0)


def cube_vc(volume, link_capacity, period_factor):
    """Cube's V/C: volume / (hourly link capacity * period factor E)."""
    denominator = np.asarray(link_capacity, dtype=float) * float(period_factor)
    return np.divide(np.asarray(volume, dtype=float), denominator,
                     out=np.zeros_like(np.asarray(volume, dtype=float)),
                     where=denominator > 0)


def travel_time_min(fftt_min, ratio):
    """Congested travel time in minutes from free-flow time and the VDF ratio."""
    return np.asarray(fftt_min, dtype=float) * np.asarray(ratio, dtype=float)


def speed_mph(free_speed_mph, ratio):
    """Congested speed. Cube stores this directly: I4{P}SPD == I4{P}FFSPD / I4{P}VDF."""
    ratio = np.asarray(ratio, dtype=float)
    return np.divide(np.asarray(free_speed_mph, dtype=float), ratio,
                     out=np.zeros_like(ratio), where=ratio > 0)


def vmt(volume, length_mi):
    """Vehicle-miles travelled on one link."""
    return np.asarray(volume, dtype=float) * np.asarray(length_mi, dtype=float)


def vht(volume, travel_time_minutes):
    """Vehicle-hours travelled. Equals VMT / speed; both forms are cross-checked."""
    return np.asarray(volume, dtype=float) * np.asarray(travel_time_minutes, dtype=float) / 60.0


def network_speed(total_vmt, total_vht):
    """The only correct network speed: total VMT / total VHT.

    The arithmetic mean of link speeds is a different quantity and is reported
    beside this one purely so it is visibly labelled as wrong.
    """
    total_vht = float(total_vht)
    return float(total_vmt) / total_vht if total_vht > 0 else float("nan")


def error_stats(values, prefix=""):
    """Median / p95 / p99 / max of an absolute-error array, plus tolerance shares.

    Deliberately a distribution rather than a pass/fail flag -- no replay tolerance
    has been agreed, so the analysis reports what the error *is*.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {f"{prefix}n": 0}
    return {
        f"{prefix}n": int(values.size),
        f"{prefix}median": float(np.median(values)),
        f"{prefix}p95": float(np.percentile(values, 95)),
        f"{prefix}p99": float(np.percentile(values, 99)),
        f"{prefix}max": float(values.max()),
        f"{prefix}share_within_0.001": float((values <= 0.001).mean()),
        f"{prefix}share_within_0.01": float((values <= 0.01).mean()),
        f"{prefix}share_within_0.1": float((values <= 0.1).mean()),
    }
