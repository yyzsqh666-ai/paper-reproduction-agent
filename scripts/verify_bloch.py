"""Independent linear finite elements for one Bloch cell, in units a=1."""
import csv
import math
import numpy as np
from scipy.linalg import eigh
from threadpoolctl import threadpool_limits


def edges(strength, nodes):
    h = 1 / nodes
    result = []
    for sign in (1, -1):
        # Assemble local stiffness and consistent mass for -d²/dx².
        # Last element's right node equals sign times the first node.
        k = np.zeros((nodes, nodes))
        m = np.zeros_like(k)
        for i in range(nodes):
            j = (i + 1) % nodes
            phase = sign if j == 0 else 1
            for a in (i, j):
                k[a,a] += 1/h
                m[a,a] += h/3
            k[i,j] -= phase/h
            k[j,i] -= phase/h
            m[i,j] += phase*h/6
            m[j,i] += phase*h/6
        k[0,0] += 2 * strength
        result.extend(eigh(k, m, eigvals_only=True, subset_by_index=(0,2)))
    return np.sort(result) / math.pi**2


def check(csv_path):
    with csv_path.open(encoding="utf8") as stream:
        rows = list(csv.DictReader(stream))
    result = []
    with threadpool_limits(limits=1):
        for p in (2*math.pi, 6*math.pi):
            target = sorted((r for r in rows if math.isclose(float(r["P"]), p, rel_tol=1e-12)),
                            key=lambda r:int(r["band"]))
            reference = [float(r[key]) for r in target for key in ("y_lower","y_upper")]
            errors = []
            for size in (128,256):
                values = edges(p, size)
                errors.append(float(max(abs(values-reference))))
            result.append(dict(P=p, csv=reference, fem256=values.tolist(), errors=errors,
                               passed=errors[1]<0.002 and errors[1]<0.35*errors[0]))
    return {"nodes":[128,256], "tolerance":0.002, "max_ratio":0.35, "points":result,
            "passed":all(x["passed"] for x in result)}

