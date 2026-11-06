"""Reproduce section 2.1 only. References and derivations: ../extraction.md.
All numerical settings beyond Table 1 are explicit exploratory assumptions.
"""
import argparse
import contextlib
import csv
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

CASE = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(CASE / "outputs" / ".mplconfig"))
import numpy as np
import scipy
from scipy.linalg import eig_banded
from scipy.integrate import solve_bvp
from threadpoolctl import threadpool_limits, threadpool_info
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def hermite_states(x, k):
    """Normalized analytic whole-line eigenfunctions by ladder recurrence."""
    u = np.zeros((len(x), k))
    u[:, 0] = np.pi ** (-0.25) * np.exp(-x*x/2)
    if k > 1:
        u[:, 1] = np.sqrt(2)*x*u[:, 0]
    for n in range(1, k-1):
        u[:, n+1] = np.sqrt(2/(n+1))*x*u[:, n] - np.sqrt(n/(n+1))*u[:, n-1]
    return u


def solve_fd(L, h, order, k=10, closure="zero"):
    N = round(2*L/h)
    if abs(N*h-2*L) > 1e-11 or N <= k+2:
        raise ValueError("Nonintegral or too-small grid")
    x = np.linspace(-L, L, N+1)[1:-1]
    width = order//2
    ab = np.zeros((width+1, N-1))
    ab[0] = (1 if order == 2 else 1.25)/h**2 + x*x/2
    ab[1, :-1] = (-0.5 if order == 2 else -2/3)/h**2
    if order == 4:
        ab[2, :-2] = 1/(24*h*h)
        if closure == "odd":
            ab[0, [0, -1]] -= 1/(24*h*h)
    elif closure != "zero":
        raise ValueError("odd closure is only defined for order 4")
    e, v = eig_banded(ab, lower=True, select="i", select_range=(0, k-1))
    analytic = hermite_states(x, k)
    psi = v/np.sqrt(h)
    signs = np.where(np.sum(psi*analytic, axis=0) < 0, -1, 1)
    psi *= signs
    # Apply stencil directly, separately from LAPACK band storage.
    hv = ab[0, :, None]*psi
    for d in range(1, width+1):
        hv[d:] += ab[d, :-d, None]*psi[:-d]
        hv[:-d] += ab[d, :-d, None]*psi[d:]
    norm_bound = np.max(np.abs(ab[0])) + 2*sum(np.max(np.abs(ab[d])) for d in range(1, width+1))
    residual = np.linalg.norm(hv-psi*e, axis=0)*np.sqrt(h)/(norm_bound+np.abs(e))
    wave_error = np.sqrt(h*np.sum((psi-analytic)**2, axis=0))
    parity = np.sqrt(h*np.sum((psi[::-1]-psi*((-1.)**np.arange(k)))**2, axis=0))
    orth = np.max(np.abs(h*psi.T@psi-np.eye(k)))
    return dict(x=x, e=e, psi=psi, analytic=analytic, residual=residual,
                wave_error=wave_error, parity=parity, orth=float(orth))


def continuous_reference(L, n, tol, max_nodes):
    """Adaptive continuous ODE collocation; no finite-difference Hamiltonian."""
    x = np.linspace(-L, L, 501)
    a = hermite_states(x, n+1)
    y = a[:, n]
    dy = -x*y if n == 0 else np.sqrt(2*n)*a[:, n-1]-x*y
    integ = np.concatenate(([0.], np.cumsum((y[:-1]**2+y[1:]**2)*np.diff(x)/2)))
    norm = np.sqrt(integ[-1])
    init = np.array([y/norm, dy/norm, integ/integ[-1]])

    def fun(t, u, p):
        return np.vstack((u[1], (t*t-2*p[0])*u[0], u[0]**2))

    def bc(left, right, p):
        return np.array([left[0], right[0], left[2], right[2]-1])

    sol = solve_bvp(fun, bc, x, init, p=[n+0.5], tol=tol, max_nodes=max_nodes)
    sample = np.linspace(-L, L, 4001)
    vals = sol.sol(sample)[0]
    active = vals[1:-1]
    active = active[np.abs(active) > 1e-8*np.max(np.abs(active))]
    nodes = int(np.count_nonzero(active[:-1]*active[1:] < 0))
    return sol, dict(L=L, n=n, tol=tol, energy=float(sol.p[0]), status=int(sol.status),
                     success=bool(sol.success), nodes=nodes, mesh_points=len(sol.x),
                     max_rms_residual=float(np.max(sol.rms_residuals)))


