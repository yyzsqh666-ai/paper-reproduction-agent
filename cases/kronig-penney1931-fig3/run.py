"""Recompute §1 Fig. 3 of the 1931 Kronig–Penney paper."""
import argparse
import csv
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time




ROOT = Path(__file__).resolve().parent
PI = math.pi


@dataclass(frozen=True)
class Sample:
    u: float
    left: float | None
    right: float | None
    strength: float

    @property
    def branch(self):
        if self.left is None:
            return "right"
        if self.right is None:
            return "left"
        return "join"


def sample_grid(count, switch):
    for i in range(2 * count + 1):
        left = i / count if i <= count else None
        right = (2 * count - i) / count if i >= count else None
        if left is not None:
            strength = switch * left
        else:
            strength = switch / right if right > 0 else math.inf
        yield Sample(i / count, left, right, strength)


def bisect_increasing(function, hi, steps):
    lo = 0.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        if function(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def lower_edge(band, strength, switch, steps):
    bottom, top = (band - 1) * PI, band * PI
    if strength == 0:
        return bottom
    if math.isinf(strength):
        return top
    if strength <= switch:
        def equation(t):
            return (bottom + t) * math.sin(t / 2) - strength * math.cos(t / 2)

        return bottom + bisect_increasing(equation, PI, steps)

    def equation(d):
        return math.sin(d / 2) - (top - d) * math.cos(d / 2) / strength

    return top - bisect_increasing(equation, PI, steps)


def edges_at(strength, band_count, switch, steps):
    return np.array([
        (lower_edge(n, strength, switch, steps), n * PI)
        for n in range(1, band_count + 1)
    ])


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def dispersion(z, strength):
    return np.cos(z) + strength * np.sinc(z / PI)


def check_bands(samples, z, energy, config, count, switch):
    strength = np.array([s.strength for s in samples])
    u = np.array([s.u for s in samples])
    tolerance = config["tolerances"]
    band_count = config["band_count"]
    exact = np.arange(1, band_count + 1) ** 2
    # Compare the exported chart position with a fresh mapping from P.
    left_u = strength[:count + 1] / switch
    right_u = 2 - switch / strength[count:]
    coordinate_error = float(max(np.max(np.abs(left_u - u[:count + 1])),
                                 np.max(np.abs(right_u - u[count:]))))
    grid = {
        "chart_positions": len(samples),
        "bands_per_position": band_count,
        "rows": len(samples) * band_count,
        "join_rows_in_grid": sum(s.branch == "join" for s in samples),
        "max_coordinate_error": coordinate_error,
    }
    left_values = [s.left for s in samples[:count + 1]]
    right_values = [s.right for s in samples[count:]]
    grid["pass"] = (
        len(samples) == 2 * count + 1 and z.shape == (len(samples), band_count, 2)
        and grid["join_rows_in_grid"] == 1 and strength[count] == switch
        and strength[0] == 0 and math.isinf(strength[-1])
        and bool(np.all(strength[1:] > strength[:-1]))
        and left_values[0] == right_values[-1] == 0
        and left_values[-1] == right_values[0] == 1
        and bool(np.all(np.diff(left_values) > 0))
        and bool(np.all(np.diff(right_values) < 0))
        and coordinate_error <= tolerance["coordinate"]
    )

    finite_strength = strength[:-1]
    signs = (-1) ** np.arange(band_count)
    target = np.column_stack((signs, -signs))
    residual = np.abs(dispersion(z[:-1], finite_strength[:, None, None]) - target)
    allowed_mid = np.abs(dispersion(z[:-1].mean(axis=2), finite_strength[:, None]))
    previous_upper = np.column_stack((np.zeros(len(samples)), z[:, :-1, 1]))
    gap_mid = (previous_upper[1:-1] + z[1:-1, :, 0]) / 2
    gap_margin = np.abs(dispersion(gap_mid, strength[1:-1, None])) - 1
    min_gap = np.min(energy[1:, 1:, 0] - energy[1:, :-1, 1])
    min_finite_width = np.min(energy[:-1, :, 1] - energy[:-1, :, 0])
    min_lower_step = np.min(np.diff(energy[:, :, 0], axis=0))
    upper_error = np.max(np.abs(energy[:, :, 1] - exact))
    intervals = {
        "max_lower_edge_residual": float(np.max(residual[:, :, 0])),
        "max_upper_edge_residual": float(np.max(residual[:, :, 1])),
        "max_abs_F_inside": float(np.max(allowed_mid)),
        "min_abs_F_minus_1_in_forbidden_region": float(np.min(gap_margin)),
        "min_interband_gap_for_positive_P": float(min_gap),
        "min_width_at_finite_P": float(min_finite_width),
        "min_increase_of_lower_edge": float(min_lower_step),
        "max_upper_energy_error": float(upper_error),
    }
    intervals["pass"] = bool(
        float(np.max(residual)) <= tolerance["dispersion"]
        and intervals["max_abs_F_inside"] <= 1 + tolerance["dispersion"]
        and intervals["min_abs_F_minus_1_in_forbidden_region"] > 0
        and min_gap > 0 and min_finite_width > 0 and min_lower_step > 0
        and upper_error == 0
    )

    strong_p = switch * tolerance["strong_barrier_strength_over_switch"]
    strong = (edges_at(strong_p, band_count, switch, config["bisection_steps"]) / PI) ** 2
    strong_widths = strong[:, 1] - strong[:, 0]
    limits = {
        "free_intervals": energy[0].tolist(),
        "infinite_barrier_intervals": energy[-1].tolist(),
        "strong_finite_P": strong_p,
        "strong_finite_widths": strong_widths.tolist(),
        "max_strong_finite_width": float(max(strong_widths)),
    }
    limits["pass"] = (
        np.array_equal(energy[0], np.column_stack((np.r_[0, exact[:-1]], exact)))
        and np.array_equal(energy[-1], np.column_stack((exact, exact)))
        and limits["max_strong_finite_width"] <= tolerance["strong_barrier_max_width"]
    )
    return {"A1_grid": grid, "A2_intervals": intervals, "A3_limits": limits}


def finite_difference_edges(strength, size, count):
    inverse_spacing_squared = size ** 2
    matrix = np.diag(np.full(size, 2.0 * inverse_spacing_squared))
    i = np.arange(size - 1)
    matrix[i, i + 1] = matrix[i + 1, i] = -inverse_spacing_squared
    matrix[0, 0] += 2 * strength * size
    per_phase = []
    for phase in (1, -1):
        matrix[0, -1] = matrix[-1, 0] = -phase * inverse_spacing_squared
        per_phase.extend(np.linalg.eigvalsh(matrix)[:count])
    return (np.sort(per_phase) / PI ** 2).reshape(count, 2)


def check_finite_difference(output, mode, config, switch):
    fd = config["fd"][mode]
    count = config["band_count"]
    rows = []
    maxima = []
    for size in fd["nodes"]:
        largest = 0.0
        for relative_p in fd["strength_over_switch"]:
            strength = relative_p * switch
            reference = (edges_at(strength, count, switch, config["bisection_steps"]) / PI) ** 2
            numerical = finite_difference_edges(strength, size, count)
            errors = np.abs(numerical - reference)
            largest = max(largest, float(np.max(errors)))
            for index, (fd_edges, equation_edges, error) in enumerate(
                    zip(numerical, reference, errors), start=1):
                rows.append((relative_p, strength, size, index, *fd_edges, *equation_edges, *error))
        maxima.append(largest)
    ratios = [new / old for old, new in zip(maxima, maxima[1:])]
    write_csv(output / "fd-verification.csv",
              ("P_over_4pi", "P", "nodes", "band", "fd_lower", "fd_upper",
               "equation_lower", "equation_upper", "abs_error_lower", "abs_error_upper"), rows)
    return {
        "nodes": fd["nodes"],
        "P_over_4pi": fd["strength_over_switch"],
        "max_absolute_error_by_size": maxima,
        "ratios_new_over_old": ratios,
        "max_finest_error_threshold": fd["max_error"],
        "max_refinement_ratio_threshold": config["fd"]["max_refinement_ratio"],
        "pass": maxima[-1] <= fd["max_error"]
        and max(ratios) <= config["fd"]["max_refinement_ratio"],
    }


def plot_bands(output, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator

    # Read the delivered plotting table so the figure and CSV share identical data.
    fig, ax = plt.subplots(figsize=(4.65, 6.35))
    fig.subplots_adjust(left=0.23, right=0.94, bottom=0.18, top=0.85)
    fig.text(0.23, 0.941, "Kronig–Penney (1931)", fontsize=16, weight="bold", color="#15252d")
    fig.text(0.23, 0.902, "Figure 3  ·  First three allowed bands", fontsize=10, color="#405765")
    for n in sorted({int(row["band"]) for row in rows}):
        band = [row for row in rows if int(row["band"]) == n]
        x = [float(row["x_plot"]) for row in band]
        lower = [float(row["y_lower"]) for row in band]
        upper = [float(row["y_upper"]) for row in band]
        ax.fill_between(x, lower, upper, facecolor="#deebef", edgecolor="#5e8594",
                        hatch="///", linewidth=0, zorder=2)
        ax.plot(x, lower, color="#184e61", linewidth=1.25, zorder=3)
        ax.plot(x, upper, color="#184e61", linewidth=1.05, zorder=3)
    ax.axvline(1, color="#60747c", linewidth=0.9, zorder=4)
    ax.set(xlim=(0, 2), ylim=(0, 9.24), ylabel=r"$(\beta a/\pi)^2$")
    ax.set_xticks((0, 1, 2), ("0", "1", "0"))
    ax.yaxis.set_major_locator(FixedLocator((0, 1, 4, 9)))
    ax.tick_params(axis="both", labelsize=10, length=3.5, color="#52646b")
    ax.yaxis.label.set_size(13)
    for name in ("bottom", "left", "right"):
        ax.spines[name].set_color("#52646b")
        ax.spines[name].set_linewidth(0.9)
    ax.spines["top"].set_visible(False)
    for x, label in [(0.25, r"$P/(4\pi)$"), (0.75, r"$4\pi/P$")]:
        ax.text(x, -0.105, label, transform=ax.transAxes, ha="center", fontsize=12,
                color="#15252d")
    for x, label in [(0, r"$P=0$"), (0.5, r"$P=4\pi$"), (1, r"$P\to\infty$")]:
        ax.text(x, -0.178, label, transform=ax.transAxes, ha="center", fontsize=9,
                color="#405765")
    fig.savefig(output / "fig3.png", dpi=260)
    fig.savefig(output / "fig3.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def peak_memory_bytes():
    if sys.platform == "win32":
        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if not query(get_process(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
        return counters.PeakWorkingSetSize
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else 1024 * peak


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_provenance(output):
    source = json.loads((ROOT / "records/baseline/record.json").read_text(encoding="utf-8"))
    files = ("run.py", "run.ps1", "config.json", "plan.md", "extraction.md", "requirements-lock.txt")
    inputs = {name: sha256(ROOT / name) for name in files}
    snapshot = output / "snapshot"
    snapshot.mkdir()
    for name in files:
        shutil.copyfile(ROOT / name, snapshot / name)
    attached_pdf = ROOT / source["source"]["path"]
    actual_pdf_hash = sha256(attached_pdf)
    save_json(output / "inputs.json", {
        "sha256": inputs,
        "baseline_sha256": source["snapshots_sha256"],
        "source_pdf": source["source"],
        "source_pdf_sha256_at_run": actual_pdf_hash,
    })
    if actual_pdf_hash != source["source"]["sha256"]:
        raise ValueError("The source PDF differs from the frozen attachment.")
    installed = {dist.metadata["Name"].lower(): dist.version for dist in distributions()
                 if dist.metadata["Name"]}
    locked = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines()
    packages = {line.split("==")[0]: installed.get(line.split("==")[0]) for line in locked if line}
    save_json(output / "environment.json", {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
        "logical_cpus_visible": os.cpu_count(),
        "packages": packages,
        "numpy_build": np.show_config(mode="dicts"),
        "process_environment": {key: os.environ.get(key) for key in
                                ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                                 "MPLCONFIGDIR", "MPLBACKEND")},
        "working_directory": str(Path.cwd()),
        "python_command": subprocess.list2cmdline([sys.executable, *sys.orig_argv[1:]]),
        "random_seed": None,
        "random_seed_note": "Deterministic; no random numbers used.",
    })


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("smoke", "full"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reserved", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
    from run_evidence import run
    return run(ROOT, args.output, False, lambda out, config: compute(out, config, args.mode, started),
               reserved=args.reserved)


def compute(output, config, mode, started):
    global np
    import numpy as np
    print(f"START {datetime.now(timezone.utc).isoformat()} | {mode} | {output.resolve()}")
    save_provenance(output)
    switch = config["switch_P_over_pi"] * PI
    count = config["plot_subdivisions"][mode]
    samples = list(sample_grid(count, switch))
    z = np.array([edges_at(s.strength, config["band_count"], switch, config["bisection_steps"])
                  for s in samples])
    energy = (z / PI) ** 2
    rows = ((s.u, s.branch, s.left, s.right, s.strength, n, *zed, *ene)
            for s, zs, es in zip(samples, z, energy)
            for n, (zed, ene) in enumerate(zip(zs, es), start=1))
    bands = output / "band-edges.csv"
    write_csv(bands, ("x_plot", "branch", "P_over_4pi", "four_pi_over_P", "P", "band",
                      "beta_a_lower", "beta_a_upper", "y_lower", "y_upper"), rows)

    checks = check_bands(samples, z, energy, config, count, switch)
    checks["A4_independent_fd"] = check_finite_difference(output, mode, config, switch)
    if mode == "full":
        with bands.open(encoding="utf-8", newline="") as stream:
            plot_bands(output, list(csv.DictReader(stream)))

    resource_check = {
        "python_seconds": time.perf_counter() - started,
        "python_peak_memory_bytes": peak_memory_bytes(),
        "wall_limit_seconds": config["limits"]["wall_seconds"],
        "memory_limit_bytes": config["limits"]["memory_bytes"],
    }
    resource_check["pass"] = (
        resource_check["python_seconds"] <= resource_check["wall_limit_seconds"]
        and resource_check["python_peak_memory_bytes"] <= resource_check["memory_limit_bytes"]
    )
    checks["A6_python_resources"] = resource_check
    checks["all_programmatic_checks_pass"] = all(check["pass"] for check in checks.values())
    save_json(output / "checks.json", checks)
    print(json.dumps(checks, indent=2))
    print(f"END {datetime.now(timezone.utc).isoformat()}")
    return 0 if checks["all_programmatic_checks_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
