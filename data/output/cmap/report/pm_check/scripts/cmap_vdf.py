"""CMAP volume-delay functions fd1-fd8, written line by line from Database/data/vdf_iter.in (lines 10-29),
CMAP-REPOS/cmap_trip-based_model (local copy: task_C1_link_21416_proof/inputs/cmap_code/vdf_iter.in).
V = el1 + el2 = @avtot + @busveq (veq, period total); ul1 = free-flow time (min); ul2 = period capacity;
ul3 = signal code: int(ul3/1000) and (ul3 mod 1000) as in the Emme text; length in miles. Returns minutes.
All functions take numpy arrays (or scalars)."""
import numpy as np


def _signal(V, ul2, ul3):
    # ((int(ul3/1000)) / 10 .min. ((1/60) * (((ul3 .mod. 1000) .gt. 0) * (int(ul3/1000) .gt. 0)) *
    #   ((0 .max. (5.96*(V/ul2) - .39*6*int(ul3/1000)*(ul3 .mod. 1000)/100 + .35*6*int(ul3/1000) - 4.47))
    #  + (0 .max. (3.38 - 7.32*(ul3 .mod. 1000)/100 + 2.65*((V/ul2)^8))))))
    a = np.floor(ul3 / 1000.0)
    b = np.mod(ul3, 1000.0)
    x = V / ul2
    flag = ((b > 0) & (a > 0)).astype(float)
    t1 = np.maximum(0.0, 5.96 * x - .39 * 6 * a * b / 100 + .35 * 6 * a - 4.47)
    t2 = np.maximum(0.0, 3.38 - 7.32 * b / 100 + 2.65 * x ** 8)
    return np.minimum(a / 10.0, (1.0 / 60.0) * flag * (t1 + t2))


def fd1(V, ul1, ul2, ul3, length=None):   # arterial street
    return ul1 * (1 + .15 * (V / ul2) ** 4) + _signal(V, ul2, ul3)


def fd2(V, ul1, ul2, ul3=None, length=None):   # freeway
    return (1 + .15 * np.minimum(V / ul2, 1)) * ((ul1 / 1.15) * (1 + .15 * (V / (ul2 + 300)) ** 8))


def fd3(V, ul1, ul2, ul3, length=None):   # freeway/expressway to arterial ramp (same as fd1)
    return fd1(V, ul1, ul2, ul3)


def fd4(V, ul1, ul2, ul3=None, length=None):   # expressway
    return (1 + .15 * np.minimum(V / ul2, 1)) * (ul1 * (1 + .15 * (V / ul2) ** 8))


def fd5(V, ul1, ul2, ul3=None, length=None):   # freeway/expressway to freeway/expressway ramp
    return ul1 * (1 + .15 * (V / ul2) ** 8)


def fd6(V, ul1, ul2, ul3, length):   # zone connector: 20 mph
    return np.asarray(length, dtype=float) * 3 + 0 * np.asarray(V, dtype=float)


def fd7(V, ul1, ul2=None, ul3=None, length=None):   # toll link
    return np.asarray(ul1, dtype=float) + 0 * np.asarray(V, dtype=float)


def fd8(V, ul1, ul2, ul3=None, length=None):   # metered expressway entrance ramp
    return ul1 * (1 + .15 * (V / ul2) ** 10)


FD = {1: fd1, 2: fd2, 3: fd3, 4: fd4, 5: fd5, 6: fd6, 7: fd7, 8: fd8}


def link_time(vdf, V, ul1, ul2, ul3, length):
    """Vectorised over links: picks fd by vdf code. Links with ul2 <= 0 on volume-dependent functions get ul1."""
    vdf = np.asarray(vdf); V = np.asarray(V, float); ul1 = np.asarray(ul1, float)
    ul2 = np.asarray(ul2, float); ul3 = np.asarray(ul3, float); length = np.asarray(length, float)
    out = np.full(V.shape, np.nan)
    safe = np.where(ul2 > 0, ul2, 1.0)
    for k, f in FD.items():
        m = vdf == k
        if m.any():
            out[m] = f(V[m], ul1[m], safe[m], ul3[m], length[m])
    return out


if __name__ == "__main__":
    # check: link 21416-21403 (C1.3): fd2 with V = 13,599 veq -> 0.9320 min (CMAP timau 0.9286)
    print(round(float(fd2(13598.9955, 0.698182, 12000.0)), 4))
    print(fd6(0, 0, 0, 0, 0.5), fd7(100, 0.7))
