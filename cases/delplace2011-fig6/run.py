"""Recompute Delplace et al. Fig. 6 in units of the intercell hopping."""

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np
from scipy.linalg import eigh_tridiagonal
from scipy.optimize import brentq
from scipy.special import eval_chebyu
from threadpoolctl import threadpool_limits

CASE = Path(__file__).resolve().parent


def solve(cells, ratio):
    diagonal = np.zeros(2 * cells)
    hopping = np.ones(2 * cells - 1)
    hopping[::2] = ratio
    energy, vectors = eigh_tridiagonal(diagonal, hopping)
    return hopping, energy, vectors


def analytic_spectrum(cells, ratio):
    """Solve the published boundary equations separately from the matrix."""
    if ratio == 0:
        return np.repeat([-1., 0., 1.], [cells - 1, 2, cells - 1]), None

    def quantization(x):
        return ratio * eval_chebyu(cells, x) + eval_chebyu(cells - 1, x)

    poles = np.cos(np.arange(1, cells + 1) * np.pi / (cells + 1))
    roots = [brentq(quantization, right, left) for left, right in zip(poles[:-1], poles[1:])]
    critical = cells / (cells + 1)
    decay = None
    if ratio > critical:
        roots.append(brentq(quantization, -1, poles[-1]))
    elif ratio == critical:
        roots.append(-1.)
    positive = list(np.sqrt(1 + ratio**2 + 2 * ratio * np.array(roots)))
    if ratio < critical:
        def boundary(decay):
            if decay == 0:
                return critical - ratio
            return np.sinh(cells * decay) / np.sinh((cells + 1) * decay) - ratio

        decay = brentq(boundary, 0, -np.log(ratio) + 1)
        positive.append(np.sinh(decay) / np.sinh((cells + 1) * decay))
    return np.sort(np.r_[-np.array(positive), positive]), decay


