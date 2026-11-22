"""Rebuild Roy's Legendre GPS for the three H2 s-wave states in Table II."""

import argparse
import csv
import ctypes
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.linalg import eigh
from scipy.special import eval_genlaguerre, eval_legendre, roots_jacobi
from threadpoolctl import threadpool_info, threadpool_limits


@dataclass(frozen=True)
class Morse:
    depth: float
    equilibrium: float
    mass: float
    inverse_length: float
    hartree_ev: float

    @classmethod
    def from_paper_units(cls, params):
        equilibrium = params["equilibrium_angstrom"] / params["bohr_angstrom"]
        return cls(
            depth=params["depth_ev"] / params["hartree_ev"],
            equilibrium=equilibrium,
            mass=params["reduced_mass_u"] / params["electron_mass_u"],
            inverse_length=params["morse_alpha"] / equilibrium,
            hartree_ev=params["hartree_ev"],
        )

    def potential(self, r):
        decaying = np.exp(-self.inverse_length * (r - self.equilibrium))
        return self.depth * decaying * (decaying - 2)


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_memory():
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        get_memory = kernel.K32GetProcessMemoryInfo
        get_memory.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_memory.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not get_memory(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "peak_working_set_bytes": counters.PeakWorkingSetSize,
            "peak_commit_bytes": counters.PeakPagefileUsage,
        }

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"peak_working_set_bytes": peak * (1 if sys.platform == "darwin" else 1024)}


def gps_run(model, setting, alpha, cutoff, states, limits):
    started = time.perf_counter()
    degree, radius = setting["degree"], setting["r_max_bohr"]
    x, _ = roots_jacobi(degree - 1, 1, 1)
    poly = eval_legendre(degree, x)
    length = alpha * radius / 2
    denom = 1 - x + alpha
    r = length * (1 + x) / denom
    jac = length * (2 + alpha) / denom**2

    i_diag = np.diag_indices(x.size)
    separation = x[:, None] - x[None, :]
    separation[i_diag] = 1
    second = -2 / separation**2
    second[i_diag] = -degree * (degree + 1) / (3 * (1 - x**2))
    polynomial_error = None
    if setting["id"] == "smoke":
        p = (1 - x**2) * (1 + x / 4)
        polynomial_error = float(np.max(np.abs(poly * (second @ (p / poly)) + 2 + 1.5 * x)))

    hamiltonian = -second / (2 * model.mass * np.outer(jac, jac))
    hamiltonian[i_diag] += model.potential(r)
    symmetric = bool(np.array_equal(hamiltonian, hamiltonian.T))
    if not symmetric:
        raise ArithmeticError(f"{setting['id']}: matrix is not exactly symmetric")
    energy, vectors = eigh(hamiltonian, subset_by_index=(0, len(states) - 1), driver="evr")
    residual_ev = np.linalg.norm(hamiltonian @ vectors - vectors * energy, axis=0)
    residual_ev *= model.hartree_ev

    psi = vectors * (poly / np.sqrt(jac))[:, None]
    nodes = []
    for state in psi.T:
        signs = np.signbit(state[np.abs(state) > cutoff * np.max(np.abs(state))])
        nodes.append(int(np.count_nonzero(signs[1:] != signs[:-1])))

    ordered_bound = bool(np.all(np.diff(energy) > 0) and np.all(energy < 0))
    rows = [
        {
            "grid": setting["id"],
            "N": degree,
            "r_max_bohr": radius,
            "n": n,
            "energy_ev": float(energy[n] * model.hartree_ev),
            "residual_ev": float(residual_ev[n]),
            "observed_nodes": nodes[n],
            "passes_state_checks": bool(
                ordered_bound and nodes[n] == n and residual_ev[n] <= limits["matrix_residual_ev"]
            ),
        }
        for n in states
    ]
    metadata = {
        "grid": setting["id"],
        "potential_minimum_grid_ev": float(np.min(model.potential(r)) * model.hartree_ev),
        "exactly_symmetric": symmetric,
        "ordered_bound": ordered_bound,
        "polynomial_max_abs_error": polynomial_error,
        "elapsed_s": time.perf_counter() - started,
    }
    return rows, metadata


