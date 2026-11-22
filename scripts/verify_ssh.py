from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json
import math
import sys


@dataclass(frozen=True)
class Metric:
    error: float
    tolerance: float

    @property
    def passed(self):
        return self.error <= self.tolerance


# [Original, as recorded in extraction.md] Fig. 6 uses an open 10-cell chain
# and reports hopping ratio r = t'/t and energies E/t.
CELLS = 10
SITES = 2 * CELLS
INTERVALS = 800
RATIO_MAX = 2
# [Assumption] Numerical tolerances fixed before execution. For the spectrum,
# 64 * 20 * eps * 3 < 1e-12, using a max row sum of 3 for ||H/t||.
ENERGY_TOL = 1e-12
# Propagate the energy budget to sum(E**2) at |E| <= 3: at most
# 20 * (2 * 3 * 1e-12 + 1e-24), then allow rounding in the sum.
TRACE_TOL = 2e-10
RATIO_TOL = 2e-15


def max_difference(values, reference):
    return max(abs(actual - expected) for actual, expected in zip(values, reference, strict=True))


def check(path):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        rows = [tuple(map(float, row)) for row in reader]
    columns = ["ratio", *(f"energy_{i}" for i in range(1, SITES + 1))]
    if header != columns or len(rows) != INTERVALS + 1:
        raise ValueError(f"Unexpected spectrum grid or columns in {path}")
    if any(len(row) != len(columns) or not all(map(math.isfinite, row)) for row in rows):
        raise ValueError(f"Invalid numerical row in {path}")
    if any(list(row[1:]) != sorted(row[1:]) for row in rows):
        raise ValueError(f"Energy order is invalid in {path}")

    # [Derivation] At r=0 only 9 intercell bonds remain. Each isolated
    # dimer has eigenvalues +/-1, and the two unpaired sites have E=0.
    decoupled = [-1.0] * (CELLS - 1) + [0.0, 0.0] + [1.0] * (CELLS - 1)
    # At r=1 the open-chain recurrence E u_j = u_(j-1) + u_(j+1)
    # with u_0=u_21=0 admits sine modes u_j = sin(j*m*pi/21).
    uniform = sorted(2 * math.cos(m * math.pi / (SITES + 1)) for m in range(1, SITES + 1))
    # For every r, tr((H/t)^2) sums twice each squared bond strength.
    # There are 10 intracell bonds of strength r and 9 intercell bonds of strength 1.
    trace_errors = [
        abs(math.fsum(energy ** 2 for energy in levels) - 2 * (CELLS * r ** 2 + CELLS - 1))
        for r, *levels in rows
    ]
    worst_trace_index = max(range(len(rows)), key=trace_errors.__getitem__)
    midpoint = rows[INTERVALS // 2][1:]
    metrics = {
        "grid": Metric(max(abs(row[0] - i * RATIO_MAX / INTERVALS) for i, row in enumerate(rows)), RATIO_TOL),
        "r0_dimer_limit": Metric(max_difference(rows[0][1:], decoupled), ENERGY_TOL),
        "r1_uniform_chain": Metric(max_difference(midpoint, uniform), ENERGY_TOL),
        "all_grid_trace_h_squared": Metric(max(trace_errors), TRACE_TOL),
    }
    # In sublattice order H = [[0,B],[B.T,0]], giving pairs +/-svd(B).
    import numpy as np
    r = 0.5
    b = r * np.eye(CELLS) + np.eye(CELLS, k=-1)
    singular = np.linalg.svd(b, compute_uv=False)
    independent = np.sort(np.r_[-singular, singular]).tolist()
    exported = next(row[1:] for row in rows if row[0] == r)
    metrics["r_half_sorted_svd"] = Metric(max_difference(exported, independent), ENERGY_TOL)
    return {
        "r_half_levels": [{"expected": e, "csv": a, "delta": a-e}
                          for e, a in zip(independent, exported, strict=True)],
        "csv": str(path),
        "rows": len(rows),
        "levels_per_row": SITES,
        "metrics": {name: {**asdict(metric), "passed": metric.passed} for name, metric in metrics.items()},
        "r_at_max_trace_error": rows[worst_trace_index][0],
        "r1_lowest_energy": {"computed": midpoint[0], "analytic": uniform[0]},
        "passed": all(metric.passed for metric in metrics.values()),
    }


if __name__ == "__main__":
    results = [check(Path(arg)) for arg in sys.argv[1:]]
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if results and all(item["passed"] for item in results) else 1)