def calculate(out, config):
    os.environ.setdefault("MPLCONFIGDIR", str(CASE / "outputs" / ".mplconfig"))
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    cells = config["cells"]
    critical = cells / (cells + 1)
    ratios = np.linspace(0, config["ratio_max"], 2 * config["coarse_intervals"] + 1)
    profile_ratios = config["edge_profile_ratios"]
    count_ratios = (0.8, 0.95)
    extras = [critical, 1., *profile_ratios, *count_ratios]
    energies = []
    references = []
    vectors = []
    residuals = []
    orthogonality = []
    edge_differences = {}
    edge_counts = {}

    for ratio in [*ratios, *extras]:
        hopping, energy, wave = solve(cells, ratio)
        matrix = np.diag(hopping, 1) + np.diag(hopping, -1)
        ref, decay = analytic_spectrum(cells, ratio)
        energies.append(energy)
        references.append(ref)
        vectors.append(wave)
        residuals.append(np.max(np.linalg.norm(matrix @ wave - wave * energy, axis=0)) / (1 + ratio))
        orthogonality.append(np.max(np.abs(wave.T @ wave - np.eye(2 * cells))))
        if ratio in profile_ratios:
            m = np.arange(1, cells + 1)
            profile = np.empty(2 * cells)
            profile[::2] = np.sinh(decay * (cells + 1 - m))
            profile[1::2] = np.sinh(decay * m)
            density = profile**2 / np.sum(profile**2)
            edge_differences[str(ratio)] = float(np.max(np.abs(wave[:, cells-1:cells+1]**2 - density[:, None])))
        if ratio in count_ratios:
            edge_counts[str(ratio)] = int(np.count_nonzero(np.abs(energy) < abs(ratio-1)))

    energy = np.array(energies)
    reference = np.array(references)
    scan = energy[:len(ratios)]
    uniform = np.sort(2 * np.cos(np.arange(1, 2*cells+1) * np.pi / (2*cells+1)))
    thresholds = config["thresholds"]
    checks = {}

    def check(name, value):
        limit = thresholds.get(name, thresholds["analytic_energy"])
        checks[name] = {"value": float(value), "limit": limit, "passed": bool(value <= limit)}

    check("residual", max(residuals))
    check("orthogonality", max(orthogonality))
    check("energy_pairing", np.max(np.abs(energy + energy[:, ::-1])))
    check("analytic_energy", np.max(np.abs(energy - reference)))
    check("decoupled_limit", np.max(np.abs(scan[0] - np.repeat([-1., 0., 1.], [cells-1, 2, cells-1]))))
    check("uniform_limit", np.max(np.abs(energy[len(ratios)+1] - uniform)))
    check("edge_density", max(edge_differences.values()))
    check("midpoint_interpolation", np.max(np.abs(scan[1::2] - (scan[:-2:2] + scan[2::2])/2)))
    checks["gap_state_count"] = {"value": edge_counts, "expected": {"0.8": 2, "0.95": 0},
                                 "passed": edge_counts == {"0.8": 2, "0.95": 0}}

    np.savetxt(out/"spectrum.csv", np.column_stack([ratios, scan]), delimiter=",",
               header="ratio," + ",".join(f"energy_{i+1}" for i in range(2*cells)), comments="")
    np.savez_compressed(out/"eigenpairs.npz", ratios=[*ratios, *extras], energy=energy,
                        analytic_energy=reference, vectors=np.array(vectors))
    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    ax.plot(ratios, scan, color="#334e68", linewidth=0.75)
    ax.plot(ratios, ratios - 1, "--", color="#707070", label="Infinite-chain band edges")
    ax.plot(ratios, 1 - ratios, "--", color="#707070")
    edge = ratios < critical
    edge_ratio = np.r_[ratios[edge], critical]
    edge_energy = np.r_[scan[edge, cells], energy[len(ratios), cells]]
    ax.plot(edge_ratio, edge_energy, color="#00856a", linewidth=2, label="Finite-chain edge pair")
    ax.plot(edge_ratio, -edge_energy, color="#00856a", linewidth=2)
    ax.set(xlabel="Intracell / intercell hopping  t'/t", ylabel="Energy  E/t",
           title=f"Open SSH chain · {cells} unit cells", xlim=(0, config["ratio_max"]))
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(out/"spectrum.png", dpi=180)
    plt.close(fig)
    (out/"checks.json").write_text(json.dumps(checks, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"{sum(c['passed'] for c in checks.values())}/{len(checks)} checks passed")
    return 0 if all(c["passed"] for c in checks.values()) else 2


def main():
    started = datetime.now(timezone.utc)
    clock = time.perf_counter()
    out = CASE / "outputs" / started.strftime("%Y%m%dT%H%M%S_%fZ")
    snapshot = out / "snapshot"
    snapshot.mkdir(parents=True)
    status = {"started_utc": started.isoformat(), "cwd": str(Path.cwd()),
              "command": subprocess.list2cmdline([sys.executable, *sys.argv]),
              "python": sys.version, "platform": platform.platform(), "seed": None, "threads": 1}
    code = 1
    try:
        for name in ("run.py", "config.json", "extraction.md", "plan.md", "records/baseline/record.json"):
            shutil.copy2(CASE/name, snapshot/Path(name).name)
        status["versions"] = {name: importlib.metadata.version(name) for name in
                              ("numpy", "scipy", "matplotlib", "threadpoolctl")}
        config = json.loads((snapshot/"config.json").read_text(encoding="utf-8"))
        with threadpool_limits(limits=1):
            code = calculate(out, config)
    except Exception:
        (out/"failure.log").write_text(traceback.format_exc(), encoding="utf-8")
    status.update(exit_code=code, elapsed_seconds=time.perf_counter()-clock)
    (out/"status.json").write_text(json.dumps(status, indent=2)+"\n", encoding="utf-8")
    hashes = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.rglob("*")) if p.is_file()}
    (out/"manifest.json").write_text(json.dumps(hashes, indent=2)+"\n", encoding="utf-8")
    print(f"{out} (exit {code})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