def analytic_morse(model, states, radius):
    """Full-line solution computed without the GPS matrix or reference table."""
    a = model.inverse_length
    lam = np.sqrt(2 * model.mass * model.depth) / a
    samples = np.linspace(0, model.equilibrium + 8 / a, 4097)
    radii = np.concatenate(([0, radius], samples))
    log_y = np.log(2 * lam) - a * (radii - model.equilibrium)
    y = np.exp(log_y)
    for n in states:
        s = lam - n - 0.5
        if s <= 0:
            raise ValueError(f"Analytic Morse state {n} is not bound")
        with np.errstate(divide="ignore"):
            log_psi = s * log_y - y / 2 + np.log(np.abs(eval_genlaguerre(n, 2 * s, y)))
        log_ratio = log_psi[:2] - np.max(log_psi[2:])
        yield {
            "n": n,
            "lambda": float(lam),
            "energy_analytic_ev": float(-a**2 * s**2 / (2 * model.mass) * model.hartree_ev),
            "log10_origin_relative_amplitude": float(log_ratio[0] / np.log(10)),
            "log10_box_end_relative_amplitude": float(log_ratio[1] / np.log(10)),
        }


def compare_paper(ref_path, states, primary, default, thresholds):
    with ref_path.open(encoding="utf-8", newline="") as f:
        paper_rows = list(csv.DictReader(f))
    if [(int(row["n"]), int(row["ell"])) for row in paper_rows] != [(n, 0) for n in states]:
        raise ValueError("Expected exactly the three target rows from the author result column")
    rows = []
    for reference in paper_rows:
        n = int(reference["n"])
        printed = reference["minus_e_pr_ev"]
        binding_ref = float(printed)
        for label, group in [("main", primary), ("paper_default", default)]:
            energy = group[n]["energy_ev"]
            delta = -energy - binding_ref
            rows.append({
                "n": n,
                "ell": 0,
                "gps_grid": label,
                "minus_e_pr_ev": printed,
                "e_calculated_ev": energy,
                "minus_e_calculated_ev": -energy,
                "signed_delta_ev": delta,
                "absolute_delta_ev": abs(delta),
                "relative_absolute_delta": abs(delta) / binding_ref,
                "same_8_decimal_rounding": f"{-energy:.8f}" == printed,
                "passes_8_decimal": abs(delta) <= thresholds["paper_rounding_ev"]
                and f"{-energy:.8f}" == printed,
                "passes_1_micro_ev": abs(delta) <= thresholds["paper_micro_ev"],
            })
    return rows