def execute(out, config):
    t = config["thresholds"]
    checks = []

    def check(name, ok, value, limit):
        checks.append(dict(name=name, passed=bool(ok), value=value, criterion=limit))

    paper_rows = list(csv.DictReader((CASE / "source/table1.csv").open(encoding="utf-8")))
    cache = {}
    metrics, table, raw = [], [], {}
    L = config["paper"]["L"]
    for order in (2, 4):
        for h in sorted(set(config["convergence_h"]+config["paper"]["h"]), reverse=True):
            s = solve_fd(L, h, order, config["paper"]["states"])
            cache[order, h] = s
            tag = f"o{order}_h{h:g}"
            for field in ("x", "e", "psi", "analytic"):
                raw[tag+"_"+field] = s[field]
            for n, en in enumerate(s["e"]):
                metrics.append(dict(order=order, h=h, L=L, n=n, energy=float(en),
                                    signed_error=float(en-n-0.5), abs_error=float(abs(en-n-0.5)),
                                    wave_L2=float(s["wave_error"][n]), relative_residual=float(s["residual"][n]),
                                    parity_error=float(s["parity"][n]), orthogonality=s["orth"]))
                if h in config["paper"]["h"]:
                    ref = float(paper_rows[n][f"order{order}_h{h:g}"])
                    table.append(dict(n=n, order=order, h=h, computed=float(en), printed=ref,
                                      delta=float(en-ref), computed_6dp=f"{en:.6f}",
                                      printed_6dp=f"{ref:.6f}", rounding_match=f"{en:.6f}" == f"{ref:.6f}"))
            print(f"L={L:g} order={order} h={h:g}; max energy error={max(abs(s['e']-np.arange(10)-.5)):.6g}", flush=True)
    np.savez_compressed(out / "eigenpairs.npz", **raw)
    csv_write(out / "metrics.csv", metrics)
    csv_write(out / "table1_comparison.csv", table)
    check("table1_rounding", all(r["rounding_match"] for r in table), sum(r["rounding_match"] for r in table), "40/40 exact six-decimal strings")
    check("table1_interval", max(abs(r["delta"]) for r in table) <= t["table_absolute"], max(abs(r["delta"]) for r in table), t["table_absolute"])
    for key, threshold in [("relative_residual", "relative_residual"), ("parity_error", "parity"), ("orthogonality", "orthogonality")]:
        m = max(r[key] for r in metrics)
        check(key, m <= t[threshold], m, t[threshold])
    convergence = []
    for order in (2, 4):
        hs = config["fit_h"]
        for n in range(10):
            for metric in ("energy", "wave"):
                errors = [abs(cache[order, h]["e"][n]-n-.5) if metric == "energy" else cache[order, h]["wave_error"][n] for h in hs]
                slope = float(np.polyfit(np.log(hs), np.log(errors), 1)[0])
                convergence.append(dict(order=order, n=n, metric=metric, slope=slope))
        for metric in ("energy", "wave"):
            slopes = [r["slope"] for r in convergence if r["order"] == order and r["metric"] == metric]
            limits = t[f"{metric}_order{order}"]
            check(f"{metric}_convergence_order{order}", all(limits[0] <= p <= limits[1] for p in slopes), [min(slopes), max(slopes)], limits)
        for metric, errors in [("energy", abs(cache[order, .01]["e"]-np.arange(10)-.5)), ("wave", cache[order, .01]["wave_error"])]:
            limit = t[f"fine_{metric}_order{order}"]
            check(f"fine_{metric}_order{order}", max(errors) <= limit, float(max(errors)), limit)
    csv_write(out / "convergence.csv", convergence)
    improved = all(abs(cache[4,h]["e"][n]-n-.5) < abs(cache[2,h]["e"][n]-n-.5) for h in config["paper"]["h"] for n in range(10))
    check("same_h_fourth_more_accurate", improved, improved, "all 20 comparisons")

    refs, domain, bvpraw = [], [], {}
    for domainL in config["domain_L"]:
        reference = {}
        for n in config["domain_states"]:
            for factor in (1, .1):
                sol, info = continuous_reference(domainL, n, config["bvp_tol"]*factor, config["bvp_max_nodes"])
                refs.append(info)
                tag = f"L{domainL:g}_n{n}_tol{info['tol']:g}"
                bvpraw[tag+"_x"] = sol.x
                bvpraw[tag+"_y"] = sol.y
                print(f"BVP {tag}: E={sol.p[0]:.12f}, status={sol.status}, nodes={info['nodes']}", flush=True)
                if factor == 1:
                    coarse = info["energy"]
                else:
                    reference[n] = info["energy"]
                    info["refinement_difference"] = abs(info["energy"]-coarse)
        for h in config["boundary_h"]:
            zero = solve_fd(domainL, h, 4)
            odd = solve_fd(domainL, h, 4, closure="odd")
            second = solve_fd(domainL, h, 2)
            for n in config["domain_states"]:
                ref = reference[n]
                domain.append(dict(L=domainL, h=h, n=n, exact=n+.5, bvp=ref,
                                   order2=float(second["e"][n]), zero4=float(zero["e"][n]), odd4=float(odd["e"][n]),
                                   domain_error=ref-n-.5, smooth_discretization=float(odd["e"][n]-ref),
                                   boundary_difference=float(zero["e"][n]-odd["e"][n]),
                                   order2_discretization=float(second["e"][n]-ref),
                                   total_error=float(zero["e"][n]-n-.5)))
    csv_write(out / "continuous_references.csv", [{k:r.get(k, "") for k in list(refs[-1])} for r in refs])
    csv_write(out / "error_budget.csv", domain)
    np.savez_compressed(out / "bvp_solutions.npz", **bvpraw)
    check("bvp_success_and_nodes", all(r["success"] and r["nodes"] == r["n"] for r in refs),
          [dict(L=r["L"], n=r["n"], status=r["status"], nodes=r["nodes"]) for r in refs], "status=0 and node count=n")
    refine = max(r.get("refinement_difference", 0) for r in refs)
    check("bvp_refinement", refine <= t["bvp_refinement"], refine, t["bvp_refinement"])
    for key, threshold in [("domain_error", "L10_domain_floor"), ("boundary_difference", "L10_boundary_floor")]:
        m = max(abs(r[key]) for r in domain if r["L"] == 10)
        check("L10_"+key, m <= t[threshold], m, t[threshold])
    identity = max(abs(r["domain_error"]+r["smooth_discretization"]+r["boundary_difference"]-r["total_error"]) for r in domain)
    check("error_decomposition_identity", identity <= t["decomposition_identity"], identity, t["decomposition_identity"])
    dump(out / "checks.json", checks)
    make_plots(out, metrics, domain, cache)
    print(f"Checks: {sum(r['passed'] for r in checks)}/{len(checks)}", flush=True)
    return all(r["passed"] for r in checks)


