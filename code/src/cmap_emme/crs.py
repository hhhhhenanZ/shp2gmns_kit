"""EPSG:26771 (NAD27 / Illinois East, US survey feet) -> EPSG:4326.

pyproj is used when installed; it is in requirements.txt and is the method of record.
Without it, a built-in path runs: inverse Transverse Mercator on Clarke 1866 with the
EPSG:26771 parameters, then an abridged Molodensky shift NAD27 -> WGS84 with the NAD27
CONUS mean parameters (dx -8, dy 160, dz 176 m). That path is accurate to a few metres,
enough for a planning network. The method used is written to the manifest and the report.
"""

from __future__ import annotations

import math

import numpy as np

US_FOOT = 1200.0 / 3937.0
# EPSG:26771 [emme_links.prj]
A_CLARKE, INV_F_CLARKE = 6378206.4, 294.9786982138982
LAT0, LON0, K0 = 36.66666666666666, -88.33333333333333, 0.999975
FALSE_EASTING_FT, FALSE_NORTHING_FT = 500000.0, 0.0
# NAD27 CONUS -> WGS84 (DMA TR8350.2 mean values)
DX, DY, DZ = -8.0, 160.0, 176.0
A_WGS, INV_F_WGS = 6378137.0, 298.257223563


def _tm_inverse(x_ft: np.ndarray, y_ft: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a, f = A_CLARKE, 1.0 / INV_F_CLARKE
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
    x = (x_ft - FALSE_EASTING_FT) * US_FOOT
    y = (y_ft - FALSE_NORTHING_FT) * US_FOOT

    def meridian(phi):
        return a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
                    - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * np.sin(2 * phi)
                    + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * np.sin(4 * phi)
                    - (35 * e2**3 / 3072) * np.sin(6 * phi))

    m0 = meridian(math.radians(LAT0))
    m = m0 + y / K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
            + (151 * e1**3 / 96) * np.sin(6 * mu) + (1097 * e1**4 / 512) * np.sin(8 * mu))
    c1 = ep2 * np.cos(phi1) ** 2
    t1 = np.tan(phi1) ** 2
    n1 = a / np.sqrt(1 - e2 * np.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * np.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * K0)
    lat = phi1 - (n1 * np.tan(phi1) / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
    lon = math.radians(LON0) + (d - (1 + 2 * t1 + c1) * d**3 / 6
                                + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2)
                                * d**5 / 120) / np.cos(phi1)
    return lat, lon


def _molodensky(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a, f = A_CLARKE, 1.0 / INV_F_CLARKE
    da, df = A_WGS - A_CLARKE, 1.0 / INV_F_WGS - f
    e2 = 2 * f - f * f
    sl, cl = np.sin(lat), np.cos(lat)
    so, co = np.sin(lon), np.cos(lon)
    rn = a / np.sqrt(1 - e2 * sl**2)
    rm = a * (1 - e2) / (1 - e2 * sl**2) ** 1.5
    dlat = (-DX * sl * co - DY * sl * so + DZ * cl
            + (a * df + f * da) * np.sin(2 * lat)) / rm
    dlon = (-DX * so + DY * co) / (rn * cl)
    return lat + dlat, lon + dlon


def to_wgs84(x_ft, y_ft) -> tuple[np.ndarray, np.ndarray, str]:
    """(lon, lat) in degrees and the method used."""
    x_ft, y_ft = np.asarray(x_ft, float), np.asarray(y_ft, float)
    try:
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:26771", "EPSG:4326", always_xy=True)
        lon, lat = tr.transform(x_ft, y_ft)
        return np.asarray(lon), np.asarray(lat), "pyproj " + __import__("pyproj").__version__
    except ImportError:
        lat, lon = _tm_inverse(x_ft, y_ft)
        lat, lon = _molodensky(lat, lon)
        return np.degrees(lon), np.degrees(lat), "built-in (TM inverse, Clarke 1866 + Molodensky NAD27 CONUS)"