def run(config, case, out, log):
    model = Morse.from_paper_units(config["physical"])
    states = config["physical"]["states"]
    if states != [0, 1, 2] or config["physical"]["ell"] != 0:
        raise ValueError("This case covers n=0,1,2 at ell=0 only")
    gps = config["gps"]
    thresholds = config["thresholds"]
    model_au = {name: float(value) for name, value in vars(model).items()}
    save_json(out / "model_atomic_units.json", model_au)

    by_grid = {}
    failed_grids = []
    for setting in gps["grids"]:
        rows, metadata = gps_run(
            model, setting, gps["mapping_alpha"], gps["node_amplitude_cutoff"], states, thresholds
        )
        grid = setting["id"]
        by_grid[grid] = rows
        save_json(out / f"gps_{grid}.json", {"diagnostics": metadata, "states": rows})
        log.info(
            "%s: N=%d, radius=%g bohr, elapsed=%.4f s, B(eV)=%s",
            grid, setting["degree"], setting["r_max_bohr"], metadata["elapsed_s"],
            [round(-row["energy_ev"], 12) for row in rows],
        )
        if not all(row["passes_state_checks"] for row in rows):
            failed_grids.append(grid)
            log.warning("%s: state, bound-energy ordering, or residual check failed", grid)
            if grid == "smoke":
                raise ArithmeticError("Smoke test failed state checks")
        if grid == "smoke" and metadata["polynomial_max_abs_error"] > thresholds["polynomial_max_abs"]:
            raise ArithmeticError("Smoke test failed the polynomial differentiation check")

    primary = by_grid["main"]
    convergence = []
    for rows in by_grid.values():
        for row in rows:
            convergence.append({
                **row,
                "absolute_delta_vs_main_ev": abs(
                    row["energy_ev"] - primary[row["n"]]["energy_ev"]
                ),
            })
    save_csv(out / "gps_convergence.csv", convergence)
    controlled = {"refine_600", "box_160", "box_240"}
    convergence_passed = all(
        row["absolute_delta_vs_main_ev"] <= thresholds["convergence_ev"]
        for row in convergence if row["grid"] in controlled
    )

    radius = next(grid["r_max_bohr"] for grid in gps["grids"] if grid["id"] == "main")
    analytic = list(analytic_morse(model, states, radius))
    for row in analytic:
        e_main = primary[row["n"]]["energy_ev"]
        delta = abs(e_main - row["energy_analytic_ev"])
        log_max = np.log10(thresholds["analytic_endpoint_relative_amplitude"])
        row.update(
            energy_main_ev=e_main,
            absolute_delta_ev=delta,
            passes=bool(
                delta <= thresholds["analytic_agreement_ev"]
                and row["log10_origin_relative_amplitude"] < log_max
                and row["log10_box_end_relative_amplitude"] < log_max
            ),
        )
    save_csv(out / "analytic_verification.csv", analytic)

    comparisons = compare_paper(case / config["paper_reference"], states, primary,
                                by_grid["paper_default"], thresholds)
    save_csv(out / "table2_comparison.csv", comparisons)
    checks = {
        "discrete_checks": not failed_grids,
        "failed_discrete_grids": failed_grids,
        "grid_and_box_convergence": convergence_passed,
        "independent_analytic": all(row["passes"] for row in analytic),
        "paper_8_decimal_by_grid": {
            grid: all(row["passes_8_decimal"] for row in comparisons if row["gps_grid"] == grid)
            for grid in ("main", "paper_default")
        },
        "paper_1_micro_ev_by_grid": {
            grid: all(row["passes_1_micro_ev"] for row in comparisons if row["gps_grid"] == grid)
            for grid in ("main", "paper_default")
        },
    }
    save_json(out / "checks.json", checks)
    log.info("Checks: %s", checks)
    if failed_grids or not (convergence_passed and checks["independent_analytic"]):
        raise ArithmeticError("One or more solver checks failed. See checks.json and grid data.")


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    args = parser.parse_args()

    case = Path(__file__).resolve().parent
    now = datetime.now(timezone.utc)
    out = case / "evidence" / now.strftime("%Y%m%dT%H%M%S_%fZ")
    out.mkdir(parents=True)
    logger = logging.getLogger("roy2013")
    logger.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(out / "run-log.txt", encoding="utf-8")):
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    command = subprocess.list2cmdline([sys.executable, *sys.argv])
    logger.info("UTC start %s", now.isoformat())
    logger.info("CWD %s", Path.cwd())
    logger.info("Command %s", command)
    logger.info("Output %s", out)

    code = 1
    failure = None
    memory = {}
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        inputs = {
            "config": args.config.resolve(),
            "solver": Path(__file__).resolve(),
            "paper_reference": case / config["paper_reference"],
            "paper_pdf": case / config["source_pdf"],
            "extraction": case / "extraction.md",
            "pre_run_plan": case / "plan.md",
        }
        for name in ("config", "solver", "paper_reference"):
            shutil.copyfile(inputs[name], out / inputs[name].name)
        budget = config["budget"]
        with threadpool_limits(limits=budget["blas_threads"], user_api="blas"):
            save_json(out / "environment.json", {
                "started_at_utc": now.isoformat(),
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cpu_count_logical": os.cpu_count(),
                "versions": {name: version(name) for name in ("numpy", "scipy", "threadpoolctl")},
                "cwd": str(Path.cwd()),
                "command": command,
                "argv": sys.argv,
                "threadpools_during_run": threadpool_info(),
                "random_seed": None,
                "inputs": {
                    name: {"path": str(path), "sha256": sha256(path)}
                    for name, path in inputs.items()
                },
            })
            run(config, case, out, logger)
        memory = peak_memory()
        if max(memory.values()) > budget["memory_bytes"]:
            raise RuntimeError("Peak process memory exceeded configured budget")
        if time.perf_counter() - started > budget["seconds"]:
            raise RuntimeError("Runtime exceeded configured budget")
        code = 0
    except Exception as error:
        failure = str(error)
        logger.exception("Run failed")
    finally:
        if not memory:
            try:
                memory = peak_memory()
            except OSError:
                logger.exception("Could not measure process memory")
        status = {
            "exit_code": code,
            "failure": failure,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started,
            "process_memory": memory,
        }
        save_json(out / "status.json", status)
        if code == 0:
            # Publication of this pointer is independent of the paper agreement criteria.
            pointer = case / f".latest-success-{out.name}.json"
            save_json(pointer, {"evidence": out.relative_to(case).as_posix()})
            pointer.replace(case / "latest-success.json")
        logger.info("Exit %d, elapsed %.4f s, memory %s", code, status["elapsed_seconds"], memory)
    return code


if __name__ == "__main__":
    sys.exit(main())