def make_plots(out, metrics, domain, cache):
    plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": .2})
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    for order, color in [(2, "#cb4b16"), (4, "#0072b2")]:
        for n, style in [(0, "o-"), (9, "s--")]:
            rows = sorted([r for r in metrics if r["order"] == order and r["n"] == n], key=lambda r:r["h"])
            for ax, key in zip(axs, ("abs_error", "wave_L2")):
                ax.loglog([r["h"] for r in rows], [r[key] for r in rows], style, color=color, label=f"Order {order}, n={n}")
    for ax, title in zip(axs, ("Energy absolute error", "Wavefunction L2 error")):
        ax.set(xlabel="Grid spacing h", ylabel="Error", title=title+" (L=10)")
        ax.legend(fontsize=9)
    fig.savefig(out / "convergence.png", dpi=180)
    plt.close(fig)
    fig, axs = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for col, n in enumerate((0, 9)):
        for order, color in ((2, "#cb4b16"), (4, "#0072b2")):
            s = cache[order, .1]
            axs[0,col].plot(s["x"], s["psi"][:,n], color=color, label=f"Order {order}")
            axs[1,col].plot(s["x"], s["psi"][:,n]-s["analytic"][:,n], color=color, label=f"Order {order}")
        axs[0,col].plot(s["x"], s["analytic"][:,n], "k--", lw=1, label="Analytic")
        axs[0,col].set(title=f"n={n}, h=0.1", ylabel="Wavefunction")
        axs[1,col].set(xlabel="x", ylabel="Numerical - analytic")
        for ax in axs[:,col]:
            ax.set_xlim(-6,6)
            ax.legend(fontsize=9)
    fig.savefig(out / "wavefunctions.png", dpi=180)
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12,4.8), constrained_layout=True)
    for n in (0,3,9):
        rows = [r for r in domain if r["h"] == .1 and r["n"] == n]
        axs[0].semilogy([r["L"] for r in rows], np.maximum([abs(r["domain_error"]) for r in rows], 1e-14), "o-", label=f"n={n}")
    axs[0].axhline(1e-9, color="gray", ls=":", label="Reference acceptance floor")
    axs[0].set(xlabel="Half interval L", ylabel="|E_BVP - E_infinite|", title="Continuous finite-interval shift")
    rows = sorted([r for r in domain if r["L"] == 5 and r["n"] == 9], key=lambda r:r["h"])
    for key, label in [("domain_error", "Finite interval"), ("smooth_discretization", "Smooth-closure discretization"), ("boundary_difference", "Zero vs odd boundary"), ("total_error", "Total (zero extension)")]:
        axs[1].loglog([r["h"] for r in rows], [abs(r[key]) for r in rows], "o-", label=label)
    axs[1].set(xlabel="h", ylabel="Absolute contribution", title="Error separation: L=5, n=9 (exploratory)")
    for ax in axs:
        ax.legend(fontsize=8)
    fig.savefig(out / "error_budget.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CASE/"config.json")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    out = CASE/"outputs"/started.strftime("%Y%m%dT%H%M%S_%fZ")
    out.mkdir(parents=True, exist_ok=False)
    snap = out/"snapshot"
    snap.mkdir()
    inputs = [args.config.resolve(), Path(__file__).resolve(), CASE/"source/table1.csv", CASE/"extraction.md", CASE/"plan.md"]
    for path in inputs:
        shutil.copy2(path, snap/path.name)
    dump(out/"inputs.json", [{"path":str(p), "sha256":sha(p)} for p in inputs+[CASE/"source/paper.pdf"]])
    command = subprocess.list2cmdline([sys.executable]+sys.argv)
    dump(out/"environment.json", dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
        cwd=str(Path.cwd()), command=command, argv=sys.argv, seed=None, threading="one BLAS thread",
        versions={m:importlib.metadata.version(m) for m in ["numpy","scipy","matplotlib","threadpoolctl"]}, threadpools=threadpool_info()))
    (out/"requirements-lock.txt").write_text(subprocess.check_output([sys.executable,"-m","pip","freeze"], text=True), encoding="utf-8")
    start = time.perf_counter()
    code = 1
    with (out/"run.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            with threadpool_limits(limits=1):
                code = 0 if execute(out, config) else 2
        except Exception:
            traceback.print_exc()
    dump(out/"status.json", dict(started_utc=started.isoformat(), ended_utc=datetime.now(timezone.utc).isoformat(),
         elapsed_seconds=time.perf_counter()-start, exit_code=code, checks_passed=code==0,
         memory_peak="not measured", evidence_label="[推导]", command=command, cwd=str(Path.cwd())))
    dump(out/"manifest.json", [{"path":str(p.relative_to(out)), "sha256":sha(p), "bytes":p.stat().st_size} for p in sorted(out.rglob("*")) if p.is_file()])
    if code == 0:
        (CASE/"latest_run.txt").write_text(out.name+"\n", encoding="utf-8")
    print(str(out))
    print(f"Exit {code}; see run.log and checks.json")
    return code


if __name__ == "__main__":
    sys.exit(main())
